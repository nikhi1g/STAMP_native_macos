"""Suspected defects found by the accuracy suite. Each test asserts the correct (oracle) result
and is marked xfail(strict=True): it fails today, and an XPASS (the defect fixed) turns the suite
red so the marker gets removed. All are upstream behaviour (the code paths are unchanged from
STAMP 2.1.3 apart from the mechanical port); none is caused by the port. The reason string
carries the failing input, STAMP's value and the correct value."""
import importlib
import math
import os
import random

import mpmath as mp
import numpy
import pytest
from scipy import stats

import oracle
from oracle import PREFS


def sample_plugin(kind, name):
	mod = importlib.import_module('stamp.plugins.samples.%s.%s' % (kind, name))
	return getattr(mod, name)(PREFS)


# ------------------------------------------------------------------ two-sample mode

@pytest.mark.xfail(strict=True, reason=(
	"Fishers.py: two-sided p sums tables with p <= P_cutoff compared in floating point with no "
	"relative slack (R uses P_cutoff * (1 + 1e-7)); exactly tied tables computed one ulp apart are "
	"dropped. Fishers.hypothesisTest(1, 2, 2, 8) -> 0.5333 (= 24/45); exact 1.0 (tables a = 0 and "
	"a = 1 both have weight 21/45). 78 of 20214 small tables in test_fishers_grid are affected; "
	"inherited by 'G-test (w/ Yates') + Fisher's' and White's low-count branch."))
def test_fisher_two_sided_includes_tied_tables():
	fishers = sample_plugin('statisticalTests', 'Fishers')
	bad = []
	for t1 in range(1, 13):
		for t2 in range(t1, 13):
			for s1 in range(t1 + 1):
				for s2 in range(t2 + 1):
					if s1 + s2 and oracle.fisher_tied_tables(s1, s2, t1, t2):
						two = fishers.hypothesisTest(s1, s2, t1, t2)[1]
						if not math.isclose(two, float(oracle.fisher(s1, s2, t1, t2)[1]), rel_tol=1e-12):
							bad.append((s1, s2, t1, t2))
	assert fishers.hypothesisTest(1, 2, 2, 8)[1] == pytest.approx(1.0, rel=1e-12)
	assert not bad, bad[:10]


@pytest.mark.xfail(strict=True, reason=(
	"Fishers.py: counts are rounded to integers (floor(x + 0.5)) to build the table, but the "
	"one-sided tails test 'a >= seq1' / 'a <= seq1' against the unrounded seq1, so the observed "
	"table drops out of one tail for non-integer profiles (relative abundances, e.g. Enterotypes). "
	"Fishers.hypothesisTest(4.35613848, 0.0, 551049.9974042901, 571785.6967745499) one-sided -> 0.0; "
	"exact 0.0580091 (table 4/0 of 551050/571786). Also feeds White's low-count branch."))
def test_fisher_one_sided_noninteger_counts():
	fishers = sample_plugin('statisticalTests', 'Fishers')
	args = (4.35613848, 0.0, 551049.9974042901, 571785.6967745499)
	one = fishers.hypothesisTest(*args)[0]
	assert one == pytest.approx(float(oracle.fisher(*args)[0]), rel=1e-7)


@pytest.mark.xfail(strict=True, reason=(
	"NewcombeWilson.py: the Wilson roots are found by scanning v = 0, h, ..., 1 - h "
	"(h = 1/max(n, 1000)); a root in (1 - h, 1] -- always the case for p = 1 -- is never bracketed, "
	"so the single root found is duplicated and the wrong bound is used. run(10, 3, 10, 10, 0.95) "
	"-> upper 103.759 % (above 100 %); exact Newcombe upper 89.224 %. run(999, 950, 1000, 1000, "
	"0.95) is affected the same way. Reachable on real data: a feature equal to its parent "
	"category (e.g. a phylum with one class)."))
def test_newcombe_wilson_root_in_last_grid_step():
	nw = sample_plugin('confidenceIntervalMethods', 'NewcombeWilson')
	for args in [(10, 3, 10, 10), (999, 950, 1000, 1000)]:
		lo, hi, es, note = nw.run(*args, 0.95)
		olo, ohi, oes = oracle.ci_newcombe_wilson(*args, 0.95)
		assert hi == pytest.approx(float(ohi), abs=0.3 * float(ohi - oes)), (args, hi, float(ohi))
		assert lo == pytest.approx(float(olo), abs=0.3 * float(oes - olo)), (args, lo, float(olo))


@pytest.mark.xfail(strict=True, raises=ZeroDivisionError, reason=(
	"statisticalTests/DiffBetweenProp.py divides by a zero parent count: hypothesisTest(33, 0, 58, 0) "
	"raises ZeroDivisionError. Real case: Skirball 400-feature subset, samples S1 vs S6, parent "
	"level Phylum, feature level Class, feature Bacilli (Firmicutes absent from S6); 90 such "
	"features across Skirball sample pairs. Expected: the degenerate result (0.5, 1.0) with a note."))
def test_difference_between_proportions_zero_parent():
	test = sample_plugin('statisticalTests', 'DiffBetweenProp')
	one, two, note = test.hypothesisTest(33.0, 0.0, 58.0, 0.0)
	assert (one, two) == (0.5, 1.0)


@pytest.mark.xfail(strict=True, reason=(
	"Bootstrap.py compares float differences c1/n1 - c2/n2 with <=, >= and abs() >=; outcomes whose "
	"difference equals the observed one exactly in rational arithmetic are classified by rounding. "
	"Bootstrap on (5, 3, 40, 40): two-sided p converges to 0.4815 (float classification) instead of "
	"the exact 0.5709 under upstream's own null (Bin(n_i, pooled p)); one-sided 0.2407 vs 0.2855."))
def test_bootstrap_float_ties():
	test = sample_plugin('statisticalTests', 'Bootstrap')
	test.preferences = dict(PREFS, Replicates=20000)
	numpy.random.seed(3)
	one, two, _ = test.hypothesisTest(5, 3, 40, 40)
	left, right, both = (float(x) for x in oracle.bootstrap_null_tails(5, 3, 40, 40))
	sd = math.sqrt(both * (1 - both) / 20000)
	assert abs(two - both) <= 5 * sd, (two, both)


# ------------------------------------------------------------------ two-group mode

@pytest.mark.xfail(strict=True, reason=(
	"Ttest.py: 'except Exception' precedes 'except ZeroDivisionError', so the zero-variance handler "
	"is dead code. When both groups have exactly zero variance in floating point (proportions that "
	"are exact binary fractions), Ttest.run([5, 5, 5], [4, 4, 4], [8]*3, [8]*3, '', 0.95) returns "
	"one/two-sided p 0.5/1.0, CI (0, 0), effect 0 and note 'float division by zero' although the "
	"means are 62.5 % and 50 %; the intended branch (and Welch.py) gives two-sided p = 0, effect "
	"12.5 %, CI (12.5, 12.5). With 1/10-type proportions numpy's variance is ~1e-34, not 0, and the "
	"result is p = 0 -- so the outcome depends on binary representability."))
def test_ttest_zero_variance_branch_unreachable():
	from stamp.plugins.groups.statisticalTests.Ttest import Ttest
	one, two, lo, hi, es, note = Ttest(PREFS).run([5, 5, 5], [4, 4, 4], [8] * 3, [8] * 3, '', 0.95)
	assert (two, es, lo, hi) == (0.0, 12.5, 12.5, 12.5)


@pytest.mark.xfail(strict=True, raises=ZeroDivisionError, reason=(
	"groups/effectSizeFilters/RatioProportions.py: for a feature absent from both groups it computes "
	"pseudocount / (meanG1 + meanG2) = x / 0 -> ZeroDivisionError inside filterFeatures whenever this "
	"filter is enabled and the profile has an all-zero feature (common when the two groups are a "
	"subset of the samples). Expected: ratio 1.0."))
def test_group_ratio_filter_all_zero_feature():
	from stamp.plugins.groups.effectSizeFilters.RatioProportions import RatioProportions
	assert RatioProportions(PREFS).run([0.0, 0.0, 0.0], [0.0, 0.0]) == 1.0


@pytest.mark.xfail(strict=True, raises=ZeroDivisionError, reason=(
	"White.py divides counts by parent counts without the zero guard Ttest/Welch have. Real case: "
	"Skirball 400-feature subset, 'Burn status' Burned vs Unburned, parent Phylum, level Class "
	"(43 zero parent counts) -> ZeroDivisionError in detect_differentially_abundant_features."))
def test_white_zero_parent_count(group_profiles):
	from stamp.plugins.groups.statisticalTests.White import White
	gp = dict(group_profiles)['skirball400 burned/unburned class']
	f = gp.getFeatures()
	s1, s2 = zip(*[gp.getFeatureCounts(x) for x in f])
	p1, p2 = zip(*[gp.getParentFeatureCounts(x) for x in f])
	assert any(0 in row for row in p1 + p2)
	random.seed(1)
	numpy.random.seed(1)
	res = White(dict(PREFS, Replicates=20)).runAll(list(s1), list(s2), list(p1), list(p2), '', 0.95, None)
	assert all(math.isfinite(x) for x in res[1])


@pytest.mark.xfail(strict=True, reason=(
	"White.py counts permuted statistics with a strict '>' on floats; assignments whose statistic "
	"equals the observed one exactly (tied values, e.g. zeros or repeated proportions) are counted "
	"or not depending on summation order. Groups [3, 5, 2, 4] vs [4, 3, 5, 6] per mille (with two "
	"other features, n < 8 pooled branch): two-sided p converges to 0.3548 (exhaustive enumeration "
	"of the port's own statistic) instead of 0.2952 under upstream's strict definition."))
def test_white_permutation_float_ties():
	from stamp.plugins.groups.statisticalTests.White import White
	import itertools
	from fractions import Fraction
	rows = [([12, 15, 9, 20], [8, 6, 11, 9]), ([3, 5, 2, 4], [4, 3, 5, 6]), ([30, 28, 35, 31], [40, 38, 45, 41])]
	B = 4000
	random.seed(11)
	numpy.random.seed(11)
	one, two, lo, hi, es, notes = White(dict(PREFS, Replicates=B)).runAll(
		[list(a) for a, b in rows], [list(b) for a, b in rows], [[1000] * 4] * 3, [[1000] * 4] * 3, '', 0.95, None)
	props = [[Fraction(c, 1000) for c in a + b] for a, b in rows]
	subsets = list(itertools.combinations(range(8), 4))
	tobs = oracle.welch_t(props[1][:4], props[1][4:])
	mu = 0
	for h in range(3):
		vals = [oracle.welch_t([props[h][i] for i in S], [props[h][i] for i in range(8) if i not in S]) for S in subsets]
		mu += Fraction(sum(1 for v in vals if abs(v) > abs(tobs) + mp.mpf('1e-30')), len(subsets))
	mu = float(mu / 3)
	assert abs(two[1] - mu) <= 5 * math.sqrt(mu * (1 - mu) / B), (two[1], mu)


# ------------------------------------------------------------------ multiple-group mode

@pytest.mark.xfail(strict=True, reason=(
	"EtaSquared.py computes SS_between as sum(groupSum^2/n) - total^2/N, which cancels "
	"catastrophically: for three groups of values 1e6 + (0..0.7) it returns 0.40057 vs exact 0.39678 "
	"(1 % error), where a two-pass sum of n (mean - grand mean)^2 keeps ~1e-9 (the conditioning "
	"bound used for the other statistics on the same data is 1.4e-7)."))
def test_eta_squared_cancellation():
	from stamp.plugins.multiGroups.effectSizeFilters.EtaSquared import EtaSquared
	d = [[1e6 + x for x in (0.1, 0.2, 0.3, 0.4, 0.5)], [1e6 + x for x in (0.2, 0.3, 0.4, 0.5, 0.7)], [1e6 + x for x in (0.0, 0.1, 0.1, 0.2, 0.3)]]
	assert EtaSquared(PREFS).run(d) == pytest.approx(oracle.to_float(oracle.eta_squared(d)), rel=1.4e-7)


@pytest.mark.xfail(strict=True, reason=(
	"stamp/data/tukeyQ_*.txt, row df = 2, is wrong: for k = 2 the exact value is sqrt(2) t(1 - a/2; 2) "
	"= 44.688 at a = 0.001 but the table has 34.714 (14.036 vs 13.902 at a = 0.01, 6.0849 vs "
	"6.0796 at a = 0.05); at k = 29 the tabulated q has exceedance probability 0.00343 for "
	"a = 0.001 (3.4x nominal, anti-conservative) and 0.00696 for a = 0.01 (0.70x, conservative). Used "
	"by Tukey-Kramer when N - k = 2 and by Games-Howell for 2 <= df < 3."))
def test_qtable_df2_row():
	from stamp.metagenomics.stats.distributions.QTable import QTable
	qt = QTable(PREFS)
	bad = []
	for a in ['0.001', '0.01', '0.02', '0.05', '0.1']:
		exact = mp.sqrt(2) * oracle.t_isf(oracle.M(a) / 2, 2, start=stats.t.isf(float(a) / 2, 2))
		v = qt.cv(float(a), 2, 2)
		if not math.isclose(v, float(exact), rel_tol=oracle.qtable_tol_q(3)):
			bad.append((a, v, float(exact)))
	assert not bad, bad


@pytest.mark.xfail(strict=True, raises=IndexError, reason=(
	"QTable.py clamps k > 30 to 30 and indexes values[k - 2], but each table row holds k = 2..29 "
	"(28 values; the header lists 2..30). QTable.cv(0.05, 30, 10) -> IndexError, so Tukey-Kramer "
	"and Games-Howell crash with 30 or more active groups."))
def test_qtable_k30():
	from stamp.metagenomics.stats.distributions.QTable import QTable
	v = QTable(PREFS).cv(0.05, 30, 10)
	exact = oracle.qtukey_isf(oracle.M('0.05'), 30, 10, start=stats.studentized_range.isf(0.05, 30, 10))
	assert v == pytest.approx(float(exact), rel=oracle.qtable_tol_q(10))


# ------------------------------------------------------------------ corrections

@pytest.mark.xfail(strict=True, reason=(
	"Sidak.py never resets numSignFeatures, so 'Number of significant features' accumulates over "
	"successive correct() calls: two calls on [0.01] report 2 instead of 1."))
def test_sidak_significant_count_resets():
	from stamp.plugins.common.multipleComparisonCorrections.Sidak import Sidak
	s = Sidak(PREFS)
	s.correct([0.01], 0.05)
	s.correct([0.01], 0.05)
	assert s.additionalInfo()[0] == ['Number of significant features', 1]
