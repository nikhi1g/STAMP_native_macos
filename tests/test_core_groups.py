"""Two-group statistics: t-test, Welch's t-test, White's non-parametric test, group effect sizes.

Data: Arumugam et al. enterotypes, Enterotype 1 (8 samples) vs Enterotype 2 (6 samples).
The t-tests are cross-checked against scipy.stats.ttest_ind (p-values and the confidence
interval of the difference in means) to 1e-9 relative tolerance.
"""
import os
import random

import numpy as np
import pytest
from scipy import stats

from stamp.metagenomics.fileIO.StampIO import StampIO
from stamp.metagenomics.fileIO.MetadataIO import MetadataIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'stamp', 'examples', 'EnterotypesArumugam')
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15}
REL = 1e-9


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


def group_profile(tree_md, g1, g2, level):
	tree, md = tree_md
	return tree.createGroupProfile(g1, g2, 'Entire sample', level, md, 'Remove unclassified reads')


@pytest.fixture(scope='module')
def genera(tree_md):
	gp = group_profile(tree_md, 'Enterotype 1', 'Enterotype 2', 'Genera')
	assert (len(gp.samplesInGroup1), len(gp.samplesInGroup2)) == (8, 6)
	return gp


def proportions(gp, feature):
	s1, s2 = gp.getFeatureCounts(feature)
	p1, p2 = gp.getParentFeatureCounts(feature)
	return np.array(s1) / np.array(p1), np.array(s2) / np.array(p2)


@pytest.mark.parametrize('plugin, equalVar', [('Ttest', True), ('Welch', False)])
def test_t_tests_match_scipy(genera, plugin, equalVar):
	module = __import__('stamp.plugins.groups.statisticalTests.' + plugin, fromlist=[plugin])
	test = getattr(module, plugin)(PREFS)
	compared = 0
	for feature in sorted(genera.getFeatures()):
		s1, s2 = genera.getFeatureCounts(feature)
		p1, p2 = genera.getParentFeatureCounts(feature)
		oneSided, twoSided, lower, upper, es, note = test.run(s1, s2, p1, p2, None, 0.95)
		x, y = proportions(genera, feature)
		assert es == approx(100 * (x.mean() - y.mean()))
		if x.var() == 0 and y.var() == 0:
			continue
		res = stats.ttest_ind(x, y, equal_var=equalVar)
		ci = res.confidence_interval(0.95)
		assert twoSided == approx(res.pvalue), feature
		assert oneSided == approx(stats.ttest_ind(x, y, equal_var=equalVar, alternative='greater').pvalue), feature
		assert (lower, upper) == (approx(100 * ci.low), approx(100 * ci.high)), feature
		assert note == ''
		compared += 1
	assert compared > 150


def test_t_tests_degenerate_cases(tree_md):
	"""A group with one sample ('Enterotype 3 - twin') and zero-variance groups."""
	from stamp.plugins.groups.statisticalTests.Ttest import Ttest
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
	gp = group_profile(tree_md, 'Enterotype 3 - twin', 'Enterotype 1', 'Phyla')
	assert len(gp.samplesInGroup1) == 1
	for plugin, note in [(Ttest, 'degenerate case: both groups must contain at least 2 samples'),
						(Welch, 'degenerate case: both groups must contain at least 2 samples')]:
		g = GroupStatsTests(PREFS)
		g.run(plugin(PREFS), 'Two-sided', None, 0.95, gp)
		assert len(g.results.data) == gp.getNumFeatures()
		for row in g.results.data:
			h = g.results.dataHeadings
			assert (row[h['pValues']], row[h['EffectSize']], row[h['LowerCI']], row[h['UpperCI']]) == (1.0, 0.0, 0.0, 0.0)
			assert row[h['Note']] == note

	# zero variance in both groups: upstream's ZeroDivisionError handler is unreachable (the
	# preceding `except Exception` catches it), so the note is the division error message
	assert Ttest(PREFS).run([1, 1], [2, 2], [10, 10], [10, 10], None, 0.95) == (0.5, 1.0, 0.0, 0.0, 0.0, 'float division by zero')
	assert Welch(PREFS).run([1, 1], [2, 2], [10, 10], [10, 10], None, 0.95) == \
		(1.0, 0.0, -10.0, -10.0, -10.0, 'degenerate case: variance of both groups is zero')


def test_whites_test(tree_md):
	"""White et al. (2009) permutation t-test. With fewer than 8 samples in a group the null
	distribution is pooled over the high-frequency features; sparse features fall back to
	Fisher's exact test on summed counts. Monte Carlo output is pinned under fixed seeds."""
	from stamp.plugins.groups.statisticalTests.White import White
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptoticCC import DiffBetweenPropAsymptoticCC
	gp = group_profile(tree_md, 'Enterotype 1', 'Enterotype 2', 'Phyla')
	features = gp.getFeatures()
	seq1, seq2 = gp.getFeatureCountsAll()
	par1, par2 = gp.getParentFeatureCountsAll()

	random.seed(1)
	np.random.seed(1)
	oneSided, twoSided, lower, upper, es, notes = White(PREFS).runAll(seq1, seq2, par1, par2, None, 0.95, None)

	n1, n2 = len(seq1[0]), len(seq2[0])
	fishers, cc = Fishers(PREFS), DiffBetweenPropAsymptoticCC(PREFS)
	sparse = 0
	for i, feature in enumerate(features):
		assert 0.0 <= oneSided[i] <= 1.0 and 0.0 <= twoSided[i] <= 1.0
		if sum(seq1[i]) < n1 and sum(seq2[i]) < n2:
			sparse += 1
			args = (sum(seq1[i]), sum(seq2[i]), sum(par1[i]), sum(par2[i]))
			assert notes[i] == "heuristic: statistics calculated with Fisher's test"
			assert (oneSided[i], twoSided[i]) == fishers.hypothesisTest(*args)[:2]
			assert (lower[i], upper[i], es[i]) == cc.run(*args, coverage=0.95)[:3]
		else:
			welch = Welch(PREFS).run(seq1[i], seq2[i], par1[i], par2[i], None, 0.95)
			assert es[i] == approx(welch[4])
			assert lower[i] <= upper[i]
	assert sparse > 0
	got = {f: (twoSided[i], lower[i], upper[i]) for i, f in enumerate(features) if f in WHITE_SEED1}
	assert len(WHITE_SEED1) == 3
	for f, values in WHITE_SEED1.items():
		assert got[f] == pytest.approx(values, rel=REL), f


def test_group_effect_size_filters():
	from stamp.plugins.groups.effectSizeFilters.DiffBetweenProp import DiffBetweenProp
	from stamp.plugins.groups.effectSizeFilters.RatioProportions import RatioProportions
	x, y = [1.5, 2.5, 3.0, 4.25], [0.5, 1.0, 2.0]
	assert DiffBetweenProp(PREFS).run(x, y) == approx(np.mean(x) - np.mean(y))
	assert DiffBetweenProp(PREFS).run([], y) == approx(-np.mean(y))
	assert RatioProportions(PREFS).run(x, y) == approx(np.mean(x) / np.mean(y))
	# zero mean: pseudocount scaled by the sum of the means is added to both
	pc = 0.5 / (0 + np.mean(y))
	assert RatioProportions(PREFS).run([0.0, 0.0], y) == approx(pc / (np.mean(y) + pc))


def test_group_stats_pipeline_and_filters(genera):
	from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	from stamp.plugins.groups.effectSizeFilters.DiffBetweenProp import DiffBetweenProp
	from stamp.plugins.groups.effectSizeFilters.RatioProportions import RatioProportions
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	g = GroupStatsTests(PREFS)
	g.run(Welch(PREFS), 'Two-sided', None, 0.95, genera)
	res = g.results
	res.performMultCompCorrection(NoCorrection(PREFS))
	h = res.dataHeadings
	assert len(res.data) == genera.getNumFeatures()
	pValues = res.getColumn('pValues', False)
	assert pValues == sorted(pValues)

	expected = {}
	for row in res.data:
		x, y = proportions(genera, row[0])
		assert row[h['MeanRelFreq1']] == approx(100 * x.mean())
		assert row[h['StdDevRelFreq1']] == approx(100 * x.std())
		assert row[h['MeanRelFreq2']] == approx(100 * y.mean())
		assert row[h['StdDevRelFreq2']] == approx(100 * y.std())
		p = 1.0 if x.var() == 0 and y.var() == 0 and x.mean() == y.mean() else stats.ttest_ind(x, y, equal_var=False).pvalue
		expected[row[0]] = (p, 100 * abs(x.mean() - y.mean()))

	res.selectAllFeautres()
	res.filterFeatures(0.05, None, 0, 0, None, 0, 0, None, 0, None, None, 0)
	sign = {f for f, (p, _) in expected.items() if p <= 0.05}
	assert set(res.getActiveFeatures()) == sign and len(sign) == WELCH_SIGNIFICANT_GENERA

	res.filterFeatures(0.05, None, 0, 0, None, 0, 0, DiffBetweenProp(PREFS), 1.0, None, None, 0)
	big = {f for f, (p, d) in expected.items() if p <= 0.05 and d >= 1.0}
	assert set(res.getActiveFeatures()) == big and 0 < len(big) < len(sign)

	res.filterFeatures(0.05, None, 0, 0, None, 0, 0, DiffBetweenProp(PREFS), 1.0, 'OR', RatioProportions(PREFS), 2.0)
	assert set(res.getActiveFeatures()) <= big


WELCH_SIGNIFICANT_GENERA = 3
# (two-sided p, lower CI, upper CI) from this port with random.seed(1), numpy.random.seed(1).
# Python 3's random.sample draws a different permutation stream than Python 2 did, so these
# Monte Carlo values are port-specific; the checks above verify the deterministic parts.
WHITE_SEED1 = {
	'Firmicutes': (0.9333636363636363, -18.499104466676627, 14.11684714037819),
	'Bacteroidetes': (0.9704545454545453, -18.166782903850308, 16.927117949607062),
	'Verrucomicrobia': (0.31127272727272726, 0.006057589734546247, 2.993436893062221),
}
