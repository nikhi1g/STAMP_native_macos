"""Two-group mode: t-test, Welch's t-test (p-values and CI endpoints with the exact Student-t
quantile), the deterministic parts of White's non-parametric test, and the effect-size filters.
Inputs: every feature of Skirball (burned vs unburned, full phylum sums and the 400-feature subset
at Phylum -> Class), soil (2 undisturbed vs 4 disturbed samples) and Enterotypes 1 vs 2, plus
hand-made edge cases."""
import importlib

import pytest
from scipy.stats import t as scipy_t

import oracle
from oracle import Checks, PREFS, Q

COVERAGES = [0.9, 0.95, 0.99]

# (label, counts1, counts2, parents1, parents2)
EDGE_GROUPS = [
	('n = 2 per group', [3, 5], [10, 1], [100, 120], [90, 110]),
	('equal groups', [4, 6, 5], [4, 6, 5], [100, 100, 100], [100, 100, 100]),
	('one group zero variance', [5, 5, 5], [1, 9, 4], [100, 100, 100], [100, 100, 100]),
	('zero counts in group 1', [0, 0, 0], [3, 1, 7], [50, 60, 70], [50, 60, 70]),
	('tiny counts', [1, 2, 1, 0], [2, 1, 2, 2], [10, 12, 9, 11], [10, 10, 13, 12]),
	('huge counts', [1500000, 1499000, 1501234], [1400000, 1405000, 1399999], [3000000, 3000001, 2999999], [3100000, 3100002, 3099998]),
	('unequal sizes', [10, 12, 9, 14, 11, 13, 8], [20, 25], [1000] * 7, [1000, 1000]),
	('parent zero in one sample', [0, 4, 6], [3, 2, 9], [0, 50, 60], [40, 50, 60]),
]


def plugin(kind, name):
	mod = importlib.import_module('stamp.plugins.groups.%s.%s' % (kind, name))
	return getattr(mod, name)(PREFS)


@pytest.fixture(scope='module')
def inputs(group_inputs):
	return list(group_inputs) + [('edge: ' + e[0],) + tuple(e[1:]) for e in EDGE_GROUPS]


def _degenerate(c1, c2, p1, p2):
	g1, g2 = oracle.proportions(c1, p1), oracle.proportions(c2, p2)
	if len(g1) < 2 or len(g2) < 2:
		return True
	return oracle.mean_var(g1)[1] == 0 and oracle.mean_var(g2)[1] == 0


@pytest.mark.parametrize('name,welch', [('Ttest', False), ('Welch', True)])
def test_t_tests(inputs, name, welch):
	"""p-values from the regularized incomplete beta and CI endpoints from the exact Student-t
	quantile (Newton in mpmath; scipy's value is only the starting point). Both-variances-zero
	cases are upstream's degenerate branches, asserted in test_acc_upstream_behaviour.py."""
	test = plugin('statisticalTests', name)
	ck = Checks()
	n = 0
	for label, c1, c2, p1, p2 in inputs:
		if _degenerate(c1, c2, p1, p2):
			continue
		for c in COVERAGES:
			one, two, lo, hi, es, note = test.run(c1, c2, p1, p2, test.confIntervMethods[0], c)
			# start Newton near the answer; any start converges to the same mpmath root
			g1, g2 = oracle.proportions(c1, p1), oracle.proportions(c2, p2)
			start = scipy_t.isf((1 - c) / 2, max(len(g1) + len(g2) - 2, 1))
			o = oracle.t_test(c1, c2, p1, p2, c, welch, start=start)
			ctx = (label, c)
			ck('groups/%s one-sided' % name, one, o[0], ctx=ctx)
			ck('groups/%s two-sided' % name, two, o[1], ctx=ctx)
			ck('groups/%s CI lower' % name, lo, o[2], ctx=ctx)
			ck('groups/%s CI upper' % name, hi, o[3], ctx=ctx)
			ck('groups/%s effect' % name, es, o[4], ctx=ctx)
			n += 1
	assert n > 300
	ck.done()


def test_student_t_quantile_used_for_ci():
	"""The CI half-width divided by the standard error is exactly the Student-t quantile; checked
	directly for integer and fractional degrees of freedom (Welch) and several coverages."""
	from scipy.stats.distributions import t
	ck = Checks()
	for dof in [1, 1.5, 2, 2.7183, 3, 4.25, 5, 7.9, 10, 17.3, 30, 63.5, 120, 1000, 1e5]:
		for c in COVERAGES + [0.8, 0.98, 0.999]:
			ck('groups/Student-t quantile t.isf((1-c)/2, dof)', t.isf(0.5 * (1.0 - c), dof),
				oracle.t_isf((1 - oracle.M(c)) / 2, dof, start=t.isf(0.5 * (1.0 - c), dof)), ctx=(dof, c))
	ck.done()


def test_effect_size_filters(group_profiles):
	"""Called as filterFeatures calls them: on getFeatureProportions (percent per sample)."""
	dp = plugin('effectSizeFilters', 'DiffBetweenProp')
	rp = plugin('effectSizeFilters', 'RatioProportions')
	ck = Checks()
	for name, gp in group_profiles:
		for f in gp.getFeatures():
			a, b = gp.getFeatureProportions(f)
			for x, y in [(a, b), (b, a)]:
				ck('groups/ES DiffBetweenProp', dp.run(x, y), oracle.es_group_diff(x, y), ctx=(name, f))
				if sum(x) + sum(y) > 0:		# all-zero features: see test_acc_defects.py
					ck('groups/ES RatioProportions', rp.run(x, y), oracle.es_group_ratio(x, y), ctx=(name, f))
	ck.done()


def _white_inputs(gp):
	features = gp.getFeatures()
	s1, s2 = [], []
	p1, p2 = [], []
	for f in features:
		a, b = gp.getFeatureCounts(f)
		pa, pb = gp.getParentFeatureCounts(f)
		s1.append(a)
		s2.append(b)
		p1.append(pa)
		p2.append(pb)
	return features, s1, s2, p1, p2


def test_white_deterministic_parts(group_profiles):
	"""White's test is Monte Carlo (permutation p-values, bootstrap CIs; see
	test_acc_montecarlo.py). Deterministic and checked here at 1e-12: the effect size (difference
	of mean proportions, %) of every feature, and the complete result of the low-count branch
	(both group sums below the group sizes), which upstream replaces by Fisher's exact test on
	the pooled counts and the DP asymptotic-CC interval."""
	import random
	import numpy
	from stamp.plugins.groups.statisticalTests.White import White
	white = White(dict(PREFS, Replicates=50))
	ck = Checks()
	checked_low = 0
	for name, gp in group_profiles:
		features, s1, s2, p1, p2 = _white_inputs(gp)
		if any(0 in row for row in p1 + p2):
			continue		# parent count of zero: upstream divides by it (see test_acc_defects.py)
		random.seed(1)
		numpy.random.seed(1)
		one, two, lo, hi, es, notes = white.runAll(s1, s2, p1, p2, '', 0.95, None)
		n1, n2 = len(s1[0]), len(s2[0])
		for r, f in enumerate(features):
			if sum(s1[r]) < n1 and sum(s2[r]) < n2:
				checked_low += 1
				a, b, ta, tb = sum(s1[r]), sum(s2[r]), sum(p1[r]), sum(p2[r])
				o1, o2 = oracle.fisher(a, b, ta, tb)
				tol = max(oracle.REL, 8 * 2.0 ** -52 * __import__('math').lgamma(ta + tb + 1))		# see test_acc_samples.lgamma_tol
				ck("groups/White low-count branch: Fisher [lgamma tol]", one[r], o1, rel=tol, ctx=(name, f))
				ck("groups/White low-count branch: Fisher [lgamma tol]", two[r], o2, rel=tol, ctx=(name, f))
				olo, ohi, oes = oracle.ci_dp_asymptotic(a, b, ta, tb, 0.95, cc=True)
				ck('groups/White low-count branch: DP-CC CI', lo[r], olo, ctx=(name, f))
				ck('groups/White low-count branch: DP-CC CI', hi[r], ohi, ctx=(name, f))
				ck('groups/White low-count branch: effect', es[r], oes, ctx=(name, f))
				assert notes[r] == "heuristic: statistics calculated with Fisher's test"
			else:
				ck('groups/White effect size', es[r], oracle.es_group_diff(oracle.proportions(s1[r], p1[r]), oracle.proportions(s2[r], p2[r])) * 100, ctx=(name, f))
	assert checked_low > 0
	ck.done()
