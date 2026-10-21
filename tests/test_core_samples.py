"""Two-sample statistics: every statistical test, CI method and effect-size filter.

Data: the Edwards iron-mine profile (Red vs Black, integer counts, 247 subsystems), the
two-sample example analysed in the STAMP paper. Exact tests are cross-checked against scipy
to 1e-9 relative tolerance. Where STAMP subtracts a CDF from 1.0 (chi-square, G-test,
hypergeometric) only features with p > 1e-5 are compared, because 1 - cdf loses relative
precision for tiny p-values in upstream's own formulation.
"""
import math
import os

import numpy as np
import pytest
from scipy import stats
from scipy.stats.contingency import odds_ratio, relative_risk

from stamp.metagenomics.fileIO.StampIO import StampIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IRON = os.path.join(ROOT, 'stamp', 'examples', 'IronMineEdwards', 'EdwardsIronMine.spf')
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15}
REL = 1e-9


def approx(x):
	return pytest.approx(x, rel=REL)


@pytest.fixture(scope='module')
def profile():
	tree, err = StampIO(PREFS).read(IRON)
	assert err is None
	sp = tree.createSampleProfile('Red', 'Black', 'Entire sample', 'Subsystem', 'Remove unclassified reads')
	assert sp.getNumFeatures() == 247
	return sp


@pytest.fixture(scope='module')
def tables(profile):
	rows = sorted(profile.getLabeledTables())
	for _, s1, s2, t1, t2 in rows:
		assert s1 == int(s1) and s2 == int(s2)
	return rows


def cells(s1, s2, t1, t2):
	return int(s1), int(s2), int(t1 - s1), int(t2 - s2)


# ---------------------------------------------------------------- statistical tests

def test_fishers_matches_scipy_fisher_exact(tables):
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	fishers = Fishers(PREFS)
	for feature, s1, s2, t1, t2 in tables:
		a, b, c, d = cells(s1, s2, t1, t2)
		oneSided, twoSided, note = fishers.hypothesisTest(s1, s2, t1, t2)
		table = [[a, b], [c, d]]
		assert twoSided == approx(stats.fisher_exact(table).pvalue), feature
		less = stats.fisher_exact(table, alternative='less').pvalue
		greater = stats.fisher_exact(table, alternative='greater').pvalue
		assert oneSided == approx(min(less, greater)), feature
		assert note == ''


def test_hypergeometric_is_doubled_one_sided_fisher(tables):
	from stamp.plugins.samples.statisticalTests.Hypergeometric import Hypergeometric
	hyper = Hypergeometric(PREFS)
	compared = 0
	for feature, s1, s2, t1, t2 in tables:
		a, b, c, d = cells(s1, s2, t1, t2)
		oneSided, twoSided, _ = hyper.hypothesisTest(s1, s2, t1, t2)
		assert twoSided == 2 * oneSided
		# P(X <= a) and P(X >= a) for the hypergeometric distribution with fixed margins
		hg = stats.hypergeom(a + b + c + d, a + b, a + c)
		expected = min(hg.cdf(a), hg.sf(a - 1))
		if expected > 1e-5:
			# upstream sums exp(gammaln(...)) terms (log-magnitudes ~1e5, so ~3e-11 error each)
			# and forms the far tail as 1 - cdf, so its error is absolute (~1e-10), not relative
			assert oneSided == pytest.approx(expected, rel=REL, abs=1e-9), feature
			compared += 1
	assert compared > 200


def _chi2(table, **kw):
	return stats.chi2_contingency(np.array(table, dtype=float), **kw)


def _yates_applies(table):
	# scipy's Yates correction shrinks |O - E| by min(0.5, |O - E|); STAMP always subtracts 0.5
	res = _chi2(table, correction=False)
	return np.all(np.abs(np.array(table) - res.expected_freq) >= 0.5)


@pytest.mark.parametrize('plugin, kw, needsYates', [
	('ChiSquare', dict(correction=False), False),
	('ChiSquareYates', dict(correction=True), True),
	('GTest', dict(correction=False, lambda_='log-likelihood'), False),
	('GTestYates', dict(correction=True, lambda_='log-likelihood'), True),
])
def test_contingency_tests_match_scipy(tables, plugin, kw, needsYates):
	module = __import__('stamp.plugins.samples.statisticalTests.' + plugin, fromlist=[plugin])
	test = getattr(module, plugin)(PREFS)
	compared = 0
	for feature, s1, s2, t1, t2 in tables:
		a, b, c, d = cells(s1, s2, t1, t2)
		oneSided, twoSided, note = test.hypothesisTest(s1, s2, t1, t2)
		assert oneSided == float('inf')
		if a == 0 and b == 0:
			continue
		table = [[a, b], [c, d]]
		expected = _chi2(table, **kw).pvalue
		if expected > 1e-5 and (not needsYates or _yates_applies(table)):
			assert twoSided == approx(expected), feature
			compared += 1
	assert compared > 100


def test_chi_square_degenerate_case():
	from stamp.plugins.samples.statisticalTests.ChiSquare import ChiSquare
	assert ChiSquare(PREFS).hypothesisTest(0, 0, 10, 20) == (float('inf'), 1.0, 'degenerate case: suspect p-value')


def test_diff_between_prop_matches_uncorrected_chi_square(tables):
	"""The pooled two-proportion z-test is the uncorrected chi-square test (z^2 = X^2)."""
	from stamp.plugins.samples.statisticalTests.DiffBetweenProp import DiffBetweenProp
	test = DiffBetweenProp(PREFS)
	compared = 0
	for feature, s1, s2, t1, t2 in tables:
		a, b, c, d = cells(s1, s2, t1, t2)
		oneSided, twoSided, _ = test.hypothesisTest(s1, s2, t1, t2)
		assert twoSided == 2 * oneSided
		if a == 0 and b == 0:
			continue
		expected = _chi2([[a, b], [c, d]], correction=False).pvalue
		if expected > 1e-5:
			assert twoSided == approx(expected), feature
			compared += 1
	assert compared > 100


def test_gtest_fisher_dispatches_on_cell_size(tables):
	from stamp.plugins.samples.statisticalTests.GTestFisher import GTestFisher
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.samples.statisticalTests.GTestYates import GTestYates
	combined, fishers, gYates = GTestFisher(PREFS), Fishers(PREFS), GTestYates(PREFS)
	used = set()
	for feature, s1, s2, t1, t2 in tables:
		small = min(cells(s1, s2, t1, t2)) < 20
		expected = (fishers if small else gYates).hypothesisTest(s1, s2, t1, t2)
		assert combined.hypothesisTest(s1, s2, t1, t2) == expected
		used.add(small)
	assert used == {True, False}


# Bootstrap and permutation tests are Monte Carlo: no exact oracle. They are checked against
# the exact test they estimate (within 5 binomial standard errors) and pinned to the values
# this port produces under a fixed numpy seed.
MC_FEATURES = ['L-ascorbate degradation', 'Pentose phosphate pathway', 'Queuosine-Archaeosine Biosynthesis', 'dTDP-rhamnose synthesis']


def _by_name(tables, name):
	return next(row for row in tables if row[0] == name)


def test_permutation_estimates_fisher(tables):
	from stamp.plugins.samples.statisticalTests.Permutation import Permutation
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	np.random.seed(0)
	perm, fishers = Permutation(PREFS), Fishers(PREFS)
	got = []
	for name in MC_FEATURES:
		_, s1, s2, t1, t2 = _by_name(tables, name)
		oneSided, twoSided, note = perm.hypothesisTest(s1, s2, t1, t2)
		exact = fishers.hypothesisTest(s1, s2, t1, t2)[1]
		se = math.sqrt(exact * (1 - exact) / PREFS['Replicates'])
		assert abs(twoSided - exact) <= 5 * se + 2.0 / PREFS['Replicates'], name
		got.append((oneSided, twoSided))
	assert got == PERMUTATION_SEED0


def test_bootstrap_estimates_z_test(tables):
	from stamp.plugins.samples.statisticalTests.Bootstrap import Bootstrap
	from stamp.plugins.samples.statisticalTests.DiffBetweenProp import DiffBetweenProp
	np.random.seed(0)
	boot, z = Bootstrap(PREFS), DiffBetweenProp(PREFS)
	got = []
	for name in MC_FEATURES:
		_, s1, s2, t1, t2 = _by_name(tables, name)
		oneSided, twoSided, note = boot.hypothesisTest(s1, s2, t1, t2)
		approxP = z.hypothesisTest(s1, s2, t1, t2)[1]
		se = math.sqrt(approxP * (1 - approxP) / PREFS['Replicates'])
		assert abs(twoSided - approxP) <= 5 * se + 0.02, name
		got.append((oneSided, twoSided))
	assert got == BOOTSTRAP_SEED0


def test_resampling_tests_degenerate_parent():
	from stamp.plugins.samples.statisticalTests.Permutation import Permutation
	from stamp.plugins.samples.statisticalTests.Bootstrap import Bootstrap
	assert Permutation(PREFS).hypothesisTest(0, 3, 0, 10) == (1.0, 1.0, 'degenerate case: parent has a count of zero')
	# upstream drops the note for Bootstrap (returns '')
	assert Bootstrap(PREFS).hypothesisTest(0, 3, 0, 10) == (1.0, 1.0, '')


# ---------------------------------------------------------------- confidence intervals

Z95 = stats.norm.ppf(0.975)


def test_odds_ratio_ci_matches_scipy(tables):
	from stamp.plugins.samples.confidenceIntervalMethods.OddsRatio import OddsRatio
	from stamp.plugins.samples.effectSizeFilters.OddsRatio import OddsRatio as OddsRatioFilter
	ci, esFilter = OddsRatio(PREFS), OddsRatioFilter(PREFS)
	compared = 0
	for feature, s1, s2, t1, t2 in tables:
		a, b, c, d = cells(s1, s2, t1, t2)
		lower, upper, es, note = ci.run(s1, s2, t1, t2, 0.95)
		assert esFilter.run(s1, s2, t1, t2) == approx(es)
		if 0 in (a, b, c, d):
			# Haldane correction: add the pseudocount to every cell
			a, b, c, d = (x + 0.5 for x in (a, b, c, d))
			assert es == approx(a * d / (b * c))
			se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
			assert lower == approx(es * math.exp(-Z95 * se))
			assert upper == approx(es * math.exp(Z95 * se))
			assert note == 'degenerate case: CI calculation used pseudocount'
			continue
		res = odds_ratio([[a, b], [c, d]], kind='sample')
		interval = res.confidence_interval(0.95)
		assert (es, lower, upper) == (approx(res.statistic), approx(interval.low), approx(interval.high)), feature
		compared += 1
	assert compared > 100


def test_ratio_of_proportions_ci_matches_scipy(tables):
	from stamp.plugins.samples.confidenceIntervalMethods.RatioProportions import RatioProportions
	from stamp.plugins.samples.effectSizeFilters.RatioProportions import RatioProportions as RatioFilter
	ci, esFilter = RatioProportions(PREFS), RatioFilter(PREFS)
	compared = 0
	for feature, s1, s2, t1, t2 in tables:
		lower, upper, es, note = ci.run(s1, s2, t1, t2, 0.95)
		if s1 == 0 or s2 == 0:
			# CI adds the pseudocount to counts and twice to totals; the filter adds it once to both
			assert note == 'degenerate case: CI calculation used pseudocount'
			assert esFilter.run(s1, s2, t1, t2) == approx(((s1 + .5) / (t1 + .5)) / ((s2 + .5) / (t2 + .5)))
			continue
		assert esFilter.run(s1, s2, t1, t2) == approx(es)
		res = relative_risk(int(s1), int(t1), int(s2), int(t2))
		interval = res.confidence_interval(0.95)
		assert (es, lower, upper) == (approx(res.relative_risk), approx(interval.low), approx(interval.high)), feature
		compared += 1
	assert compared > 100


@pytest.mark.parametrize('coverage', [0.90, 0.95, 0.98, 0.99, 0.80])
def test_asymptotic_ci_is_wald_interval(tables, coverage):
	"""Wald interval for p1 - p2 in percent; -CC adds (1/n1 + 1/n2)/2 to the standard error."""
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptotic import DiffBetweenPropAsymptotic
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptoticCC import DiffBetweenPropAsymptoticCC
	from stamp.plugins.samples.effectSizeFilters.DiffBetweenProp import DiffBetweenProp
	wald, waldCC, esFilter = DiffBetweenPropAsymptotic(PREFS), DiffBetweenPropAsymptoticCC(PREFS), DiffBetweenProp(PREFS)
	z = stats.norm.ppf(0.5 + coverage / 2)
	for feature, s1, s2, t1, t2 in tables:
		p1, p2 = s1 / t1, s2 / t2
		se = math.sqrt(p1 * (1 - p1) / t1 + p2 * (1 - p2) / t2)
		cc = (1 / t1 + 1 / t2) / 2
		lower, upper, es, _ = wald.run(s1, s2, t1, t2, coverage)
		assert es == approx(100 * (p1 - p2))
		assert esFilter.run(s1, s2, t1, t2) == approx(es)
		assert lower == pytest.approx(100 * (p1 - p2 - z * se), rel=REL, abs=1e-12)
		assert upper == pytest.approx(100 * (p1 - p2 + z * se), rel=REL, abs=1e-12)
		lower, upper, es, _ = waldCC.run(s1, s2, t1, t2, coverage)
		assert lower == pytest.approx(100 * (p1 - p2 - z * (se + cc)), rel=REL, abs=1e-12)
		assert upper == pytest.approx(100 * (p1 - p2 + z * (se + cc)), rel=REL, abs=1e-12)


def test_newcombe_wilson_approximates_exact_newcombe(tables):
	"""STAMP finds the Wilson score roots on a grid of step 1/max(n, 1000) with linear
	interpolation, so it matches Newcombe's hybrid score interval (method 10, built here
	from scipy's exact Wilson bounds) only to grid precision."""
	from stamp.plugins.samples.confidenceIntervalMethods.NewcombeWilson import NewcombeWilson
	nw = NewcombeWilson(PREFS)
	for feature, s1, s2, t1, t2 in tables:
		lower, upper, es, _ = nw.run(s1, s2, t1, t2, 0.95)
		w1 = stats.binomtest(int(s1), int(t1)).proportion_ci(0.95, method='wilson')
		w2 = stats.binomtest(int(s2), int(t2)).proportion_ci(0.95, method='wilson')
		p1, p2 = s1 / t1, s2 / t2
		exactLower = (p1 - p2) - math.sqrt((p1 - w1.low) ** 2 + (w2.high - p2) ** 2)
		exactUpper = (p1 - p2) + math.sqrt((w1.high - p1) ** 2 + (p2 - w2.low) ** 2)
		assert es == approx(100 * (p1 - p2))
		assert lower == pytest.approx(100 * exactLower, abs=0.02), feature
		assert upper == pytest.approx(100 * exactUpper, abs=0.02), feature
	# pinned port output (verified above to grid precision against the exact interval)
	_, s1, s2, t1, t2 = _by_name(tables, 'Flagellum')
	assert nw.run(s1, s2, t1, t2, 0.95)[:3] == tuple(approx(x) for x in NEWCOMBE_FLAGELLUM)


# ---------------------------------------------------------------- pipeline and filters

def test_sample_stats_pipeline_and_filters(profile, tables):
	from stamp.metagenomics.stats.SampleStatsTests import SampleStatsTests
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptotic import DiffBetweenPropAsymptotic
	from stamp.plugins.samples.effectSizeFilters.DiffBetweenProp import DiffBetweenProp
	from stamp.plugins.samples.effectSizeFilters.RatioProportions import RatioProportions
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection

	tests = SampleStatsTests(PREFS)
	tests.run(Fishers(PREFS), 'Two-sided', DiffBetweenPropAsymptotic(PREFS), 0.95, profile)
	res = tests.results
	res.performMultCompCorrection(NoCorrection(PREFS))
	assert len(res.data) == 247
	pValues = res.getColumn('pValues', False)
	assert pValues == sorted(pValues)

	# independent expectations from scipy and the raw counts
	exact = {}
	for feature, s1, s2, t1, t2 in tables:
		a, b, c, d = cells(s1, s2, t1, t2)
		exact[feature] = (stats.fisher_exact([[a, b], [c, d]]).pvalue, 100 * abs(s1 / t1 - s2 / t2),
			max((s1 / t1) / (s2 / t2) if s2 else 0, (s2 / t2) / (s1 / t1) if s1 else 0))
	for row in res.data:
		assert row[res.dataHeadings['pValues']] == approx(exact[row[0]][0])
		assert row[res.dataHeadings['RelFreq1']] == approx(100 * row[1] / row[3])

	res.selectAllFeautres()
	res.filterFeatures(0.05, None, 0, 0, None, 0, 0, None, 0, None, None, 0)
	expected = {f for f, v in exact.items() if v[0] <= 0.05}
	assert set(res.getActiveFeatures()) == expected and len(expected) == 87

	res.filterFeatures(0.05, None, 0, 0, None, 0, 0, DiffBetweenProp(PREFS), 0.1, None, None, 0)
	expected = {f for f, v in exact.items() if v[0] <= 0.05 and v[1] >= 0.1}
	assert set(res.getActiveFeatures()) == expected and 0 < len(expected) < 87

	# upstream labels are swapped: 'OR' keeps features passing both filters, 'AND' either
	res.filterFeatures(None, None, 0, 0, None, 0, 0, DiffBetweenProp(PREFS), 0.1, 'OR', RatioProportions(PREFS), 3.0)
	both = set(res.getActiveFeatures())
	res.filterFeatures(None, None, 0, 0, None, 0, 0, DiffBetweenProp(PREFS), 0.1, 'AND', RatioProportions(PREFS), 3.0)
	either = set(res.getActiveFeatures())
	assert both < either

	res.filterFeatures(None, 'minimum', 10, 0, None, 0, 0, None, 0, None, None, 0)
	assert set(res.getActiveFeatures()) == {f for f, s1, s2, t1, t2 in tables if min(s1, s2) >= 10}


# Values produced by this port, filled in after verification (see the tests above).
PERMUTATION_SEED0 = [(0.019, 0.019), (0.037, 0.087), (0.121, 0.251), (0.292, 0.551)]
BOOTSTRAP_SEED0 = [(0.008, 0.008), (0.033, 0.076), (0.1, 0.208), (0.228, 0.496)]
NEWCOMBE_FLAGELLUM = (0.707998210867481, 1.3681906581964793, 1.0921313489173454)
