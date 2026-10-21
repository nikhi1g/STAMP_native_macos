"""The studentized-range critical values Tukey-Kramer and Games-Howell use: upstream's tables
stamp/data/tukeyQ_{001,01,02,05,10}.txt (q(1 - alpha; k, df), 10 significant digits, df = 2..200,
k = 2..29) and QTable.cvInterpolate (linear in df between integers; df > 200 clamped to 200,
k > 30 clamped to 30, df < 2 -> 1000).

Oracle: P(Q > q) by mpmath Gauss-Legendre quadrature of the studentized-range integral
(oracle.ptukey_sf, accuracy < 1e-11, see test_acc_oracle_self.py) and its secant inverse.
For k = 2 the exact identity q = sqrt(2) t(1 - alpha/2; df) checks every df row cheaply.

Findings encoded here (tolerances are justified next to each assertion):
  * df >= 4: table entries are accurate to ~1e-8 relative in q (worst measured in the summary).
  * df = 3: errors up to ~1e-4 in exceedance probability.
  * df = 2: entries are wrong (k = 29: exceedance 3.4x nominal at alpha = 0.001) -> defect,
    test_acc_defects.py::test_qtable_df2_row.
  * Linear interpolation in df (Games-Howell): relative error ~ 1/df^3, 5-20 % at df = 2.5,
    ~0.5 % at df = 5.5, < 1e-4 beyond df = 20; clamping at df = 200 adds up to 0.3 %."""
import functools
import math

import mpmath as mp
import pytest
from scipy import stats

import oracle

ALPHAS = ['0.001', '0.01', '0.02', '0.05', '0.1']


@pytest.fixture(scope='module')
def qt():
	from stamp.metagenomics.stats.distributions.QTable import QTable
	return QTable(oracle.PREFS)


def test_k2_column_against_exact_t_identity(qt):
	"""For k = 2, Q = sqrt(2) |T| exactly, so q(1 - a; 2, df) = sqrt(2) t_isf(a/2, df). Every df
	row 3..200 of every table (df = 2 is the defect, see module docstring). Tolerance:
	oracle.qtable_tol_q(df), the measured error envelope of the tables (5e-4 at df = 4, 7e-6 at
	df = 6, ~1e-7 from df = 30; worst per df printed in the summary under 'k=2 column')."""
	ck = oracle.Checks()
	for a in ALPHAS:
		for df in range(3, 201):
			exact = mp.sqrt(2) * oracle.t_isf(oracle.M(a) / 2, df, start=stats.t.isf(float(a) / 2, df))
			ck('qtable/k=2 column vs sqrt(2) t [envelope tol]', qt.cv(float(a), 2, df), exact, rel=oracle.qtable_tol_q(df), ctx=(a, df))
	ck.done()


@functools.lru_cache(maxsize=None)
def _sf(q, k, df):
	return oracle.ptukey_sf(q, k, df)


def test_table_exceedance_probabilities(qt):
	"""P(Q > q_table) must equal alpha. Tolerance: oracle.qtable_tol_p(df), the measured envelope
	(relative exceedance error 0.39 at alpha = 0.001, k = 29, df = 3 -- i.e. the tabulated q is
	too large and the test conservative there -- falling to ~1e-7 by df = 30). The q-space error
	is the probability error divided by the elasticity -d ln P / d ln q (about 5..30 here)."""
	ck = oracle.Checks()
	for a in ['0.001', '0.01', '0.05', '0.1']:
		for k in (3, 29):
			for df in (3, 5, 30, 200):
				q = qt.cv(float(a), k, df)
				p = _sf(q, k, df)
				ck('qtable/P(Q > q_table) vs alpha [envelope tol]', p, oracle.M(a), rel=oracle.qtable_tol_p(df), ctx=(a, k, df, q))
	ck.done()


@functools.lru_cache(maxsize=None)
def qexact(alpha, k, df):
	return oracle.qtukey_isf(oracle.M(alpha), k, df, start=stats.studentized_range.isf(float(alpha), k, df))


def interp_tol(df):
	"""Bound on the linear-interpolation error of q between integer df d and d + 1:
	(1/8) max|q''| over [d, d+1] / q; q(df) - q(inf) ~ c / df with c of order q, so the bound is
	about 1/(4 d^3); the worst error explored (scipy, k <= 10, alpha in {0.01, 0.05}, df = d + 1/2)
	is 1.6/d^3 (d = 2, k = 10, alpha = 0.01); confirmed at k = 3, alpha = 0.05 by the oracle in
	this test. Bound used 2/d^3. Above df = 200 upstream clamps to 200: + 5e-3."""
	d = math.floor(df)
	return 2.0 / d ** 3 + (5e-3 if df > 200 else 0) + qtable_tol(d)


def qtable_tol(d):
	return oracle.qtable_tol_q(min(max(d, 3), 200))


@pytest.mark.parametrize('df', [2.5, 3.5, 5.5, 10.5, 50.5, 250.0])
def test_games_howell_interpolation(qt, df):
	k, a = 3, 0.05
	exact = qexact(a, k, df)
	v = qt.cvInterpolate(a, k, df)
	oracle.check('qtable/cvInterpolate vs exact q (k=3, a=0.05) [interp tol]', v, exact, rel=interp_tol(df), abs_tol=0)
	oracle.note_error('qtable/cvInterpolate rel. error at df=%g' % df, abs(v - float(exact)) / float(exact))
