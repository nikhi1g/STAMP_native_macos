"""Multiple-group mode: ANOVA, Kruskal-Wallis, eta-squared and the post-hoc tests (Games-Howell,
Scheffe, Tukey-Kramer, Welch's uncorrected). Inputs: getActiveFeatureProportions of every feature
of Enterotypes (3 groups: 8, 6, 18 samples) and Skirball (burn status and section, 2 groups each),
plus hand-made edge cases."""
import functools
import importlib
import math

import mpmath as mp
import pytest
from scipy import stats

import oracle
from oracle import Checks, PREFS, Q
from test_acc_qtable import interp_tol

EPS = 2.0 ** -52

# (label, data)
EDGE_MULTI = [
	('n = 2 per group', [[1.5, 2.5], [3.0, 3.5], [0.5, 1.0]]),
	('equal groups', [[1.0, 2.0, 3.0, 4.0, 5.0]] * 3),
	('one group zero variance', [[2.0] * 5, [1.0, 2.0, 3.0, 4.0, 6.0], [2.5, 2.6, 2.7, 2.8, 3.9]]),
	('ties across groups', [[1.0, 1.0, 2.0, 2.0, 3.0], [2.0, 2.0, 3.0, 3.0, 3.0], [1.0, 3.0, 3.0, 4.0, 4.0]]),
	('zeros', [[0.0, 0.0, 0.0, 0.0, 0.1], [0.0, 0.2, 0.0, 0.0, 0.0], [0.0] * 5 + [0.3]]),
	('large offset, small spread', [[1e6 + x for x in (0.1, 0.2, 0.3, 0.4, 0.5)], [1e6 + x for x in (0.2, 0.3, 0.4, 0.5, 0.7)], [1e6 + x for x in (0.0, 0.1, 0.1, 0.2, 0.3)]]),
	('unequal sizes, 5 groups', [[3.1, 2.9, 3.3, 3.0, 3.6, 2.2], [4.0, 4.4, 3.9, 4.2, 5.1], [2.0, 2.5, 2.2, 1.9, 2.8, 2.1, 2.4], [3.3, 3.1, 3.8, 3.5, 3.2], [5.5, 4.9, 5.1, 5.8, 5.2, 6.0]]),
]


def plugin(kind, name):
	mod = importlib.import_module('stamp.plugins.multiGroups.%s.%s' % (kind, name))
	return getattr(mod, name)(PREFS)


@pytest.fixture(scope='module')
def inputs(multi_inputs):
	out = [(label, data) for label, data, names in multi_inputs]
	return out + [('edge: ' + l, d) for l, d in EDGE_MULTI]


def _constant(data):
	vals = {v for g in data for v in g}
	return len(vals) == 1


def test_anova(inputs):
	anova = plugin('statisticalTests', 'ANOVA')
	ck = Checks()
	for label, data in inputs:
		p, note = anova.hypothesisTest(data)
		if any(len(g) < 2 for g in data):
			assert (p, note) == (1.0, 'degenerate case: at least one group contains less than 2 samples')
			continue
		g = oracle._groups(data)
		within = sum(sum((v - sum(x, 0) / len(x)) ** 2 for v in x) for x in g)
		if within == 0:
			assert p == 1.0 or math.isnan(p) is False		# scipy returns nan/inf; upstream maps nan to 1
			continue
		ck('multi/ANOVA p-value', p, oracle.anova(data), ctx=label)
	ck.done()


# all-identical data: scipy divides H by a zero tie correction (nan); upstream maps it to p = 1
@pytest.mark.filterwarnings('ignore:invalid value encountered in scalar divide:RuntimeWarning')
def test_kruskal_wallis(inputs):
	"""H uses mid-ranks and the tie correction C = 1 - sum(t^3 - t)/(N^3 - N) (scipy.stats.kruskal
	applies it; the oracle computes it exactly). Groups smaller than 5 samples: upstream returns
	p = 1 with a note."""
	kw = plugin('statisticalTests', 'KruskalWallis')
	ck = Checks()
	tied = 0
	for label, data in inputs:
		p, note = kw.hypothesisTest(data)
		if any(len(g) < 5 for g in data):
			assert (p, note) == (1.0, 'degenerate case: at least one group contains less than 5 samples')
			continue
		if _constant(data):
			assert (p, note) == (1.0, 'Invalid input data for Kruskal-Wallis H-test.')
			continue
		op, H = oracle.kruskal_wallis(data)
		pooled = [v for x in data for v in x]
		tied += len(set(pooled)) < len(pooled)
		ck('multi/KruskalWallis p-value', p, op, ctx=label)
	assert tied > 10		# the tie correction is exercised (zeros are common in real profiles)
	ck.done()


def test_eta_squared(inputs):
	"""Upstream computes SS_between as sum(group sum^2 / n) - total^2 / N, which cancels
	catastrophically when the group means differ little relative to their magnitude. Real
	profiles (percent abundances) are checked at 1e-12; the 'large offset, small spread' edge
	case is the defect asserted in test_acc_defects.py."""
	eta = plugin('effectSizeFilters', 'EtaSquared')
	ck = Checks()
	for label, data in inputs:
		if label.startswith('edge: large offset'):
			continue
		v = eta.run(data)
		if _constant(data):
			assert v == -1.0
			continue
		ck('multi/EtaSquared', v, oracle.eta_squared(data), ctx=label)
	ck.done()


@functools.lru_cache(maxsize=None)
def _f_ppf(coverage, dfN, dfD):
	return oracle.f_ppf(oracle.M(coverage), dfN, dfD)


def cond_tol(label, data):
	"""1e-12, except for the deliberately ill-conditioned 'large offset, small spread' case: means
	of values ~1e6 that differ by ~0.1 lose log10(1e6/0.1) = 7 digits to cancellation in any
	double-precision evaluation (sums carry ~n eps |x| absolute error). Tolerance there:
	64 eps max|x| / min spread = 1.4e-7 (measured worst 7.5e-8, see the summary)."""
	if not label.startswith('edge: large offset'):
		return oracle.REL
	vals = [v for g in data for v in g]
	return 64 * EPS * max(abs(v) for v in vals) / 0.1


def test_scheffe(inputs):
	from stamp.plugins.multiGroups.postHoc.Scheffe import Scheffe
	scheffe = Scheffe(PREFS)
	ck = Checks()
	for label, data in inputs:
		if any(len(g) < 2 for g in data):
			continue
		g = oracle._groups(data)
		k, N = len(g), sum(len(x) for x in g)
		means = [sum(x, 0) / len(x) for x in g]
		msw = sum(sum((v - m) ** 2 for v in x) for x, m in zip(g, means))
		if msw == 0:
			continue		# upstream substitutes 1e-6 for the variance (test_acc_upstream_behaviour.py)
		for coverage in (0.95, 0.99):
			pv, es, lo, hi, labels, note = scheffe.run(data, coverage, ['g%d' % i for i in range(k)])
			cv = (k - 1) * _f_ppf(coverage, k - 1, N - k)
			n = 0
			for i in range(k):
				for j in range(i + 1, k):
					inv = Q(1) / len(g[i]) + Q(1) / len(g[j])
					d = means[i] - means[j]
					Fs = d * d / (msw / (N - k) * inv)
					half = mp.sqrt(cv * oracle.M(inv)) * mp.sqrt(oracle.M(msw / (N - k)))
					ctx = (label, coverage, i, j)
					tol = cond_tol(label, data)
					# CI endpoints are effect -/+ half-width: relative accuracy refers to the size of
					# those terms, abs_tol = tol * (|effect| + half-width)
					scale = tol * float(abs(oracle.M(d)) + half)
					ck('multi/Scheffe p-value', pv[n], oracle.f_sf(oracle.M(Fs / (k - 1)), k - 1, N - k), rel=tol, ctx=ctx)
					ck('multi/Scheffe effect', es[n], d, rel=tol, ctx=ctx)
					ck('multi/Scheffe CI lower', lo[n], oracle.M(d) - half, rel=tol, abs_tol=scale, ctx=ctx)
					ck('multi/Scheffe CI upper', hi[n], oracle.M(d) + half, rel=tol, abs_tol=scale, ctx=ctx)
					n += 1
	ck.done()


def test_welch_uncorrected(inputs):
	"""Pairwise Welch t-tests. Upstream passes the percent data with parent counts of 0.01, so
	the oracle is the Welch oracle on exactly those inputs (effect sizes and CIs come out 1e4 x
	the difference in percent; documented upstream behaviour)."""
	welch = plugin('postHoc', 'WelchUncorrected')
	ck = Checks()
	for label, data in inputs:
		k = len(data)
		if any(len(g) < 2 for g in data):
			continue
		for coverage in (0.95, 0.99):
			pv, es, lo, hi, labels, note = welch.run(data, coverage, ['g%d' % i for i in range(k)])
			n = 0
			for i in range(k):
				for j in range(i + 1, k):
					pi, pj = [0.01] * len(data[i]), [0.01] * len(data[j])
					gi, gj = oracle.proportions(data[i], pi), oracle.proportions(data[j], pj)
					if oracle.mean_var(gi)[1] == 0 and oracle.mean_var(gj)[1] == 0:
						n += 1
						continue		# upstream degenerate branch
					o = oracle.t_test(data[i], data[j], pi, pj, coverage, True, start=stats.t.isf((1 - coverage) / 2, 5))
					ctx = (label, coverage, i, j)
					tol = cond_tol(label, data)
					# CI endpoints are effect -/+ half-width (both ~1e4 x the percent difference here);
					# relative accuracy refers to the size of those terms
					scale = tol * float(abs(o[4]) + (o[3] - o[2]) / 2)
					ck('multi/WelchUncorrected p-value', pv[n], o[1], rel=tol, ctx=ctx)
					ck('multi/WelchUncorrected effect (x1e4)', es[n], o[4], rel=tol, ctx=ctx)
					ck('multi/WelchUncorrected CI lower', lo[n], o[2], rel=tol, abs_tol=scale, ctx=ctx)
					ck('multi/WelchUncorrected CI upper', hi[n], o[3], rel=tol, abs_tol=scale, ctx=ctx)
					n += 1
	ck.done()


# ------------------------------------------------------------------ studentized range post-hoc tests

POST_HOC_FEATURES = {
	'enterotypes 3 groups': ['Bacteroides', 'Prevotella', 'Ruminococcus', 'Alistipes'],
	'skirball burn status (2 groups)': ['Bacteroidetes', 'Proteobacteria'],
}


@functools.lru_cache(maxsize=None)
def qcrit(alpha, k, df):
	"""Exact studentized-range critical value (mpmath quadrature + secant; scipy only seeds it)."""
	return oracle.qtukey_isf(oracle.M(alpha), k, df, start=stats.studentized_range.isf(float(alpha), k, df))


@functools.lru_cache(maxsize=None)
def psf(q, k, df):
	return oracle.ptukey_sf(q, k, df)


def _post_hoc_inputs(multi_profiles):
	for name, mgp in multi_profiles:
		for f in POST_HOC_FEATURES.get(name, []):
			yield name, f, mgp.getActiveFeatureProportions(f), list(mgp.activeGroupNames)


def test_tukey_kramer(multi_profiles):
	"""Upstream reads the critical value q(1 - alpha; k, df) from tables (stamp/data/tukeyQ_*.txt,
	integer df 2..200, k 2..29) without interpolation. The CI half-width is
	q_table * s * sqrt((1/ni + 1/nj)/2), so its relative error is the table's: tolerance
	oracle.qtable_tol_q(df) (measured table envelope, 2.6e-6 at df = 29; measured here: see
	'multi/TukeyKramer CI half-width' in the summary). Effect sizes and CI centres at 1e-12;
	p-value categories exact (asserted against the exact studentized-range p-value)."""
	tk = plugin('postHoc', 'TukeyKramer')
	ck = Checks()
	for name, f, data, names in _post_hoc_inputs(multi_profiles):
		g = oracle._groups(data)
		k, N = len(g), sum(len(x) for x in g)
		df = N - k
		means = [sum(x, 0) / len(x) for x in g]
		sw = mp.sqrt(oracle.M(sum(sum((v - m) ** 2 for v in x) for x, m in zip(g, means)) / df))
		for coverage in (0.95, 0.99):
			pv, es, lo, hi, labels, note = tk.run(data, coverage, names)
			q = qcrit(round(1 - coverage, 3), k, df)
			n = 0
			for i in range(k):
				for j in range(i + 1, k):
					s = mp.sqrt(oracle.M((Q(1) / len(g[i]) + Q(1) / len(g[j])) / 2))
					d = means[i] - means[j]
					ctx = (name, f, coverage, i, j)
					ck('multi/TukeyKramer effect', es[n], d, ctx=ctx)
					ck('multi/TukeyKramer CI half-width [table tol]', (hi[n] - lo[n]) / 2, q * sw * s, rel=oracle.qtable_tol_q(df), ctx=ctx)
					ck('multi/TukeyKramer CI centre', (hi[n] + lo[n]) / 2, d, rel=1e-12, abs_tol=1e-12 * float(q * sw * s), ctx=ctx)
					if coverage == 0.95:
						assert pv[n] == oracle.tukey_category(psf(abs(oracle.M(d)) / (sw * s), k, df)), ctx
					n += 1
	ck.done()


def test_games_howell(multi_profiles):
	"""Games-Howell uses the Welch-Satterthwaite df, which is fractional; upstream linearly
	interpolates the tabulated q between floor(df) and ceil(df). q is convex in df, so linear
	interpolation overestimates it; the error is largest at small df (measured in the summary,
	'multi/GamesHowell CI half-width', 3.3e-3 at df = 5.4). Tolerance on the half-width:
	test_acc_qtable.interp_tol(df) (interpolation bound 2/floor(df)^3 + table envelope).
	Effect sizes and CI centres at 1e-12."""
	gh = plugin('postHoc', 'GamesHowell')
	ck = Checks()
	for name, f, data, names in _post_hoc_inputs(multi_profiles):
		g = oracle._groups(data)
		k = len(g)
		mv = [oracle.mean_var(x) for x in g]
		pv, es, lo, hi, labels, note = gh.run(data, 0.95, names)
		n = 0
		for i in range(k):
			for j in range(i + 1, k):
				a, b = mv[i][1] / len(g[i]), mv[j][1] / len(g[j])
				df = (a + b) ** 2 / (a * a / (len(g[i]) - 1) + b * b / (len(g[j]) - 1))
				adj = mp.sqrt(oracle.M((a + b) / 2))
				d = mv[i][0] - mv[j][0]
				q = qcrit(0.05, k, float(df))
				ctx = (name, f, i, j, float(df))
				ck('multi/GamesHowell effect', es[n], d, ctx=ctx)
				ck('multi/GamesHowell CI half-width [interp tol]', (hi[n] - lo[n]) / 2, q * adj, rel=interp_tol(float(df)), ctx=ctx)
				ck('multi/GamesHowell CI centre', (hi[n] + lo[n]) / 2, d, abs_tol=1e-12 * float(q * adj), ctx=ctx)
				pexact = psf(abs(oracle.M(d)) / adj, k, float(df))
				cat = oracle.tukey_category(pexact)
				if pv[n] != cat:
					# allowed only if the exact p is within the interpolation error of a boundary
					assert any(abs(pexact - c) < 0.05 * c for c in (0.001, 0.01, 0.02, 0.05, 0.1)), (ctx, pv[n], cat, pexact)
				n += 1
	ck.done()
