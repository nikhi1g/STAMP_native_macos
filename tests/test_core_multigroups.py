"""Multiple-group statistics: ANOVA, Kruskal-Wallis, eta-squared and the post-hoc tests.

Data: Arumugam et al. enterotypes, active groups Enterotype 1/2/3 (8, 6, 18 samples) at the
genus level. ANOVA and Kruskal-Wallis are cross-checked against scipy to 1e-9 relative
tolerance; Tukey-Kramer against scipy.stats.tukey_hsd (STAMP reads the studentized range
critical value from tables, so to table precision); Scheffe and Welch post-hoc against
formulas built from scipy distributions.
"""
import math
import os

import numpy as np
import pytest
from scipy import stats

from stamp.metagenomics.fileIO.StampIO import StampIO
from stamp.metagenomics.fileIO.MetadataIO import MetadataIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'stamp', 'examples', 'EnterotypesArumugam')
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15}
REL = 1e-9
ACTIVE = ('Enterotype 1', 'Enterotype 2', 'Enterotype 3')
POST_HOC_FEATURES = ['Bacteroides', 'Prevotella', 'Ruminococcus', 'Faecalibacterium', 'Alistipes']


def approx(x):
	return pytest.approx(x, rel=REL, abs=1e-12)


@pytest.fixture(scope='module')
def tree_md():
	tree, err = StampIO(PREFS).read(os.path.join(EX, 'Enterotypes.profile.spf'))
	assert err is None
	md, err = MetadataIO(PREFS).read(os.path.join(EX, 'Enterotypes.metadata.tsv'), tree)
	assert err is None
	md.setActiveField('Enterotype', tree)
	return tree, md


def multi_profile(tree_md, active):
	tree, md = tree_md
	mgp = tree.createMultiGroupProfile(list(tree.groupDict.keys()), 'Entire sample', 'Genera', md, 'Remove unclassified reads')
	mgp.setActiveGroups({g: g in active for g in tree.groupDict})
	return mgp


@pytest.fixture(scope='module')
def mgp(tree_md):
	profile = multi_profile(tree_md, ACTIVE)
	assert profile.activeGroupNames == list(ACTIVE)
	assert [len(s) for s in profile.activeSamplesInGroups] == [8, 6, 18]
	return profile


@pytest.mark.filterwarnings('ignore:invalid value encountered:RuntimeWarning')
def test_anova_and_kruskal_wallis_match_scipy(mgp):
	from stamp.plugins.multiGroups.statisticalTests.ANOVA import ANOVA
	from stamp.plugins.multiGroups.statisticalTests.KruskalWallis import KruskalWallis
	anova, kw = ANOVA(PREFS), KruskalWallis(PREFS)
	compared = 0
	for feature in sorted(mgp.getFeatures()):
		data = mgp.getActiveFeatureProportions(feature)
		pAnova, noteAnova = anova.hypothesisTest(data)
		pKW, noteKW = kw.hypothesisTest(data)
		if len(set(np.concatenate(data))) == 1:
			# all values identical: scipy gives nan / raises; STAMP reports 1.0 with a note
			assert (pAnova, noteAnova) == (1.0, 'degenerate case: failed to calculate p-value')
			assert (pKW, noteKW) == (1.0, 'Invalid input data for Kruskal-Wallis H-test.')
			continue
		assert pAnova == approx(stats.f_oneway(*data).pvalue), feature
		assert pKW == approx(stats.kruskal(*data).pvalue), feature
		assert noteAnova == noteKW == ''
		compared += 1
	assert compared > 150


def test_multi_group_tests_degenerate_groups(tree_md):
	"""ANOVA needs 2 samples per group and Kruskal-Wallis 5 (upstream thresholds)."""
	from stamp.plugins.multiGroups.statisticalTests.ANOVA import ANOVA
	from stamp.plugins.multiGroups.statisticalTests.KruskalWallis import KruskalWallis
	twin = multi_profile(tree_md, ACTIVE + ('Enterotype 3 - twin',))
	data = twin.getActiveFeatureProportions('Bacteroides')
	assert ANOVA(PREFS).hypothesisTest(data) == (1.0, 'degenerate case: at least one group contains less than 2 samples')
	infant = multi_profile(tree_md, ACTIVE + ('Infant',))
	data = infant.getActiveFeatureProportions('Bacteroides')
	assert KruskalWallis(PREFS).hypothesisTest(data) == (1.0, 'degenerate case: at least one group contains less than 5 samples')


def test_eta_squared_is_between_over_total_sum_of_squares(mgp):
	from stamp.plugins.multiGroups.effectSizeFilters.EtaSquared import EtaSquared
	eta = EtaSquared(PREFS)
	for feature in sorted(mgp.getFeatures()):
		data = [np.array(g) for g in mgp.getActiveFeatureProportions(feature)]
		allValues = np.concatenate(data)
		sst = ((allValues - allValues.mean()) ** 2).sum()
		ssb = sum(len(g) * (g.mean() - allValues.mean()) ** 2 for g in data)
		expected = ssb / sst if sst != 0 else -1.0
		assert eta.run(data) == pytest.approx(expected, rel=1e-8, abs=1e-12), feature
	assert eta.run([[1.0], []]) == -1.0


def test_tukey_kramer_matches_scipy_tukey_hsd(mgp):
	from stamp.plugins.multiGroups.postHoc.TukeyKramer import TukeyKramer
	tk = TukeyKramer(PREFS)
	for feature in POST_HOC_FEATURES:
		data = mgp.getActiveFeatureProportions(feature)
		pValues, es, lower, upper, labels, note = tk.run(data, 0.95, list(ACTIVE))
		ref = stats.tukey_hsd(*data)
		ci = ref.confidence_interval(0.95)
		pairs = [(0, 1), (0, 2), (1, 2)]
		assert labels == ['Enterotype 1 : Enterotype 2', 'Enterotype 1 : Enterotype 3', 'Enterotype 2 : Enterotype 3']
		for n, (i, j) in enumerate(pairs):
			assert es[n] == approx(np.mean(data[i]) - np.mean(data[j]))
			# q critical value comes from tables with 3 decimals (df = 29 is a table row)
			assert lower[n] == pytest.approx(ci.low[i, j], rel=1e-4), feature
			assert upper[n] == pytest.approx(ci.high[i, j], rel=1e-4), feature
			assert pValues[n] == _category(ref.pvalue[i, j]), feature


def _category(p):
	for cut, label in [(0.001, '< 0.001'), (0.01, '< 0.01'), (0.02, '< 0.02'), (0.05, '< 0.05'), (0.1, '< 0.1')]:
		if p < cut:
			return label
	return '>= 0.1'


def test_games_howell_against_studentized_range(mgp):
	"""No scipy implementation; rebuilt from the Welch-Satterthwaite df and scipy's
	studentized range quantile. STAMP linearly interpolates tabulated q between integer df,
	so the comparison is at 5e-3 relative (the
	interpolation error reaches ~3e-3 near df = 5)."""
	from stamp.plugins.multiGroups.postHoc.GamesHowell import GamesHowell
	gh = GamesHowell(PREFS)
	k = len(ACTIVE)
	for feature in POST_HOC_FEATURES:
		data = [np.array(g) for g in mgp.getActiveFeatureProportions(feature)]
		pValues, es, lower, upper, labels, note = gh.run(data, 0.95, list(ACTIVE))
		n = 0
		for i in range(k):
			for j in range(i + 1, k):
				vi, vj = data[i].var(ddof=1) / len(data[i]), data[j].var(ddof=1) / len(data[j])
				df = (vi + vj) ** 2 / (vi ** 2 / (len(data[i]) - 1) + vj ** 2 / (len(data[j]) - 1))
				half = stats.studentized_range.ppf(0.95, k, df) * math.sqrt((vi + vj) / 2)
				d = data[i].mean() - data[j].mean()
				assert es[n] == approx(d)
				assert (lower[n] + upper[n]) / 2 == approx(d)
				assert (upper[n] - lower[n]) / 2 == pytest.approx(half, rel=5e-3), feature
				p = stats.studentized_range.sf(abs(d) / math.sqrt((vi + vj) / 2), k, df)
				# only check categories when p is not within 10% of a boundary
				if all(abs(p - c) > 0.1 * c for c in (0.001, 0.01, 0.02, 0.05, 0.1)):
					assert pValues[n] == _category(p), feature
				n += 1
	# pinned port output for the first contrast of Bacteroides
	data = mgp.getActiveFeatureProportions('Bacteroides')
	assert gh.run(data, 0.95, list(ACTIVE))[2][0] == approx(24.206860887387762)


def test_scheffe_against_f_distribution(mgp):
	from stamp.plugins.multiGroups.postHoc.Scheffe import Scheffe
	scheffe = Scheffe(PREFS)
	assert scheffe.name == u'Scheff\xE8'
	k = len(ACTIVE)
	for feature in POST_HOC_FEATURES:
		data = [np.array(g) for g in mgp.getActiveFeatureProportions(feature)]
		pValues, es, lower, upper, labels, note = scheffe.run(data, 0.95, list(ACTIVE))
		N = sum(len(g) for g in data)
		mse = sum((len(g) - 1) * g.var(ddof=1) for g in data) / (N - k)
		cv = (k - 1) * stats.f.ppf(0.95, k - 1, N - k)
		n = 0
		for i in range(k):
			for j in range(i + 1, k):
				d = data[i].mean() - data[j].mean()
				inv = 1 / len(data[i]) + 1 / len(data[j])
				p = stats.f.sf(d * d / (mse * inv) / (k - 1), k - 1, N - k)
				assert es[n] == approx(d)
				if p > 1e-6:
					assert pValues[n] == approx(p), feature
				assert lower[n] == approx(d - math.sqrt(cv * inv * mse))
				assert upper[n] == approx(d + math.sqrt(cv * inv * mse))
				n += 1


def test_welch_uncorrected_matches_scipy(mgp):
	from stamp.plugins.multiGroups.postHoc.WelchUncorrected import WelchUncorrected
	welch = WelchUncorrected(PREFS)
	for feature in POST_HOC_FEATURES:
		data = [np.array(g) for g in mgp.getActiveFeatureProportions(feature)]
		pValues, es, lower, upper, labels, note = welch.run(data, 0.95, list(ACTIVE))
		n = 0
		for i in range(3):
			for j in range(i + 1, 3):
				ref = stats.ttest_ind(data[i], data[j], equal_var=False)
				ci = ref.confidence_interval(0.95)
				assert pValues[n] == approx(ref.pvalue), feature
				# upstream passes proportions in percent with parent counts of 0.01 and Welch
				# multiplies by 100 again, so effect sizes and CIs come out 1e4 times the
				# difference in percent; kept for parity
				assert es[n] == approx(1e4 * (data[i].mean() - data[j].mean()))
				assert (lower[n], upper[n]) == (approx(1e4 * ci.low), approx(1e4 * ci.high))
				n += 1


def test_qtable_against_studentized_range():
	from stamp.metagenomics.stats.distributions.QTable import QTable
	q = QTable(PREFS)
	for alpha in (0.001, 0.01, 0.05, 0.1):
		for k, df in [(2, 5), (3, 29), (5, 60), (10, 120), (29, 200)]:
			assert q.cv(alpha, k, df) == pytest.approx(stats.studentized_range.ppf(1 - alpha, k, df), rel=2e-3)
	assert q.cvInterpolate(0.05, 3, 29.5) == approx((q.cv(0.05, 3, 29) + q.cv(0.05, 3, 30)) / 2)
	assert q.cv(0.05, 1, 10) == 1000.0
	# upstream bug kept for parity: the tables stop at k = 29 but cv() clamps k to 30
	with pytest.raises(IndexError):
		q.cv(0.05, 30, 10)


def test_multi_group_pipeline_post_hoc_and_filters(mgp):
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatsTests
	from stamp.plugins.multiGroups.statisticalTests.ANOVA import ANOVA
	from stamp.plugins.multiGroups.effectSizeFilters.EtaSquared import EtaSquared
	from stamp.plugins.multiGroups.postHoc.TukeyKramer import TukeyKramer
	from stamp.plugins.multiGroups.postHoc.Scheffe import Scheffe
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	m = MultiGroupStatsTests(PREFS)
	m.run(ANOVA(PREFS), EtaSquared(PREFS), mgp)
	res = m.results
	res.performMultCompCorrection(NoCorrection(PREFS))
	h = res.dataHeadings
	assert len(res.data) == mgp.getNumFeatures()
	pValues = res.getColumn('pValues', False)
	assert pValues == sorted(pValues)

	expected = {}
	for row in res.data:
		data = mgp.getActiveFeatureProportions(row[0])
		allValues = np.concatenate(data)
		p = 1.0 if len(set(allValues)) == 1 else stats.f_oneway(*data).pvalue
		assert row[h['pValues']] == approx(p)
		# per-group mean and std. dev. columns follow the fixed headings
		for g, values in enumerate(data):
			assert row[5 + 2 * g] == approx(np.mean(values))
			assert row[6 + 2 * g] == approx(np.std(values))
		expected[row[0]] = (p, row[h['EffectSize']])

	res.selectAllFeautres()
	res.filterFeatures(0.05, None, 0)
	sign = {f for f, (p, _) in expected.items() if p <= 0.05}
	assert set(res.getActiveFeatures()) == sign and len(sign) == ANOVA_SIGNIFICANT_GENERA
	res.filterFeatures(0.05, EtaSquared(PREFS), 0.5)
	strong = {f for f, (p, eta) in expected.items() if p <= 0.05 and eta >= 0.5}
	assert set(res.getActiveFeatures()) == strong and 0 < len(strong) < len(sign)

	m.runPostHocTest(TukeyKramer(PREFS), mgp, 'Bacteroides', 0.95)
	ph = res.postHocResults
	assert (ph.feature, ph.alpha, ph.pValues) == ('Bacteroides', pytest.approx(0.05), ['< 0.001', '< 0.001', '>= 0.1'])
	m.runPostHocTest(Scheffe(PREFS), mgp, 'Bacteroides', 0.95)
	assert res.postHocTest == u'Scheff\xE8'
	m.runPostHocTest(Scheffe(PREFS), mgp, '', 0.95)
	assert res.postHocResults.labels == []


def test_get_p_value_str_keeps_python2_behaviour():
	"""Upstream compared the formatted string with a float; Python 2 evaluated that as False."""
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatTestResults
	res = MultiGroupStatTestResults(PREFS)
	assert res.getPValueStr(1e-20) == '1.00e-20'
	assert res.getPValueStr(2.5e-3) == '2.50e-3'
	assert res.getPValueStr(0.25) == '0.250'


ANOVA_SIGNIFICANT_GENERA = 18
