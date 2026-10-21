"""Upstream behaviours that are statistically questionable but are STAMP 2.1.3's definition and
are preserved by the port (parity with the Python 2 build). Each test asserts the documented
upstream value (to 1e-12 where numeric) and, where a textbook alternative exists, shows that it
differs -- so a deliberate future change shows up here. These are not failures of the port."""
import importlib
import math

import mpmath as mp
import numpy
import pytest

from fractions import Fraction

import oracle
from oracle import PREFS, Q


def sample_plugin(kind, name):
	mod = importlib.import_module('stamp.plugins.samples.%s.%s' % (kind, name))
	return getattr(mod, name)(PREFS)


def test_chi_square_one_sample_at_100_percent_returns_p_1():
	"""ChiSquare / ChiSquareYates return p = 1 ('degenerate case') whenever either sample's feature
	count equals its parent total, although the 2x2 table has positive expected counts and the
	test is well defined: (10, 0, 10, 10) is 100 % vs 0 %."""
	for name, yates in (('ChiSquare', False), ('ChiSquareYates', True)):
		one, two, note = sample_plugin('statisticalTests', name).hypothesisTest(10, 0, 10, 10)
		assert (one, two, note) == (math.inf, 1.0, 'degenerate case: suspect p-value')
		assert oracle.chi_square(10, 0, 10, 10, yates) < 1e-3		# textbook Pearson / Yates


def test_chi_square_yates_not_clamped():
	"""Upstream's Yates term is (|O - E| - 1/2)^2 / E without max(0, .): when |O - E| < 1/2 the
	'correction' increases X^2. (3, 3, 50, 50) is exactly independent (O = E) yet p < 1; the
	textbook clamped form gives X^2 = 0, p = 1."""
	one, two, note = sample_plugin('statisticalTests', 'ChiSquareYates').hypothesisTest(3, 3, 50, 50)
	oracle.check('upstream/ChiSquareYates unclamped', two, oracle.chi_square(3, 3, 50, 50, yates=True))
	assert two < 0.9


def test_g_test_yates_moves_independent_table_away():
	"""GTestYates moves the cells by 1/2 towards independence when x1*y2 - x2*y1 > 0 and the
	other way otherwise -- including when the table is exactly independent (= 0), which makes G > 0
	and p < 1 for (3, 3, 50, 50)."""
	one, two, note = sample_plugin('statisticalTests', 'GTestYates').hypothesisTest(3, 3, 50, 50)
	oracle.check('upstream/GTestYates on independent table', two, oracle.g_test(3, 3, 50, 50, yates=True))
	assert two < 1.0


def test_hypergeometric_two_sided_not_capped():
	"""'Hypergeometric' doubles the one-sided p-value and does not cap it at 1."""
	one, two, _ = sample_plugin('statisticalTests', 'Hypergeometric').hypothesisTest(5, 5, 10, 10)
	o1, o2 = oracle.hypergeometric(5, 5, 10, 10)
	oracle.check('upstream/Hypergeometric two-sided > 1', two, o2)
	assert two > 1.3


def test_one_sided_chi_square_and_g_tests_are_inf():
	for name in ('ChiSquare', 'ChiSquareYates', 'GTest', 'GTestYates'):
		assert sample_plugin('statisticalTests', name).hypothesisTest(5, 9, 100, 100)[0] == math.inf


def test_dp_asymptotic_cc_multiplies_correction_by_z():
	"""DP: Asymptotic-CC uses z * (SE + (1/n1 + 1/n2)/2); the textbook continuity-corrected Wald
	interval is z * SE + (1/n1 + 1/n2)/2."""
	lo, hi, es, _ = sample_plugin('confidenceIntervalMethods', 'DiffBetweenPropAsymptoticCC').run(12, 5, 40, 50, 0.95)
	olo, ohi, oes = oracle.ci_dp_asymptotic(12, 5, 40, 50, 0.95, cc=True)
	oracle.check('upstream/DP-CC (z multiplies the correction)', hi, ohi)
	z = oracle.z_two_sided(0.95)
	r1, r2 = mp.mpf(12) / 40, mp.mpf(5) / 50
	textbook = (r1 - r2 + z * mp.sqrt(r1 * (1 - r1) / 40 + r2 * (1 - r2) / 50) + (mp.mpf(1) / 40 + mp.mpf(1) / 50) / 2) * 100
	assert abs(hi - float(textbook)) > 0.5


def test_ratio_filter_and_ratio_ci_use_different_pseudocounts():
	"""Two-sample 'Ratio of proportions': the effect-size filter adds the pseudocount once to each
	total, the CI method adds it twice, so with a zero count the filter's ratio differs from the
	CI's point estimate."""
	f = sample_plugin('effectSizeFilters', 'RatioProportions').run(0, 4, 100, 120)
	lo, hi, es, _ = sample_plugin('confidenceIntervalMethods', 'RatioProportions').run(0, 4, 100, 120, 0.95)
	oracle.check('upstream/RP filter (pc once)', f, oracle.es_ratio_proportions(0, 4, 100, 120))
	oracle.check('upstream/RP CI point estimate (pc twice)', es, oracle.ci_ratio_proportions(0, 4, 100, 120, 0.95)[2])
	assert f != es


def test_bootstrap_drops_degenerate_note():
	b = sample_plugin('statisticalTests', 'Bootstrap')
	assert b.hypothesisTest(0, 3, 0, 10) == (1.0, 1.0, '')


def test_welch_zero_variance_one_sided_is_always_1():
	"""Welch, both variances exactly zero and means different: pValue = 0 is assigned to the CDF,
	so the one-sided p (= 1 - CDF, i.e. P(T >= t)) is 1.0 whichever group is larger."""
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	w = Welch(PREFS)
	a = w.run([5, 5, 5], [4, 4, 4], [8] * 3, [8] * 3, '', 0.95)
	b = w.run([4, 4, 4], [5, 5, 5], [8] * 3, [8] * 3, '', 0.95)
	assert a[:2] == (1.0, 0.0) and b[:2] == (1.0, 0.0)


def test_welch_uncorrected_scales_effects_by_1e4():
	from stamp.plugins.multiGroups.postHoc.WelchUncorrected import WelchUncorrected
	pv, es, lo, hi, labels, note = WelchUncorrected(PREFS).run([[1.0, 2.0, 3.0], [2.0, 3.0, 5.0]], 0.95, ['a', 'b'])
	oracle.check('upstream/WelchUncorrected effect = 1e4 x percent difference', es[0], (Q(2.0) - Q(10.0 / 3)) * 10000)


def test_post_hoc_zero_variance_substitutions_differ():
	"""Zero within-group variance: Scheffe sets the variance to 1e-6 for its p-values but keeps the
	zero standard deviation for its CI (width 0); Tukey-Kramer sets the standard deviation to 1e-6
	(variance 1e-12); Games-Howell sets each zero vn = var/n to 1e-6."""
	from stamp.plugins.multiGroups.postHoc.Scheffe import Scheffe
	from stamp.plugins.multiGroups.postHoc.TukeyKramer import TukeyKramer
	data = [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [4.0, 4.0, 4.0]]
	pv, es, lo, hi, labels, note = Scheffe(PREFS).run(data, 0.95, ['a', 'b', 'c'])
	assert note.startswith('degenerate case') and lo == es and hi == es
	inv = Fraction(1, 3) + Fraction(1, 3)
	oracle.check('upstream/Scheffe zero variance p (var := 1e-6)', pv[0], oracle.f_sf(oracle.M(1 / (Fraction(1, 10 ** 6) * inv) / 2), 2, 6))
	pv, es, lo, hi, labels, note = TukeyKramer(PREFS).run(data, 0.95, ['a', 'b', 'c'])
	assert note.startswith('degenerate case') and pv == ['< 0.001'] * 3
	# hi - es: es is ~1 and the half-width ~1e-6, so the subtraction leaves ~eps/1e-6 ~ 2e-10 relative
	oracle.check('upstream/TukeyKramer zero variance half-width (sd := 1e-6) [cancellation tol]', hi[0] - es[0],
		oracle.M(TukeyKramer(PREFS).qtable.cv(0.05, 3, 6)) * mp.mpf('1e-6') * mp.sqrt(oracle.M(Fraction(1, 3))), rel=1e-9, abs_tol=0)


def test_qtable_df_below_2_sentinel():
	"""QTable.cv returns 1000 for df < 2, and cvInterpolate interpolates towards it for 1 < df < 2:
	Games-Howell with a Welch-Satterthwaite df of 1.5 uses q = (1000 + q(2))/2 ~ 504 (k = 3,
	alpha = 0.05). The exact q(0.95; 3, 1.5) is 12.08 (oracle quadrature; scipy agrees to 3e-6)."""
	from stamp.metagenomics.stats.distributions.QTable import QTable
	qt = QTable(PREFS)
	assert qt.cv(0.05, 3, 1) == 1000.0
	assert qt.cvInterpolate(0.05, 3, 1.5) == pytest.approx((1000.0 + qt.cv(0.05, 3, 2)) / 2, rel=1e-15)


def test_white_small_groups_p_value_can_be_zero():
	"""White's n < 8 branch reports count / (B H) without the +1 of the n >= 8 branch, so a feature
	more extreme than every pooled permuted statistic gets p = 0."""
	import random
	from stamp.plugins.groups.statisticalTests.White import White
	random.seed(2)
	numpy.random.seed(2)
	rows = [([900, 950, 920], [10, 12, 8]), ([500, 510, 490], [480, 520, 505])]
	one, two, lo, hi, es, notes = White(dict(PREFS, Replicates=200)).runAll(
		[a for a, b in rows], [b for a, b in rows], [[1000] * 3] * 2, [[1000] * 3] * 2, '', 0.95, None)
	assert one[0] == 0.0 and two[0] == 0.0


def test_storey_pi0_is_random_between_calls(monkeypatch):
	"""StoreyFDR calls numpy.random.seed() (fresh OS entropy) before its bootstrap, so pi0 -- and
	every q-value -- can differ between two runs on the same p-values. Both runs return one of the
	candidates #{p > lambda}/(m (1 - lambda)) (asserted in test_acc_corrections.py)."""
	from PyQt6 import QtWidgets
	monkeypatch.setattr(QtWidgets.QMessageBox, 'information', staticmethod(lambda *a, **k: None))
	from stamp.plugins.common.multipleComparisonCorrections.StoreyFDR import StoreyFDR
	p = [0.01, 0.02, 0.2, 0.35, 0.5, 0.6, 0.7, 0.8, 0.9, 0.97]
	st = StoreyFDR(PREFS)
	seen = set()
	for _ in range(150):
		st.correct(list(p), 0.05)
		seen.add(st.estimated_pi0_hat)
	cands = {oracle.to_float(c) for c in oracle.storey_pi0_candidates(p)}
	assert all(any(math.isclose(x, c, rel_tol=1e-12) for c in cands) for x in seen)
	# measured over 1000 calls: pi0 = 0.842 (lambda = 0.05) 88.1 %, 0.889 (lambda = 0.1) 11.9 %;
	# P(150 calls all give the same value) ~ 0.881^150 ~ 6e-9
	assert len(seen) >= 2
