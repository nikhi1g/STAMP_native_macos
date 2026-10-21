"""Independent ground truth for STAMP's statistics, computed with exact rationals and mpmath.

Nothing here calls scipy or STAMP to produce a reference value. Inputs are taken exactly as the
port receives them (Python ints and binary floats, converted to Fraction without rounding);
every derived quantity is either an exact rational or an mpmath number at DPS decimal digits,
and is rounded to a float only at the very end.

Sections: tolerance bookkeeping, distributions (normal, chi-square, t, F, studentized range),
two-sample tests / CIs / effect sizes, two-group tests, multi-group tests and post-hoc tests,
multiple-comparison corrections, exact null distributions for the Monte Carlo tests, and data
loaders for the real profiles.
"""
import csv
import math
import os
from collections import defaultdict
from fractions import Fraction
from math import comb

import mpmath as mp
from mpmath.calculus.quadrature import GaussLegendre

DPS = 50
mp.mp.dps = DPS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
EXAMPLES = os.path.join(ROOT, 'stamp', 'examples')
SOIL = os.path.join(ROOT, 'tests', 'data', 'soil')


def _find_skirball():
	"""The Skirball demo lives in the sibling project projLab/mimg (read-only). Found by walking up
	from this file (works from the main checkout and from .worktrees/*); STAMP_SKIRBALL_DIR
	overrides."""
	if os.environ.get('STAMP_SKIRBALL_DIR'):
		return os.environ['STAMP_SKIRBALL_DIR']
	d = HERE
	while d != os.path.dirname(d):
		cand = os.path.join(d, 'mimg', 'lib', 'analysis', 'ci2', 'fixtures')
		if os.path.isdir(cand):
			return cand
		d = os.path.dirname(d)
	return None


SKIRBALL = _find_skirball()
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15}
REL, ABS = 1e-12, 1e-12

# ------------------------------------------------------------------ tolerance bookkeeping

# label -> [max relative error, max absolute error, comparisons, tolerance used]. The relative
# error is recorded only where |oracle| >= SIG, so values that both sides round to ~0 (e.g. a
# p-value of 1e-300 that the port returns as 0, which passes on abs_tol) do not swamp the summary.
MEASURED = {}
SIG = 1e-8


def Q(x):
	"""Exact rational of an int, float or Fraction (floats are converted without rounding)."""
	if isinstance(x, Fraction):
		return x
	if hasattr(x, 'item'):		# numpy scalar
		x = x.item()
	return Fraction(x)


def M(x):
	"""mpmath number of an int, float, Fraction or mpf at the working precision."""
	if isinstance(x, Fraction):
		return mp.mpf(x.numerator) / x.denominator
	if hasattr(x, 'item'):
		x = x.item()
	return mp.mpf(x)


def to_float(x):
	if isinstance(x, Fraction):
		return x.numerator / x.denominator		# int / int is correctly rounded in Python
	return float(x)


def check(label, port, oracle, rel=REL, abs_tol=ABS, ctx=''):
	"""Assert math.isclose(port, oracle) and record the measured error under `label`."""
	o = to_float(oracle)
	p = float(port)
	if math.isinf(o) or math.isnan(o):
		assert p == o or (math.isnan(o) and math.isnan(p)), (label, p, o)
		return
	err_abs = abs(p - o)
	err_rel = err_abs / abs(o) if o != 0 else (0.0 if p == 0 else math.inf)
	rec = MEASURED.setdefault(label, [0.0, 0.0, 0, (rel, abs_tol)])
	if abs(o) >= SIG:
		rec[0] = max(rec[0], err_rel)
	rec[1] = max(rec[1], err_abs)
	rec[2] += 1
	rec[3] = (max(rec[3][0], rel), max(rec[3][1], abs_tol))
	assert math.isclose(p, o, rel_tol=rel, abs_tol=abs_tol), \
		'%s %r: port=%r oracle=%r rel.err=%.3g abs.err=%.3g (rel_tol=%g abs_tol=%g)' % (label, ctx, p, o, err_rel, err_abs, rel, abs_tol)


def check_band(label, port, oracle, lo, hi, ctx=''):
	"""Assert lo <= port <= hi (each side widened by REL/ABS), where [lo, hi] is the oracle value
	propagated through a stated bound on the port's own rounding error. Records the error against
	`oracle` and the band's relative half-width as the tolerance used."""
	o, p, lo, hi = to_float(oracle), float(port), to_float(lo), to_float(hi)
	err_abs = abs(p - o)
	err_rel = err_abs / abs(o) if o != 0 else (0.0 if p == 0 else math.inf)
	band = max(hi - o, o - lo) / abs(o) if o != 0 else max(hi - o, o - lo)
	rec = MEASURED.setdefault(label, [0.0, 0.0, 0, (REL, ABS)])
	if abs(o) >= SIG:
		rec[0] = max(rec[0], err_rel)
	rec[1], rec[2] = max(rec[1], err_abs), rec[2] + 1
	rec[3] = (max(rec[3][0], band), rec[3][1])
	slack = lambda x: REL * abs(x) + ABS
	assert lo - slack(lo) <= p <= hi + slack(hi), \
		'%s %r: port=%r oracle=%r outside the error band [%r, %r]' % (label, ctx, p, o, lo, hi)


def note_error(label, err_rel, err_abs=0.0):
	"""Record a measured error that is reported but not asserted at 1e-12 (for the summary)."""
	rec = MEASURED.setdefault(label, [0.0, 0.0, 0, (None, None)])
	rec[0] = max(rec[0], err_rel)
	rec[1] = max(rec[1], err_abs)
	rec[2] += 1


# Hand-made 2x2 inputs: zeros in one or both samples, all-zero features, ties, tiny and huge counts,
# a feature that is 100% of its parent, and proportions so close to 1 that the Wilson root lies in
# the last grid step of upstream's Newcombe-Wilson root scan.
EDGE_TABLES = [
	('zero in sample 1', 0, 5, 100, 120),
	('zero in sample 2', 7, 0, 100, 120),
	('all zero', 0, 0, 100, 120),
	('tiny 1/2', 1, 2, 10, 12),
	('tiny 2/1', 2, 1, 3, 4),
	('tiny 1/1 of 2', 1, 1, 2, 2),
	('tie equal proportions', 3, 3, 50, 50),
	('tie scaled proportions', 3, 6, 50, 100),
	('one sample 100%', 10, 3, 10, 10),
	('both samples 100%', 10, 10, 10, 10),
	('near 100%', 999, 950, 1000, 1000),
	('huge counts', 1500000, 1400000, 3000000, 3100000),
	('huge totals', 123, 177, 2000000, 3000000),
]


class Checks:
	"""Collects every failed comparison of a test so one run reports all of them."""

	def __init__(self):
		self.failures = []

	def __call__(self, label, port, oracle, rel=REL, abs_tol=ABS, ctx=''):
		try:
			check(label, port, oracle, rel, abs_tol, ctx)
		except AssertionError as e:
			self.failures.append(str(e))

	def band(self, label, port, oracle, lo, hi, ctx=''):
		try:
			check_band(label, port, oracle, lo, hi, ctx)
		except AssertionError as e:
			self.failures.append(str(e))

	def done(self):
		assert not self.failures, '%d failed comparisons:\n' % len(self.failures) + '\n'.join(self.failures[:20])


# ------------------------------------------------------------------ distributions

def ncdf(x):
	return mp.ncdf(M(x))


def z_two_sided(coverage):
	"""z with P(|Z| <= z) = coverage."""
	return mp.sqrt(2) * mp.erfinv(M(coverage))


def chi2_sf(x, df):
	x = M(x)
	if x <= 0:
		return mp.mpf(1)
	return mp.gammainc(M(df) / 2, x / 2, mp.inf, regularized=True)


def t_cdf(x, nu):
	x, nu = M(x), M(nu)
	tail = mp.betainc(nu / 2, mp.mpf(1) / 2, 0, nu / (nu + x * x), regularized=True) / 2
	return tail if x < 0 else 1 - tail


def t_sf(x, nu):
	return t_cdf(-M(x), nu)


def t_pdf(x, nu):
	x, nu = M(x), M(nu)
	return mp.exp(mp.loggamma((nu + 1) / 2) - mp.loggamma(nu / 2)) / mp.sqrt(nu * mp.pi) * (1 + x * x / nu) ** (-(nu + 1) / 2)


def t_isf(p, nu, start=None):
	"""x > 0 with P(T > x) = p, by Newton iteration on the regularized incomplete beta. `start`
	only speeds convergence (any positive value works; the result does not depend on it)."""
	p, nu = M(p), M(nu)
	x = M(start) if start else mp.sqrt(2) * mp.erfinv(1 - 2 * p)		# normal start
	for _ in range(200):
		step = (t_sf(x, nu) - p) / t_pdf(x, nu)
		x2 = x + step
		if x2 <= 0:
			x2 = x / 2
		if abs(x2 - x) < mp.mpf(10) ** (-DPS + 5) * abs(x2):
			return x2
		x = x2
	raise RuntimeError('t_isf did not converge')


def f_sf(x, d1, d2):
	x, d1, d2 = M(x), M(d1), M(d2)
	if x <= 0:
		return mp.mpf(1)
	return mp.betainc(d2 / 2, d1 / 2, 0, d2 / (d2 + d1 * x), regularized=True)


def f_pdf(x, d1, d2):
	x, d1, d2 = M(x), M(d1), M(d2)
	return mp.exp((d1 / 2) * mp.log(d1 * x) + (d2 / 2) * mp.log(d2) - ((d1 + d2) / 2) * mp.log(d1 * x + d2)
		- mp.log(x) - mp.log(mp.beta(d1 / 2, d2 / 2)))


def f_ppf(p, d1, d2):
	"""x with P(F <= x) = p (Newton on the incomplete beta, bracketed by bisection)."""
	p = M(p)
	lo, hi = mp.mpf(0), mp.mpf(1)
	while 1 - f_sf(hi, d1, d2) < p:
		hi *= 2
	x = (lo + hi) / 2
	for _ in range(400):
		g = 1 - f_sf(x, d1, d2) - p
		if g > 0:
			hi = x
		else:
			lo = x
		step = g / f_pdf(x, d1, d2)
		x2 = x - step
		if not (lo < x2 < hi):
			x2 = (lo + hi) / 2
		if abs(x2 - x) < mp.mpf(10) ** (-DPS + 5) * abs(x2):
			return x2
		x = x2
	raise RuntimeError('f_ppf did not converge')


# Studentized range. P(Q > q; k, nu) = int_0^inf g_nu(s) [1 - W(q s)] ds with
# W(w) = k int phi(z) [Phi(z) - Phi(z - w)]^(k-1) dz and g_nu the density of sqrt(chi2_nu / nu).
# Both integrals use fixed Gauss-Legendre panels (mpmath nodes at TUKEY_DPS digits). The outer
# panels are cut at the s where q s = 1, 2, 3, 4, 6, 8, 11, 15 so that the transition of W is
# always resolved, including large q at small nu. Accuracy (checked in test_acc_oracle_self.py
# against the exact k = 2 identity and against a finer rule): better than 1e-11 relative (worst
# measured 2.1e-12 at non-integer nu) plus ~1e-19 absolute in the far tail (1 - W at 20 digits);
# far below the table errors (>= 1e-7) it is used to measure.
TUKEY_DPS = 20
_GL = {}


def _gl_panel(a, b, degree):
	key = (degree, mp.mp.prec)
	if key not in _GL:
		_GL[key] = GaussLegendre(mp.mp).calc_nodes(degree, mp.mp.prec)
	a, b = mp.mpf(a), mp.mpf(b)
	h, c = (b - a) / 2, (b + a) / 2
	return [(c + h * x, h * w) for x, w in _GL[key]]


def ptukey_sf(q, k, nu, degree=4, panels=6, dps=TUKEY_DPS):
	"""P(Q > q) for the studentized range of k means with nu degrees of freedom."""
	with mp.workdps(dps):
		q, nu = M(q), M(nu)
		sq2 = mp.sqrt(2)
		inner = []
		for a, b in [(-9, -5), (-5, -2), (-2, 0), (0, 2), (2, 5), (5, 9)]:
			for z, w in _gl_panel(a, b, degree):
				inner.append((z / sq2, w * mp.npdf(z), mp.erfc(-z / sq2) / 2))

		def W(wv):
			wv = wv / sq2
			return k * mp.fsum(wp * (Fz - mp.erfc(wv - zs) / 2) ** (k - 1) for zs, wp, Fz in inner)

		sd = 1 / mp.sqrt(nu)
		lo, hi = max(mp.mpf(0), 1 - 9 * sd), 1 + 9 * sd
		edges = [lo + (hi - lo) * i / panels for i in range(panels + 1)]
		edges = sorted(set(edges + [mp.mpf(c) / q for c in (1, 2, 3, 4, 6, 8, 11, 15) if lo < mp.mpf(c) / q < hi]))
		logc = nu / 2 * mp.log(nu) - mp.loggamma(nu / 2) - (nu / 2 - 1) * mp.log(2)
		total = mp.mpf(0)
		for a, b in zip(edges[:-1], edges[1:]):
			for s, w in _gl_panel(a, b, degree):
				g = mp.exp(logc + (nu - 1) * mp.log(s) - nu * s * s / 2)
				total += w * g * (1 - W(q * s))
		return +total


def qtable_tol_q(df):
	"""Envelope of the relative error in q of upstream's tabulated studentized-range quantiles
	(stamp/data/tukeyQ_*.txt) for df >= 3, measured against this oracle (k = 2 column exactly via
	the t identity, k = 3..29 by quadrature): 5e-4 at df = 4, 7e-6 at df = 6, < 1e-7 from df ~ 30.
	The entries evidently come from an iterative quantile routine whose accuracy degrades at
	small df, most for small alpha and large k. df = 2 is outside the envelope (wrong entries;
	see test_acc_defects.py)."""
	return 10.0 * df ** -4.5 + 1e-7


def qtable_tol_p(df):
	"""Same envelope in exceedance-probability space: P(Q > q_table)/alpha - 1 is at most
	0.4 at df = 3, 0.09 at df = 4, 3e-4 at df = 10, 2e-6 at df = 20 (alpha = 0.001, k = 29)."""
	return 100.0 * df ** -4.5 + 2e-6


def qtukey_isf(alpha, k, nu, start, **kw):
	"""q with P(Q > q) = alpha, by the secant method from `start` (any value within a few %)."""
	alpha = M(alpha)
	with mp.workdps(TUKEY_DPS):
		x0 = mp.mpf(start)
		x1 = x0 * (1 + mp.mpf('1e-4'))
		f0 = ptukey_sf(x0, k, nu, **kw) - alpha
		for _ in range(30):
			f1 = ptukey_sf(x1, k, nu, **kw) - alpha
			x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
			if abs(x2 - x1) < mp.mpf('1e-15') * x2:
				return x2
			x0, f0, x1 = x1, f1, x2
	raise RuntimeError('qtukey did not converge')


# ------------------------------------------------------------------ two-sample statistics

def hyper_weights(s1, s2, t1, t2):
	"""Exact integer weights w(a) = C(r1, a) C(r2, t1 - a) of the 2x2 tables with STAMP's
	margins (row 1 = feature counts s1, s2; column sums t1, t2), and their total C(N, t1)."""
	s1, s2, t1, t2 = int(s1), int(s2), int(t1), int(t2)
	r1 = s1 + s2
	N = t1 + t2
	r2 = N - r1
	lo, hi = max(0, t1 - r2), min(r1, t1)
	w = {}
	A = comb(r1, lo)
	B = comb(r2, t1 - lo)
	for a in range(lo, hi + 1):
		w[a] = A * B
		if a < hi:
			A = A * (r1 - a) // (a + 1)
			B = B * (t1 - a) // (r2 - t1 + a + 1)
	return w, comb(N, t1)


def round_cells(s1, s2, t1, t2):
	"""Upstream Fisher's cell rounding; returns integer (seq1, seq2, total1, total2)."""
	half = Fraction(1, 2)
	a, b = math.floor(Q(s1) + half), math.floor(Q(s2) + half)
	c, d = math.floor(Q(t1) - Q(s1) + half), math.floor(Q(t2) - Q(s2) + half)
	return a, b, a + c, b + d


def _hyper_ratio(a, r1, r2, t1):
	"""Exact P(a + 1) / P(a) for the hypergeometric with these margins."""
	return Fraction((r1 - a) * (t1 - a), (a + 1) * (r2 - t1 + a + 1))


def fisher(s1, s2, t1, t2):
	"""Fisher's exact test: (min one-sided, two-sided by minimum likelihood) as mpf.

	Weights relative to the observed table are built outwards from it with the exact one-step
	ratio, each product rounded to DPS digits (cumulative relative error < steps * 10^-DPS), and
	the walk stops once the weights fall below 10^-(DPS + 10) of the running maximum on the far
	side of the mode (the distribution is unimodal). A table whose relative weight is within
	10^-30 of the observed one is then decided exactly: the product of the exact ratios between
	the two tables is compared with 1 as a Fraction. So ties are included exactly.

	Non-integer counts (relative-abundance profiles) are rounded cell by cell to the nearest
	integer, half up, as upstream does (floor(x + 0.5) of seq1, seq2, total1 - seq1, total2 - seq2)."""
	s1, s2, t1, t2 = round_cells(s1, s2, t1, t2)
	r1 = s1 + s2
	N = t1 + t2
	r2 = N - r1
	lo, hi = max(0, t1 - r2), min(r1, t1)
	mode = (r1 + 1) * (t1 + 1) // (N + 2)
	tiny = mp.mpf(10) ** (-(DPS + 10))
	w = {s1: mp.mpf(1)}
	peak = mp.mpf(1)
	a, cur = s1, mp.mpf(1)
	while a < hi:
		cur = cur * M(_hyper_ratio(a, r1, r2, t1))
		a += 1
		w[a] = cur
		peak = max(peak, cur)
		if a > mode and cur < tiny * peak:
			break
	a, cur = s1, mp.mpf(1)
	while a > lo:
		cur = cur / M(_hyper_ratio(a - 1, r1, r2, t1))
		a -= 1
		w[a] = cur
		peak = max(peak, cur)
		if a < mode and cur < tiny * peak:
			break
	total = mp.fsum(w.values())
	two = mp.mpf(0)
	for a, v in w.items():
		if abs(v - 1) < mp.mpf('1e-30'):
			ratio = Fraction(1)
			for b in range(min(a, s1), max(a, s1)):
				ratio *= _hyper_ratio(b, r1, r2, t1)
			include = (ratio if a > s1 else 1 / ratio) <= 1
		else:
			include = v < 1
		if include:
			two += v
	left = mp.fsum(v for a, v in w.items() if a <= s1)
	right = mp.fsum(v for a, v in w.items() if a >= s1)
	return min(left, right) / total, two / total


def fisher_tied_tables(s1, s2, t1, t2):
	"""Number of other tables with exactly the observed table's probability (exact integers)."""
	w, _ = hyper_weights(s1, s2, t1, t2)
	return sum(1 for a, v in w.items() if v == w[int(s1)] and a != int(s1))


def hypergeometric(s1, s2, t1, t2):
	"""Upstream 'Hypergeometric': one-sided = min(P(X <= a), P(X >= a)), two-sided = 2 x one-sided
	(not capped at 1)."""
	one, _ = fisher(s1, s2, t1, t2)
	return one, 2 * one


def cells(seq1, seq2, total1, total2):
	return Q(seq1), Q(seq2), Q(total1) - Q(seq1), Q(total2) - Q(seq2)


def chi_square(seq1, seq2, total1, total2, yates=False):
	"""Pearson X^2 for the 2x2 table, upstream's Yates form (|O - E| - 1/2)^2 / E (no clamp at 0).
	Returns the two-sided p-value as mpf (upstream's degenerate cases are handled by the caller)."""
	x1, x2, y1, y2 = cells(seq1, seq2, total1, total2)
	N = x1 + x2 + y1 + y2
	E = [(x1 + x2) * (x1 + y1) / N, (x1 + x2) * (x2 + y2) / N, (y1 + y2) * (x1 + y1) / N, (y1 + y2) * (x2 + y2) / N]
	c = Fraction(1, 2) if yates else 0
	X2 = sum((abs(o - e) - c) ** 2 / e for o, e in zip([x1, x2, y1, y2], E))
	return chi2_sf(X2, 1)


def g_test(seq1, seq2, total1, total2, yates=False, band=False):
	"""G = 2 sum O ln(O / E). With yates=True the cells are first moved by 1/2 exactly as upstream
	does (towards independence when x1*y2 - x2*y1 > 0, otherwise the other way), and cells with
	O <= 0 or E <= 0 are skipped as upstream does.

	With band=True also returns the p-values at G -/+ dG, where dG = 16 eps sum O (1 + |ln(O/E)|)
	bounds the rounding error of upstream's double-precision evaluation (each term O*log(O/E) is
	off by about O * eps * (3 + |ln(O/E)|), plus the summation). Near independence G is a small
	difference of large terms, so this error, not the oracle, limits the attainable agreement."""
	x1, x2, y1, y2 = cells(seq1, seq2, total1, total2)
	if yates:
		h = Fraction(1, 2)
		if x1 * y2 - x2 * y1 > 0:
			x1, y2, x2, y1 = x1 - h, y2 - h, x2 + h, y1 + h
		else:
			x1, y2, x2, y1 = x1 + h, y2 + h, x2 - h, y1 - h
	N = x1 + x2 + y1 + y2
	if N <= 0:
		return (mp.mpf(1),) * 3 if band else mp.mpf(1)
	E = [(x1 + x2) * (x1 + y1) / N, (x1 + x2) * (x2 + y2) / N, (y1 + y2) * (x1 + y1) / N, (y1 + y2) * (x2 + y2) / N]
	G = mp.mpf(0)
	scale = mp.mpf(0)
	for o, e in zip([x1, x2, y1, y2], E):
		if o > 0 and e > 0:
			term = mp.log(M(o) / M(e))
			G += M(o) * term
			scale += M(o) * (1 + abs(term))
	p = chi2_sf(2 * G, 1)
	if not band:
		return p
	dG = 16 * mp.mpf(2) ** -52 * scale
	return p, chi2_sf(2 * G + dG, 1), chi2_sf(max(2 * G - dG, 0), 1)


def diff_between_prop_test(seq1, seq2, total1, total2):
	"""Pooled z test. Returns (one-sided, two-sided) = (Phi(-|D|), 2 Phi(-|D|))."""
	s1, s2, n1, n2 = Q(seq1), Q(seq2), Q(total1), Q(total2)
	if (s1 == 0 and s2 == 0) or (s1 == n1 and s2 == n2):
		D = mp.mpf(0)
	else:
		P = (s1 + s2) / (n1 + n2)
		D = M(s1 / n1 - s2 / n2) / mp.sqrt(M(P * (1 - P) * (1 / n1 + 1 / n2)))
	one = mp.ncdf(-abs(D))
	return one, 2 * one


def wilson(seq, total, z):
	"""Wilson score interval (no continuity correction) in closed form."""
	p = M(Q(seq) / Q(total))
	n = M(total)
	centre = p + z * z / (2 * n)
	half = z * mp.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
	d = 1 + z * z / n
	return (centre - half) / d, (centre + half) / d


def _pseudo_totals(total1, total2, prefs):
	n1 = Q(total1) if total1 != 0 else Q(prefs['Pseudocount'])
	n2 = Q(total2) if total2 != 0 else Q(prefs['Pseudocount'])
	return n1, n2


def ci_dp_asymptotic(seq1, seq2, total1, total2, coverage, prefs=PREFS, cc=False):
	"""Wald interval for p1 - p2 in percent. With cc=True upstream's continuity-corrected form:
	z * (SE + (1/n1 + 1/n2)/2) (the correction is multiplied by z, unlike the textbook
	z * SE + (1/n1 + 1/n2)/2)."""
	n1, n2 = _pseudo_totals(total1, total2, prefs)
	r1, r2 = Q(seq1) / n1, Q(seq2) / n2
	se = mp.sqrt(M(r1 * (1 - r1) / n1 + r2 * (1 - r2) / n2))
	if cc:
		se += M((1 / n1 + 1 / n2) / 2)
	off = z_two_sided(coverage) * se
	d = M(r1 - r2)
	return (d - off) * 100, (d + off) * 100, d * 100


def ci_newcombe_wilson(seq1, seq2, total1, total2, coverage, prefs=PREFS):
	"""Newcombe's hybrid score interval (method 10) from Wilson intervals, in percent."""
	n1, n2 = _pseudo_totals(total1, total2, prefs)
	z = z_two_sided(coverage)
	l1, u1 = wilson(seq1, n1, z)
	l2, u2 = wilson(seq2, n2, z)
	p1, p2 = M(Q(seq1) / n1), M(Q(seq2) / n2)
	d = p1 - p2
	lower = d - mp.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
	upper = d + mp.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
	return lower * 100, upper * 100, d * 100


def _or_cells(seq1, seq2, total1, total2, prefs):
	a, b, c, d = cells(seq1, seq2, total1, total2)
	if a == 0 or b == 0 or c == 0 or d == 0:
		pc = Q(prefs['Pseudocount'])
		a, b, c, d = a + pc, b + pc, c + pc, d + pc
	return a, b, c, d


def ci_odds_ratio(seq1, seq2, total1, total2, coverage, prefs=PREFS):
	"""Woolf log interval with Haldane's +pseudocount when any cell is zero."""
	a, b, c, d = _or_cells(seq1, seq2, total1, total2, prefs)
	es = a * d / (b * c)
	se = mp.sqrt(M(1 / a + 1 / b + 1 / c + 1 / d))
	z = z_two_sided(coverage)
	return mp.exp(mp.log(M(es)) - z * se), mp.exp(mp.log(M(es)) + z * se), es


def ci_ratio_proportions(seq1, seq2, total1, total2, coverage, prefs=PREFS):
	"""Katz log interval for p1/p2; when a count is zero both counts get +pc and both totals +2pc."""
	s1, s2, n1, n2 = Q(seq1), Q(seq2), Q(total1), Q(total2)
	if s1 == 0 or s2 == 0:
		pc = Q(prefs['Pseudocount'])
		s1, s2, n1, n2 = s1 + pc, s2 + pc, n1 + 2 * pc, n2 + 2 * pc
	es = (s1 / n1) / (s2 / n2)
	se = mp.sqrt(M(1 / s1 - 1 / n1 + 1 / s2 - 1 / n2))
	z = z_two_sided(coverage)
	return mp.exp(mp.log(M(es)) - z * se), mp.exp(mp.log(M(es)) + z * se), es


def es_diff_between_prop(seq1, seq2, total1, total2):
	return (Q(seq1) / max(Q(total1), 1) - Q(seq2) / max(Q(total2), 1)) * 100


def es_odds_ratio(seq1, seq2, total1, total2, prefs=PREFS):
	a, b, c, d = _or_cells(seq1, seq2, total1, total2, prefs)
	return a * d / (b * c)


def es_ratio_proportions(seq1, seq2, total1, total2, prefs=PREFS):
	"""Upstream's filter adds the pseudocount once to each total (the CI method adds it twice)."""
	s1, s2, n1, n2 = Q(seq1), Q(seq2), Q(total1), Q(total2)
	if s1 == 0 or s2 == 0:
		pc = Q(prefs['Pseudocount'])
		s1, s2, n1, n2 = s1 + pc, s2 + pc, n1 + pc, n2 + pc
	return (s1 / n1) / (s2 / n2)


# ------------------------------------------------------------------ two-group statistics

def proportions(counts, parents):
	return [Q(c) / Q(p) if p > 0 else Fraction(0) for c, p in zip(counts, parents)]


def mean_var(xs):
	n = len(xs)
	m = sum(xs, Fraction(0)) / n
	v = sum(((x - m) ** 2 for x in xs), Fraction(0)) / (n - 1)
	return m, v


def t_test(counts1, counts2, parents1, parents2, coverage, welch, start=None):
	"""Student (pooled) or Welch t test on per-sample proportions. Returns
	(one-sided = P(T >= t), two-sided, lowerCI %, upperCI %, effect size %)."""
	g1, g2 = proportions(counts1, parents1), proportions(counts2, parents2)
	n1, n2 = len(g1), len(g2)
	m1, v1 = mean_var(g1)
	m2, v2 = mean_var(g2)
	d = m1 - m2
	if welch:
		a, b = v1 / n1, v2 / n2
		var = a + b
		dof = var * var / (a * a / (n1 - 1) + b * b / (n2 - 1))
	else:
		dof = Fraction(n1 + n2 - 2)
		var = ((n1 - 1) * v1 + (n2 - 1) * v2) / dof * (Fraction(1, n1) + Fraction(1, n2))
	se = mp.sqrt(M(var))
	T = M(d) / se
	cdf = t_cdf(T, M(dof))
	tcrit = t_isf((1 - M(coverage)) / 2, M(dof), start)
	return 1 - cdf, 2 * min(cdf, 1 - cdf), (M(d) - tcrit * se) * 100, (M(d) + tcrit * se) * 100, M(d) * 100


def es_group_diff(prop1, prop2):
	m1 = sum(map(Q, prop1), Fraction(0)) / len(prop1) if prop1 else Fraction(0)
	m2 = sum(map(Q, prop2), Fraction(0)) / len(prop2) if prop2 else Fraction(0)
	return m1 - m2


def es_group_ratio(prop1, prop2, prefs=PREFS):
	"""Upstream: if a mean is zero add pseudocount / (mean1 + mean2) to both means."""
	m1 = sum(map(Q, prop1), Fraction(0)) / len(prop1)
	m2 = sum(map(Q, prop2), Fraction(0)) / len(prop2)
	if m1 == 0 or m2 == 0:
		pc = Q(prefs['Pseudocount']) / (m1 + m2)
		m1, m2 = m1 + pc, m2 + pc
	return m1 / m2


# ------------------------------------------------------------------ multi-group statistics

def _groups(data):
	return [[Q(x) for x in g] for g in data]


def anova(data):
	g = _groups(data)
	k = len(g)
	N = sum(len(x) for x in g)
	grand = sum(sum(x, Fraction(0)) for x in g) / N
	ssb = sum(len(x) * (sum(x, Fraction(0)) / len(x) - grand) ** 2 for x in g)
	ssw = sum(sum((v - sum(x, Fraction(0)) / len(x)) ** 2 for v in x) for x in g)
	F = (ssb / (k - 1)) / (ssw / (N - k))
	return f_sf(M(F), k - 1, N - k)


def kruskal_wallis(data):
	"""H with mid-ranks and the tie correction 1 - sum(t^3 - t)/(N^3 - N); p from chi2(k - 1)."""
	g = _groups(data)
	pooled = sorted(v for x in g for v in x)
	N = len(pooled)
	rank = {}
	i = 0
	ties = 0
	while i < N:
		j = i
		while j + 1 < N and pooled[j + 1] == pooled[i]:
			j += 1
		rank[pooled[i]] = Fraction(i + 1 + j + 1, 2)
		t = j - i + 1
		ties += t ** 3 - t
		i = j + 1
	H = Fraction(12, N * (N + 1)) * sum(sum((rank[v] for v in x), Fraction(0)) ** 2 / len(x) for x in g) - 3 * (N + 1)
	C = 1 - Fraction(ties, N ** 3 - N)
	return chi2_sf(M(H / C), len(g) - 1), H / C


def eta_squared(data):
	g = _groups(data)
	allv = [v for x in g for v in x]
	grand = sum(allv, Fraction(0)) / len(allv)
	sst = sum((v - grand) ** 2 for v in allv)
	ssb = sum(len(x) * (sum(x, Fraction(0)) / len(x) - grand) ** 2 for x in g)
	return ssb / sst


def scheffe(data, coverage):
	g = _groups(data)
	k = len(g)
	N = sum(len(x) for x in g)
	dfN, dfD = k - 1, N - k
	means = [sum(x, Fraction(0)) / len(x) for x in g]
	msw = sum(sum((v - m) ** 2 for v in x) for x, m in zip(g, means)) / dfD
	cv = dfN * f_ppf(M(coverage), dfN, dfD)
	out = []
	for i in range(k):
		for j in range(i + 1, k):
			es = means[i] - means[j]
			inv = Fraction(1, len(g[i])) + Fraction(1, len(g[j]))
			Fs = es * es / (msw * inv)
			half = mp.sqrt(cv * M(inv)) * mp.sqrt(M(msw))
			out.append((f_sf(M(Fs / dfN), dfN, dfD), es, M(es) - half, M(es) + half))
	return out


def tukey_category(p):
	for cut in ('0.001', '0.01', '0.02', '0.05', '0.1'):
		if p < mp.mpf(cut):
			return '< ' + cut
	return '>= 0.1'


# ------------------------------------------------------------------ multiple-comparison corrections

def bonferroni(p):
	m = len(p)
	return [Q(x) * m for x in p]


def sidak(p):
	m = len(p)
	return [1 - (1 - M(x)) ** m for x in p]


def bh_upstream_ranks(p):
	"""Upstream ranks: ascending order of (p, index), so tied p-values get distinct ranks with the
	lower input index ranked first (sort(reverse=True) over [p, index] pairs)."""
	order = sorted(range(len(p)), key=lambda i: (p[i], i))
	rank = [0] * len(p)
	for r, i in enumerate(order, start=1):
		rank[i] = r
	return rank


def benjamini_hochberg_upstream(p):
	"""Upstream definition: p * m / rank, no step-up minimum, no cap at 1."""
	m = len(p)
	rank = bh_upstream_ranks(p)
	return [Q(x) * m / r for x, r in zip(p, rank)]


def benjamini_hochberg_stepup(p):
	"""Textbook BH adjusted p-values (step-up cumulative minimum, capped at 1), for reference."""
	m = len(p)
	order = sorted(range(m), key=lambda i: p[i])
	adj = [None] * m
	running = Fraction(1)
	for r in range(m, 0, -1):
		i = order[r - 1]
		running = min(running, Q(p[i]) * m / r)
		adj[i] = running
	return adj


STOREY_LAMBDAS = [Fraction(j, 20) for j in range(20)]		# upstream numpy.arange(0.0, 0.951, 0.05)


def storey_pi0_candidates(p):
	m = len(p)
	return [Fraction(sum(1 for x in p if Q(x) > lam), 1) / (m * (1 - lam)) for lam in STOREY_LAMBDAS]


def storey_qvalues(p, pi0):
	"""q_(r) = min_{s >= r} pi0 m p_(s) / s over the ascending order of (p, index)."""
	m = len(p)
	pi0 = Q(pi0)
	order = sorted(range(m), key=lambda i: (p[i], i))
	q = [None] * m
	running = None
	for r in range(m, 0, -1):
		i = order[r - 1]
		v = pi0 * m * Q(p[i]) / r
		running = v if running is None else min(running, v)
		q[i] = running
	return q


# ------------------------------------------------------------------ exact null distributions

def binomial_pmf(n, p):
	"""Exact pmf of Binomial(n, p) for rational p, as a list of Fractions."""
	p = Q(p)
	return [comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)]


def bootstrap_null_tails(seq1, seq2, total1, total2):
	"""Exact tail probabilities of upstream's parametric bootstrap null: c_i ~ Bin(n_i, pooled p),
	D = c1/n1 - c2/n2. Returns (P(D <= obs), P(D >= obs), P(|D| >= |obs|))."""
	n1, n2 = int(total1), int(total2)
	pool = Fraction(int(seq1) + int(seq2), n1 + n2)
	b1, b2 = binomial_pmf(n1, pool), binomial_pmf(n2, pool)
	obs = Fraction(int(seq1), n1) - Fraction(int(seq2), n2)
	left = right = two = Fraction(0)
	for c1, w1 in enumerate(b1):
		for c2, w2 in enumerate(b2):
			d = Fraction(c1, n1) - Fraction(c2, n2)
			w = w1 * w2
			if d <= obs:
				left += w
			if d >= obs:
				right += w
			if abs(d) >= abs(obs):
				two += w
	return left, right, two


def permutation_null_tails(seq1, seq2, total1, total2):
	"""Exact tails of upstream's permutation null: c1 ~ Hypergeometric(pos, neg, total1)."""
	n1, n2 = int(total1), int(total2)
	w, tot = hyper_weights(seq1, seq2, n1, n2)
	pos = int(seq1) + int(seq2)
	obs = Fraction(int(seq1), n1) - Fraction(int(seq2), n2)
	left = right = two = 0
	for c1, v in w.items():
		d = Fraction(c1, n1) - Fraction(pos - c1, n2)
		if d <= obs:
			left += v
		if d >= obs:
			right += v
		if abs(d) >= abs(obs):
			two += v
	return Fraction(left, tot), Fraction(right, tot), Fraction(two, tot)


def welch_t(g1, g2):
	"""Upstream White's statistic: (m1 - m2)/sqrt(v1/n1 + v2/n2), or (m1 - m2)/1e-6 when both
	variances are zero. Exact rational in, mpf out."""
	m1, v1 = mean_var(g1)
	m2, v2 = mean_var(g2)
	den = v1 / len(g1) + v2 / len(g2)
	if den == 0:
		return M(m1 - m2) / mp.mpf('1e-6')
	return M(m1 - m2) / mp.sqrt(M(den))


# ------------------------------------------------------------------ data

def stamp_profile_from_rows(path, headings, rows):
	"""Write a STAMP profile (hierarchy columns then sample columns, tab separated)."""
	with open(path, 'w') as f:
		f.write('\t'.join(headings) + '\n')
		for r in rows:
			f.write('\t'.join(str(x) for x in r) + '\n')
	return path


def skirball_phylum_profile(path):
	"""Collapse the 400-feature Skirball table to a two-level (Phylum, Class) STAMP profile; empty
	names become 'unclassified'."""
	with open(os.path.join(SKIRBALL, 'skirball-400.tsv')) as f:
		rows = list(csv.reader(f, delimiter='\t'))
	h = rows[0]
	samples = [c for c in h if c.startswith('S') and c[1:].isdigit()]
	idx = [h.index(s) for s in samples]
	ip, ic = h.index('Phylum'), h.index('Class')
	agg = defaultdict(lambda: [0] * len(samples))
	for r in rows[1:]:
		phylum = r[ip].strip() or 'unclassified'
		klass = r[ic].strip() or 'unclassified'
		if phylum == 'unclassified':
			klass = 'unclassified'
		for j, i in enumerate(idx):
			agg[(phylum, klass)][j] += int(r[i])
	out = [[p, c] + v for (p, c), v in sorted(agg.items())]
	return stamp_profile_from_rows(path, ['Phylum', 'Class'] + samples, out), samples


def skirball_sums_profile(path, level='phylum'):
	"""The pre-collapsed full Skirball level sums (Kingdom column dropped: all 'Unclassified')."""
	import gzip
	with gzip.open(os.path.join(SKIRBALL, 'skirball-reference', '%s_sums.tsv.gz' % level), 'rt') as f:
		rows = list(csv.reader(f, delimiter='\t'))
	h = rows[0]
	first = next(i for i, c in enumerate(h) if c == 'S1')
	out = [r[1:first] + [int(float(x)) for x in r[first:]] for r in rows[1:]]
	return stamp_profile_from_rows(path, h[1:first] + h[first:], out)
