"""Two-sample mode: statistical tests, confidence intervals and effect-size filters against the
exact / mpmath oracle. Inputs: every feature of four real two-sample profiles (Iron mine, Skirball
400-feature subset at Phylum and Phylum->Class, full Skirball phylum sums, soil classes) plus
oracle.EDGE_TABLES."""
import importlib
import math

import mpmath as mp
import pytest

import oracle
from oracle import Checks, EDGE_TABLES, PREFS, Q

EPS = 2.0 ** -52
COVERAGES = [0.8, 0.9, 0.95, 0.98, 0.99, 0.999]


def plugin(kind, name):
	mod = importlib.import_module('stamp.plugins.samples.%s.%s' % (kind, name))
	return getattr(mod, name)(PREFS)


@pytest.fixture(scope='module')
def tables(sample_tables):
	return list(sample_tables) + [('edge: ' + e[0],) + tuple(e[1:]) for e in EDGE_TABLES]


def lgamma_tol(*tables_args):
	"""Tolerance for STAMP's exact tests, which evaluate each hypergeometric probability as
	exp(gammaln(.) + ... - gammaln(N + 1) ...) in double precision. Each gammaln of an argument of
	size n carries an absolute error of about eps * n ln n, so the probabilities (and their sums)
	carry a relative error of that order; for N <= 50 this is below 1e-12. Bound used: 8 eps
	lgamma(N + 1) (measured worst case in units of eps lgamma(N + 1): see 'Fisher error / (eps
	lgamma(N+1))' in the summary table)."""
	N = int(round(tables_args[2] + tables_args[3]))
	return max(oracle.REL, 8 * EPS * math.lgamma(N + 1))


def is_exact_feasible(s1, s2, t1, t2):
	return s1 + s2 <= 100000		# STAMP loops over every table with these margins


# ------------------------------------------------------------------ statistical tests

def test_fishers_exact(tables):
	fishers = plugin('statisticalTests', 'Fishers')
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		if not is_exact_feasible(s1, s2, t1, t2):
			continue
		one, two, note = fishers.hypothesisTest(s1, s2, t1, t2)
		o1, o2 = oracle.fisher(s1, s2, t1, t2)
		tol = lgamma_tol(s1, s2, t1, t2)
		ck('samples/Fisher one-sided [lgamma tol]', one, o1, rel=tol, ctx=(label, s1, s2, t1, t2))
		unit = EPS * max(math.lgamma(t1 + t2 + 1), 1.0)
		for got, exp in ((one, o1), (two, o2)):
			if exp >= oracle.SIG:
				oracle.note_error('samples/Fisher error / (eps lgamma(N+1))', abs(got - float(exp)) / float(exp) / unit)
		ck('samples/Fisher two-sided [lgamma tol]', two, o2, rel=tol, ctx=(label, s1, s2, t1, t2))
		assert note == ''
	ck.done()


def test_fishers_grid():
	"""Exhaustive small tables (totals 1..24). One-sided everywhere; two-sided wherever no other
	table is exactly as likely as the observed one. Tables with such exact ties are the defect
	asserted (strict xfail) in test_acc_defects.py::test_fisher_two_sided_includes_tied_tables."""
	fishers = plugin('statisticalTests', 'Fishers')
	ck = Checks()
	for t1 in range(1, 25):
		for t2 in range(t1, 25, 3):
			for s1 in range(t1 + 1):
				for s2 in range(t2 + 1):
					if s1 + s2 == 0:
						continue
					one, two, _ = fishers.hypothesisTest(s1, s2, t1, t2)
					o1, o2 = oracle.fisher(s1, s2, t1, t2)
					ck('samples/Fisher grid one-sided', one, o1, ctx=(s1, s2, t1, t2))
					if oracle.fisher_tied_tables(s1, s2, t1, t2) == 0:
						ck('samples/Fisher grid two-sided (no exact ties)', two, o2, ctx=(s1, s2, t1, t2))
	ck.done()


def test_hypergeometric(tables):
	hyper = plugin('statisticalTests', 'Hypergeometric')
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		if not is_exact_feasible(s1, s2, t1, t2):
			continue
		one, two, note = hyper.hypothesisTest(s1, s2, t1, t2)
		o1, o2 = oracle.hypergeometric(s1, s2, t1, t2)
		tol = lgamma_tol(s1, s2, t1, t2)
		# the far tail is formed as 1 - CDF + PMF, so the CDF's lgamma error (relative to the CDF,
		# which is ~1) becomes an absolute error of the tail: abs_tol = the same lgamma bound
		# (measured: 7.5e-11 absolute at N = 15540, where the bound is 2.4e-10)
		ck('samples/Hypergeometric one-sided [lgamma tol, rel+abs]', one, o1, rel=tol, abs_tol=tol, ctx=(label, s1, s2, t1, t2))
		ck('samples/Hypergeometric two-sided [lgamma tol, rel+abs]', two, o2, rel=tol, abs_tol=2 * tol, ctx=(label, s1, s2, t1, t2))
	ck.done()


def _chi_degenerate(s1, s2, t1, t2):
	return (s1 == 0 and s2 == 0) or (s1 == t1 or s2 == t2)


@pytest.mark.parametrize('name,yates', [('ChiSquare', False), ('ChiSquareYates', True)])
def test_chi_square(tables, name, yates):
	test = plugin('statisticalTests', name)
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		one, two, note = test.hypothesisTest(s1, s2, t1, t2)
		assert one == math.inf
		if _chi_degenerate(s1, s2, t1, t2):
			# upstream definition (see test_acc_questionable.py for the statistical problem)
			assert (two, note) == (1.0, 'degenerate case: suspect p-value')
			continue
		ck('samples/%s two-sided' % name, two, oracle.chi_square(s1, s2, t1, t2, yates), ctx=(label, s1, s2, t1, t2))
	ck.done()


@pytest.mark.parametrize('name,yates', [('GTest', False), ('GTestYates', True)])
def test_g_test(tables, name, yates):
	test = plugin('statisticalTests', name)
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		one, two, note = test.hypothesisTest(s1, s2, t1, t2)
		assert one == math.inf
		# error-propagation band, see oracle.g_test (measured worst case 2.4e-9 absolute near p = 1)
		p, lo, hi = oracle.g_test(s1, s2, t1, t2, yates, band=True)
		ck.band('samples/%s two-sided [rounding band]' % name, two, p, lo, hi, ctx=(label, s1, s2, t1, t2))
	ck.done()


def test_g_test_yates_or_fisher(tables):
	test = plugin('statisticalTests', 'GTestFisher')
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		a, b, c, d = s1, s2, t1 - s1, t2 - s2
		if min(a, b, c, d) < 20:
			if not is_exact_feasible(s1, s2, t1, t2):
				continue
			one, two, _ = test.hypothesisTest(s1, s2, t1, t2)
			o1, o2 = oracle.fisher(s1, s2, t1, t2)
			tol = lgamma_tol(s1, s2, t1, t2)
			ck('samples/GTestFisher (Fisher branch) [lgamma tol]', one, o1, rel=tol, ctx=(label, s1, s2, t1, t2))
			ck('samples/GTestFisher (Fisher branch) [lgamma tol]', two, o2, rel=tol, ctx=(label, s1, s2, t1, t2))
		else:
			one, two, _ = test.hypothesisTest(s1, s2, t1, t2)
			assert one == math.inf
			p, lo, hi = oracle.g_test(s1, s2, t1, t2, True, band=True)
			ck.band('samples/GTestFisher (G-test Yates branch) [rounding band]', two, p, lo, hi, ctx=(label, s1, s2, t1, t2))
	ck.done()


def test_difference_between_proportions(tables):
	test = plugin('statisticalTests', 'DiffBetweenProp')
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		one, two, note = test.hypothesisTest(s1, s2, t1, t2)
		o1, o2 = oracle.diff_between_prop_test(s1, s2, t1, t2)
		ck('samples/DiffBetweenProp one-sided', one, o1, ctx=(label, s1, s2, t1, t2))
		ck('samples/DiffBetweenProp two-sided', two, o2, ctx=(label, s1, s2, t1, t2))
	ck.done()


# ------------------------------------------------------------------ z quantile

def test_z_score_hardcoded_and_erfinv():
	from stamp.metagenomics.stats.distributions.NormalDist import zScore
	for c in COVERAGES + [0.5, 0.6827, 0.9973]:
		oracle.check('NormalDist.zScore', zScore(c), oracle.z_two_sided(c))


# ------------------------------------------------------------------ confidence intervals

def _ci_cases(tables):
	for label, s1, s2, t1, t2 in tables:
		for c in COVERAGES:
			yield label, s1, s2, t1, t2, c


@pytest.mark.parametrize('name,cc', [('DiffBetweenPropAsymptotic', False), ('DiffBetweenPropAsymptoticCC', True)])
def test_ci_difference_asymptotic(tables, name, cc):
	ci = plugin('confidenceIntervalMethods', name)
	ck = Checks()
	for label, s1, s2, t1, t2, c in _ci_cases(tables):
		lo, hi, es, note = ci.run(s1, s2, t1, t2, c)
		olo, ohi, oes = oracle.ci_dp_asymptotic(s1, s2, t1, t2, c, cc=cc)
		ck('samples/CI %s lower' % name, lo, olo, ctx=(label, s1, s2, t1, t2))
		ck('samples/CI %s upper' % name, hi, ohi, ctx=(label, s1, s2, t1, t2))
		ck('samples/CI %s effect' % name, es, oes, ctx=(label, s1, s2, t1, t2))
	ck.done()


def _wilson_root_missed(seq, total):
	"""Upstream scans v = 0, h, ..., (steps - 1) h with h = 1/max(n, 1000); a Wilson upper bound
	above the last scanned point is never bracketed (always the case for p = 1)."""
	h = 1.0 / max(total, 1000)
	last = (int(1.0 / h) - 1) * h
	_, u = oracle.wilson(seq, total, oracle.z_two_sided(0.95))
	return u > last - h


def test_ci_newcombe_wilson(tables):
	"""Upstream finds each Wilson root by scanning a grid of step h = 1/max(n, 1000) and linearly
	interpolating across the sign change of f(v) = z sqrt(v(1-v)/n) - |v - p|. f has a
	square-root singularity at 0, so for rare features (root within a few h of 0) the
	interpolated root is off by a sizeable fraction of h, which is of the order of the root
	itself. Tolerance: 0.3 x the oracle's half-width on each bound (measured worst case 0.24 of
	the half-width, i.e. 0.032 percentage points, for counts 0..2 of 13221; median 6e-4 of the
	half-width). Effect size: 1e-12 (exact arithmetic). Cases where a root lies in the last grid
	step are excluded here and asserted as a defect in test_acc_defects.py."""
	ci = plugin('confidenceIntervalMethods', 'NewcombeWilson')
	ck = Checks()
	for label, s1, s2, t1, t2, c in _ci_cases(tables):
		if t1 == 0 or t2 == 0 or _wilson_root_missed(s1, t1) or _wilson_root_missed(s2, t2):
			continue
		if max(t1, t2) > 200000 and c != 0.95:
			continue		# each call scans max(n, 1000) grid points in Python; one coverage suffices
		lo, hi, es, note = ci.run(s1, s2, t1, t2, c)
		olo, ohi, oes = oracle.ci_newcombe_wilson(s1, s2, t1, t2, c)
		ck('samples/CI NewcombeWilson lower [0.3 half-width]', lo, olo, rel=0, abs_tol=0.3 * float(oes - olo), ctx=(label, s1, s2, t1, t2, c))
		ck('samples/CI NewcombeWilson upper [0.3 half-width]', hi, ohi, rel=0, abs_tol=0.3 * float(ohi - oes), ctx=(label, s1, s2, t1, t2, c))
		ck('samples/CI NewcombeWilson effect', es, oes, ctx=(label, s1, s2, t1, t2, c))
		oracle.note_error('samples/CI NewcombeWilson error / half-width', max(abs(lo - float(olo)) / float(oes - olo), abs(hi - float(ohi)) / float(ohi - oes)))
	ck.done()


def test_ci_odds_ratio(tables):
	ci = plugin('confidenceIntervalMethods', 'OddsRatio')
	ck = Checks()
	for label, s1, s2, t1, t2, c in _ci_cases(tables):
		if t1 == s1 and s2 == 0 and t2 == 0:
			continue
		lo, hi, es, note = ci.run(s1, s2, t1, t2, c)
		olo, ohi, oes = oracle.ci_odds_ratio(s1, s2, t1, t2, c)
		ck('samples/CI OddsRatio lower', lo, olo, ctx=(label, s1, s2, t1, t2))
		ck('samples/CI OddsRatio upper', hi, ohi, ctx=(label, s1, s2, t1, t2))
		ck('samples/CI OddsRatio effect', es, oes, ctx=(label, s1, s2, t1, t2))
	ck.done()


def test_ci_ratio_of_proportions(tables):
	ci = plugin('confidenceIntervalMethods', 'RatioProportions')
	ck = Checks()
	for label, s1, s2, t1, t2, c in _ci_cases(tables):
		lo, hi, es, note = ci.run(s1, s2, t1, t2, c)
		olo, ohi, oes = oracle.ci_ratio_proportions(s1, s2, t1, t2, c)
		ck('samples/CI RatioProportions lower', lo, olo, ctx=(label, s1, s2, t1, t2))
		ck('samples/CI RatioProportions upper', hi, ohi, ctx=(label, s1, s2, t1, t2))
		ck('samples/CI RatioProportions effect', es, oes, ctx=(label, s1, s2, t1, t2))
	ck.done()


# ------------------------------------------------------------------ effect-size filters

def test_effect_size_filters(tables):
	dp = plugin('effectSizeFilters', 'DiffBetweenProp')
	orr = plugin('effectSizeFilters', 'OddsRatio')
	rp = plugin('effectSizeFilters', 'RatioProportions')
	ck = Checks()
	for label, s1, s2, t1, t2 in tables:
		ck('samples/ES DiffBetweenProp', dp.run(s1, s2, t1, t2), oracle.es_diff_between_prop(s1, s2, t1, t2), ctx=(label, s1, s2, t1, t2))
		ck('samples/ES OddsRatio', orr.run(s1, s2, t1, t2), oracle.es_odds_ratio(s1, s2, t1, t2), ctx=(label, s1, s2, t1, t2))
		ck('samples/ES RatioProportions', rp.run(s1, s2, t1, t2), oracle.es_ratio_proportions(s1, s2, t1, t2), ctx=(label, s1, s2, t1, t2))
	ck.done()
