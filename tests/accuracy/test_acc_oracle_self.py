"""The oracle checked against closed forms and independent formulations, so that the accuracy
suite does not rest on unverified reference code. No STAMP code is involved here."""
import itertools
import math
from fractions import Fraction

import mpmath as mp
import pytest

import oracle

TIGHT = mp.mpf('1e-40')


def close(a, b, tol=TIGHT):
	return abs(a - b) <= tol * max(abs(a), abs(b), mp.mpf(1e-300))


def test_t_distribution_closed_forms():
	for x in [-30, -2.5, -0.3, 0, 0.7, 4, 50]:
		x = mp.mpf(x)
		assert close(oracle.t_cdf(x, 1), mp.mpf(1) / 2 + mp.atan(x) / mp.pi)						# Cauchy
		assert close(oracle.t_cdf(x, 2), mp.mpf(1) / 2 + x / (2 * mp.sqrt(2 + x * x)))			# nu = 2
	for nu in [1, 2, 3.5, 10, 77.7]:
		for p in ['0.1', '0.025', '0.0005']:
			x = oracle.t_isf(mp.mpf(p), nu)
			assert close(oracle.t_sf(x, nu), mp.mpf(p))
	# Newton converges to the same root from a poor start
	assert close(oracle.t_isf(mp.mpf('0.025'), 7, start=40), oracle.t_isf(mp.mpf('0.025'), 7))


def test_chi2_and_f_closed_forms():
	for x in [0.01, 1, 3.84, 30]:
		x = mp.mpf(x)
		assert close(oracle.chi2_sf(x, 1), mp.erfc(mp.sqrt(x / 2)))
		assert close(oracle.chi2_sf(x, 2), mp.exp(-x / 2))
		for nu in [3, 12.5]:
			assert close(oracle.f_sf(x, 1, nu), 2 * oracle.t_sf(mp.sqrt(x), nu))		# F(1, nu) = T^2
	for d1, d2 in [(2, 6), (4, 29), (1, 3)]:
		for p in ['0.95', '0.99']:
			x = oracle.f_ppf(mp.mpf(p), d1, d2)
			assert close(1 - oracle.f_sf(x, d1, d2), mp.mpf(p))


def test_z_two_sided():
	for c in ['0.5', '0.9', '0.95', '0.999']:
		z = oracle.z_two_sided(mp.mpf(c))
		assert close(mp.ncdf(z) - mp.ncdf(-z), mp.mpf(c))


def test_studentized_range_k2_identity_and_convergence():
	"""k = 2: Q = sqrt(2)|T|, so P(Q > q) = 2 P(T > q/sqrt 2). Then a finer quadrature rule
	(degree 5, 10 panels) for k = 10 and k = 29 at small and moderate df. Both to 1e-11 relative
	(worst measured 2.1e-12, at non-integer nu = 4.5 where s^(nu - 1) is not polynomial), plus
	1e-18 absolute: 1 - W is formed at 20 digits, so tails below ~1e-8 carry ~1e-19 absolute error."""
	for nu in [2, 4.5, 10, 200]:
		for q in [1.0, 3.5, 40.0]:
			a = oracle.ptukey_sf(q, 2, nu)
			b = 2 * oracle.t_sf(mp.mpf(q) / mp.sqrt(2), nu)
			assert abs(a - b) <= mp.mpf('1e-11') * b + mp.mpf('1e-18'), (nu, q, a, b)		# far tail: absolute ~1e-19
	for k, nu, q in [(10, 7.5, 6.0), (29, 3, 20.0), (3, 200, 3.4)]:
		a = oracle.ptukey_sf(q, k, nu)
		b = oracle.ptukey_sf(q, k, nu, degree=5, panels=10, dps=25)
		assert abs(a - b) <= mp.mpf('1e-11') * b, (k, nu, q, a, b)


def test_fisher_walk_matches_exact_enumeration():
	"""oracle.fisher (mpmath walk with exact tie decisions) against brute-force exact integers."""
	for t1 in range(1, 13):
		for t2 in range(1, 13):
			for s1 in range(t1 + 1):
				for s2 in range(t2 + 1):
					if s1 + s2 == 0:
						continue
					w, tot = oracle.hyper_weights(s1, s2, t1, t2)
					wo = w[s1]
					one = Fraction(min(sum(v for a, v in w.items() if a <= s1), sum(v for a, v in w.items() if a >= s1)), tot)
					two = Fraction(sum(v for v in w.values() if v <= wo), tot)
					o1, o2 = oracle.fisher(s1, s2, t1, t2)
					assert close(o1, oracle.M(one), mp.mpf('1e-35')) and close(o2, oracle.M(two), mp.mpf('1e-35')), (s1, s2, t1, t2)


def test_hyper_weights_sum_to_binomial():
	w, tot = oracle.hyper_weights(37, 51, 400, 650)
	assert sum(w.values()) == tot		# Vandermonde


def test_wilson_bounds_are_roots_of_score_equation():
	z = oracle.z_two_sided(mp.mpf('0.95'))
	for x, n in [(0, 10), (1, 13221), (7, 20), (10, 10), (999, 1000)]:
		p = mp.mpf(x) / n
		for v in oracle.wilson(x, n, z):
			assert abs(z * mp.sqrt(max(v * (1 - v), 0) / n) - abs(v - p)) < mp.mpf('1e-40')


def test_kruskal_wallis_against_direct_rank_anova():
	"""H with tie correction equals (N - 1) sum n_i (Rbar_i - Rbar)^2 / sum (r - Rbar)^2 computed on
	mid-ranks directly (an independent formulation that needs no correction term)."""
	data = [[1.0, 1.0, 2.0, 2.0, 3.0], [2.0, 2.0, 3.0, 3.0, 3.0], [1.0, 3.0, 3.0, 4.0, 4.0]]
	_, H = oracle.kruskal_wallis(data)
	pooled = sorted(v for g in data for v in g)
	rank = {v: Fraction(sum(i + 1 for i, u in enumerate(pooled) if u == v), pooled.count(v)) for v in set(pooled)}
	N = len(pooled)
	Rbar = Fraction(N + 1, 2)
	num = sum(len(g) * (sum(rank[v] for v in g) / len(g) - Rbar) ** 2 for g in data)
	den = sum((rank[v] - Rbar) ** 2 for g in data for v in g)
	assert H == (N - 1) * num / den


def test_anova_two_groups_is_pooled_t_squared():
	a, b = [1.5, 2.25, 3.0, 2.0], [2.5, 3.75, 4.0]
	p_anova = oracle.anova([a, b])
	o = oracle.t_test(a, b, [1] * 4, [1] * 3, 0.95, welch=False)
	assert close(p_anova, o[1], mp.mpf('1e-35'))


def test_bh_and_storey_reference_forms():
	p = [0.01, 0.04, 0.03, 0.2]
	assert oracle.benjamini_hochberg_stepup(p) == [Fraction(0.01) * 4, Fraction(0.04) * 4 / 3, Fraction(0.04) * 4 / 3, Fraction(0.2)]
	# Storey with pi0 = 1 is the step-up BH
	assert oracle.storey_qvalues(p, 1) == oracle.benjamini_hochberg_stepup(p)
