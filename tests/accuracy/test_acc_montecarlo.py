"""Monte Carlo procedures: two-sample Bootstrap and Permutation tests, White's non-parametric
t-test (permutation p-values, bootstrap CIs). Their outputs are random, so they cannot meet
1e-12. What is checked instead, with fixed seeds (the seeds make the run reproducible; the bounds
below hold for any seed except with the stated tiny probability):

  * the exact null distribution of each procedure is computed by the oracle (binomial
    convolution, hypergeometric, full enumeration of group assignments, full enumeration of
    bootstrap resamples) in exact rationals / mpmath;
  * the Monte Carlo estimate must lie within 5 binomial standard deviations of the exact value
    (two-sided normal tail 5.7e-7 per comparison), or for quantiles within the
    Dvoretzky-Kiefer-Wolfowitz band eps = sqrt(ln(2/delta)/(2B)) with delta = 1e-6.

The deterministic parts (degenerate branches, White's effect sizes and its Fisher fallback) are
checked at 1e-12 elsewhere (test_acc_groups.py) or below."""
import itertools
import math
import random
from fractions import Fraction

import mpmath as mp
import numpy
import pytest

import oracle
from oracle import PREFS, Q

# Tables whose null distribution has no pair of distinct outcomes with exactly equal difference
# c1/n1 - c2/n2 on the far side of the observed one (where float rounding decides the comparison);
# a table where it matters is the defect in test_acc_defects.py.
TABLES = [
	(20, 1, 50, 50),
	(11, 11, 30, 60),
	(3, 9, 40, 35),
	(0, 4, 25, 30),
	(7, 7, 20, 20),
]


def sd_bound(p, B):
	return 5 * math.sqrt(max(p * (1 - p), 1.0 / B) / B) + 1.0 / B


@pytest.mark.parametrize('name', ['Bootstrap', 'Permutation'])
def test_two_sample_monte_carlo_converges_to_exact_null(name):
	import importlib
	B = 20000
	mod = importlib.import_module('stamp.plugins.samples.statisticalTests.' + name)
	test = getattr(mod, name)(dict(PREFS, Replicates=B))
	tails = oracle.bootstrap_null_tails if name == 'Bootstrap' else oracle.permutation_null_tails
	for i, (s1, s2, t1, t2) in enumerate(TABLES):
		numpy.random.seed(1000 + i)
		one, two, note = test.hypothesisTest(s1, s2, t1, t2)
		left, right, both = (float(x) for x in tails(s1, s2, t1, t2))
		exp_one = min(left, right)
		err1, err2 = abs(one - exp_one), abs(two - both)
		oracle.note_error('montecarlo/%s one-sided |MC - exact| (B=%d)' % (name, B), err1 / exp_one, err1)
		oracle.note_error('montecarlo/%s two-sided |MC - exact| (B=%d)' % (name, B), err2 / both, err2)
		# min of two estimates deviates from min of the means by at most the larger deviation
		assert err1 <= max(sd_bound(left, B), sd_bound(right, B)), ((s1, s2, t1, t2), one, exp_one)
		assert err2 <= sd_bound(both, B), ((s1, s2, t1, t2), two, both)


@pytest.mark.parametrize('name', ['Bootstrap', 'Permutation'])
def test_two_sample_monte_carlo_degenerate(name):
	import importlib
	mod = importlib.import_module('stamp.plugins.samples.statisticalTests.' + name)
	test = getattr(mod, name)(dict(PREFS, Replicates=100))
	one, two, note = test.hypothesisTest(0, 3, 0, 10)
	assert (one, two) == (1.0, 1.0)


def test_permutation_one_sided_is_fisher_one_sided():
	"""Permutation's null (c1 ~ Hypergeometric(pos, neg, total1)) is Fisher's conditional
	distribution, so its expected one-sided p-value is Fisher's one-sided p-value exactly."""
	for s1, s2, t1, t2 in TABLES:
		left, right, _ = oracle.permutation_null_tails(s1, s2, t1, t2)
		one, _ = oracle.fisher(s1, s2, t1, t2)
		assert abs(min(left, right) - oracle.M(one)) < mp.mpf('1e-40')


# ------------------------------------------------------------------ White's non-parametric t-test

def _white(n1, n2, rows, B, seed):
	"""rows: per feature (counts1, counts2); parents fixed at 1000 per sample."""
	from stamp.plugins.groups.statisticalTests.White import White
	s1 = [list(r[0]) for r in rows]
	s2 = [list(r[1]) for r in rows]
	p1 = [[1000] * n1 for _ in rows]
	p2 = [[1000] * n2 for _ in rows]
	random.seed(seed)
	numpy.random.seed(seed)
	return White(dict(PREFS, Replicates=B)).runAll(s1, s2, p1, p2, '', 0.95, None), s1, s2


def _exact_permutation_tails(props, n1, t_obs_list):
	"""For each feature r (props[r] = pooled sample values) and each threshold T, the exact
	probability over uniformly random group assignments that T*_r > T and |T*_r| > |T|."""
	n = len(props[0])
	subsets = list(itertools.combinations(range(n), n1))
	tstar = []
	for r in range(len(props)):
		vals = []
		for S in subsets:
			rest = [i for i in range(n) if i not in S]
			vals.append(oracle.welch_t([props[r][i] for i in S], [props[r][i] for i in rest]))
		tstar.append(vals)
	eps = mp.mpf('1e-30')
	return subsets, tstar, eps


def test_white_permutation_p_values_large_groups():
	"""n1, n2 >= 8: p = (#{T* > T} + 1)/(B + 1) per feature, T* from B random permutations. The
	exact P(T* > T) is the fraction of all C(17, 8) = 24310 group assignments (each permutation
	of samples induces a uniformly random assignment)."""
	n1, n2, B = 8, 9, 3000
	rows = [
		([12, 15, 9, 20, 14, 11, 17, 13], [8, 6, 11, 9, 7, 10, 5, 9, 8]),
		([3, 5, 2, 4, 6, 3, 4, 5], [4, 3, 5, 6, 2, 4, 5, 3, 4]),
		([30, 28, 35, 31, 29, 33, 27, 32], [40, 38, 45, 41, 39, 36, 44, 42, 37]),
	]
	(one, two, lo, hi, es, notes), s1, s2 = _white(n1, n2, rows, B, 7)
	props = [[Fraction(c, 1000) for c in a + b] for a, b in zip(s1, s2)]
	subsets, tstar, eps = _exact_permutation_tails(props, n1, None)
	for r in range(len(rows)):
		tobs = oracle.welch_t(props[r][:n1], props[r][n1:])
		P1 = Fraction(sum(1 for v in tstar[r] if v > tobs + eps), len(subsets))
		P2 = Fraction(sum(1 for v in tstar[r] if abs(v) > abs(tobs) + eps), len(subsets))
		for got, P, lab in ((one[r], P1, 'one'), (two[r], P2, 'two')):
			exp = (B * float(P) + 1) / (B + 1)
			oracle.note_error("montecarlo/White n>=8 %s-sided |MC - exact| (B=%d)" % (lab, B), abs(got - exp) / exp, abs(got - exp))
			assert abs(got - exp) <= sd_bound(float(P), B), (r, lab, got, exp)


def test_white_pooled_p_values_small_groups():
	"""n1 or n2 < 8: upstream pools the permutation statistics of all 'high-frequency' features
	(group sum >= group size in either group): p_r = #{(i, h): T*_{i,h} > T_r} / (B H). Its
	expectation is mean_h P(T*_h > T_r); each replicate contributes a mean of H indicators, a
	[0, 1] variable with variance <= mu (1 - mu), so the 5-sd bound uses B replicates. Values are
	distinct and n1 != n2, so no two assignments give exactly tied statistics (ties are the
	defect in test_acc_defects.py)."""
	n1, n2, B = 4, 5, 4000
	rows = [
		([12, 15, 9, 20], [8, 6, 11, 10, 7]),
		([3, 5, 2, 4], [7, 1, 6, 8, 9]),
		([30, 28, 35, 31], [40, 38, 45, 41, 36]),
	]
	(one, two, lo, hi, es, notes), s1, s2 = _white(n1, n2, rows, B, 11)
	props = [[Fraction(c, 1000) for c in a + b] for a, b in zip(s1, s2)]
	subsets, tstar, eps = _exact_permutation_tails(props, n1, None)
	H = len(rows)
	for r in range(H):
		tobs = oracle.welch_t(props[r][:n1], props[r][n1:])
		mu1 = sum(Fraction(sum(1 for v in tstar[h] if v > tobs + eps), len(subsets)) for h in range(H)) / H
		mu2 = sum(Fraction(sum(1 for v in tstar[h] if abs(v) > abs(tobs) + eps), len(subsets)) for h in range(H)) / H
		for got, mu, lab in ((one[r], mu1, 'one'), (two[r], mu2, 'two')):
			oracle.note_error("montecarlo/White n<8 pooled %s-sided |MC - exact| (B=%d)" % (lab, B), abs(got - float(mu)) / max(float(mu), 1e-300), abs(got - float(mu)))
			assert abs(got - float(mu)) <= sd_bound(float(mu), B), (r, lab, got, float(mu))


def test_white_bootstrap_ci_quantiles():
	"""White's CI is upstream's percentile bootstrap of the difference of mean proportions
	(Bootstrap.bootstrapDiffOfMeanProp): lower = sorted[floor(0.025 B)], upper =
	sorted[ceil(0.975 B)]. With n1 = n2 = 3 the exact bootstrap distribution has 3^3 x 3^3
	equally likely resamples. The chosen order statistics must sit at the 0.025 / 0.975 quantiles
	of the exact distribution up to the DKW band (delta = 1e-6) plus one step 1/B."""
	n1, n2, B = 3, 3, 20000
	rows = [
		([12, 15, 9], [8, 6, 11]),
		([30, 28, 35], [40, 38, 45]),
	]
	(one, two, lo, hi, es, notes), s1, s2 = _white(n1, n2, rows, B, 5)
	eps = math.sqrt(math.log(2 / 1e-6) / (2 * B)) + 1.0 / B
	for r in range(len(rows)):
		g1 = [Fraction(c, 1000) for c in s1[r]]
		g2 = [Fraction(c, 1000) for c in s2[r]]
		m1 = [sum(c) / 3 for c in itertools.product(g1, repeat=3)]
		m2 = [sum(c) / 3 for c in itertools.product(g2, repeat=3)]
		dist = sorted(a - b for a in m1 for b in m2)
		N = len(dist)

		def F(x, strict=False):
			x = Q(x) / 100
			# the port's value is a float; compare with a 1e-12 relative slack around atoms
			slack = abs(x) * Fraction(1, 10 ** 12) + Fraction(1, 10 ** 15)
			if strict:
				return sum(1 for d in dist if d < x - slack) / N
			return sum(1 for d in dist if d <= x + slack) / N

		for v, q in ((lo[r], 0.025), (hi[r], 0.975)):
			lower_ok = F(v) >= q - eps
			upper_ok = F(v, strict=True) <= q + eps
			oracle.note_error('montecarlo/White bootstrap CI |F(exact) - q| (B=%d)' % B, abs(F(v) - q) / q, abs(F(v) - q))
			assert lower_ok and upper_ok, (r, q, v, F(v), F(v, True))
