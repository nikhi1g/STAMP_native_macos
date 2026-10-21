"""Multiple-comparison corrections, called through correct(pValues, alpha) as the app does
(performMultCompCorrection). Inputs: p-value vectors produced by the port on real profiles
(Fisher on the Iron mine profile, ANOVA on Enterotypes, Welch on Skirball) and hand-made vectors
with ties, zeros, ones, tiny values and m = 1."""
import importlib
import math
from fractions import Fraction

import numpy
import pytest

import oracle
from oracle import Checks, PREFS, Q

NAMES = ['NoCorrection', 'Bonferroni', 'Sidak', 'BenjaminiHochbergFDR', 'StoreyFDR']


def plugin(name):
	mod = importlib.import_module('stamp.plugins.common.multipleComparisonCorrections.' + name)
	return getattr(mod, name)(PREFS)


@pytest.fixture(scope='module')
def vectors(sample_tables, multi_inputs, group_inputs):
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.multiGroups.statisticalTests.ANOVA import ANOVA
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	fishers, anova, welch = Fishers(PREFS), ANOVA(PREFS), Welch(PREFS)
	out = {
		'fisher iron (two-sided)': [fishers.hypothesisTest(*t[1:])[1] for t in sample_tables if t[0].startswith('iron/')],
		'anova enterotypes': [anova.hypothesisTest(d)[0] for l, d, n in multi_inputs if l.startswith('enterotypes')],
		'welch skirball (two-sided)': [welch.run(c1, c2, p1, p2, '', 0.95)[1] for l, c1, c2, p1, p2 in group_inputs if l.startswith('skirball burned')],
		'ties': [0.01, 0.01, 0.03, 0.03, 0.03, 0.5, 0.5, 1.0, 1.0],
		'ties reversed order': [1.0, 1.0, 0.5, 0.5, 0.03, 0.03, 0.03, 0.01, 0.01],
		'zeros and ones': [0.0, 0.0, 1.0, 0.2, 1.0],
		'tiny': [1e-300, 1e-200, 1e-17, 1e-10, 0.04],
		'single': [0.03],
		'uniform grid': [i / 101 for i in range(1, 101)],
	}
	for k, v in out.items():
		assert len(v) >= 1 and all(0 <= x <= 1 + 1e-6 for x in v), k
	f = out['fisher iron (two-sided)']
	assert len(f) - len(set(f)) > 5		# real tied p-values (features with identical tables)
	return out


def test_no_correction(vectors):
	nc = plugin('NoCorrection')
	for name, p in vectors.items():
		out = nc.correct(list(p), 0.05)
		assert out == p
		assert nc.additionalInfo() == [['Number of significant features', sum(1 for x in p if x <= 0.05)]]


def test_bonferroni(vectors):
	"""p * m, not capped at 1 (documented upstream behaviour)."""
	b = plugin('Bonferroni')
	ck = Checks()
	for name, p in vectors.items():
		out = b.correct(list(p), 0.05)
		for x, y, o in zip(p, out, oracle.bonferroni(p)):
			ck('corrections/Bonferroni', y, o, ctx=(name, x))
	ck.done()


def test_sidak(vectors):
	"""1 - (1 - p)^m. In double precision 1 - p rounds, so for p below ~1e-8 the relative error of
	the corrected value grows like eps/p (absolute error stays ~m eps): the 1e-12 criterion holds
	through abs_tol; the measured relative error for |oracle| >= 1e-8 is in the summary."""
	s = plugin('Sidak')
	ck = Checks()
	for name, p in vectors.items():
		out = s.correct(list(p), 0.05)
		for x, y, o in zip(p, out, oracle.sidak(p)):
			ck('corrections/Sidak', y, o, ctx=(name, x))
	ck.done()


def test_benjamini_hochberg_upstream_definition(vectors):
	"""Upstream: adjusted p = p * m / rank with no step-up minimum and no cap, where rank is the
	position in ascending order of (p, input index). The oracle derives the ranks independently."""
	bh = plugin('BenjaminiHochbergFDR')
	ck = Checks()
	for name, p in vectors.items():
		out = bh.correct(list(p), 0.05)
		exp = oracle.benjamini_hochberg_upstream(p)
		for x, y, o in zip(p, out, exp):
			ck('corrections/Benjamini-Hochberg (upstream def.)', y, o, ctx=(name, x))
		assert bh.numSignFeatures == sum(1 for o in exp if o < 0.05)
	ck.done()


def test_benjamini_hochberg_tied_ranks():
	"""Proof of upstream's tie handling on a minimal case. indexedList.sort(reverse=True) orders
	[p, index] pairs by p descending and, among equal p, by index descending; the first pair gets
	rank m. So among tied p-values the one with the larger input index gets the larger rank and
	hence the smaller adjusted value: ties are NOT adjusted equally, and the result depends on
	input order. Textbook BH (step-up) gives every tied p-value the same adjusted value."""
	bh = plugin('BenjaminiHochbergFDR')
	assert bh.correct([0.01, 0.01], 0.05) == [0.02, 0.01]				# ranks 1 and 2
	assert bh.correct([0.03, 0.01, 0.03], 0.05) == [0.045, 0.03, 0.03]	# ranks 2, 1, 3
	assert [float(x) for x in oracle.benjamini_hochberg_stepup([0.01, 0.01])] == [0.01, 0.01]
	# order dependence: the same multiset in reverse order permutes which tie gets which value
	p = [0.02, 0.04, 0.02, 0.04]
	fwd = bh.correct(list(p), 0.05)
	rev = bh.correct(list(reversed(p)), 0.05)
	assert sorted(fwd) == sorted(rev) and fwd != list(reversed(rev))
	# and the input list is modified in place (callers pass a fresh list from getColumn)
	q = [0.2, 0.1]
	out = bh.correct(q, 0.05)
	assert out is q


@pytest.fixture
def no_dialog(monkeypatch):
	"""StoreyFDR shows a modal QMessageBox when pi0 < 0.01; record it instead."""
	from PyQt6 import QtWidgets
	shown = []
	monkeypatch.setattr(QtWidgets.QMessageBox, 'information', staticmethod(lambda *a, **k: shown.append(a)))
	return shown


def test_storey_qvalues_given_pi0(vectors, no_dialog):
	"""Deterministic part: given the pi0 the plugin selected, q_(r) = min_{s >= r} pi0 m p_(s)/s.
	pi0 itself must be one of upstream's candidates #{p > lambda} / (m (1 - lambda)) for
	lambda = 0, 0.05, ..., 0.95 (which one is chosen depends on a bootstrap; see below)."""
	st = plugin('StoreyFDR')
	ck = Checks()
	for name, p in vectors.items():
		q = st.correct(list(p), 0.05)
		pi0 = st.estimated_pi0_hat
		cands = oracle.storey_pi0_candidates(p)
		assert any(math.isclose(pi0, oracle.to_float(c), rel_tol=1e-12) for c in cands), (name, pi0)
		for x, y, o in zip(p, q, oracle.storey_qvalues(p, pi0)):
			ck('corrections/Storey q-values (given pi0)', y, o, ctx=(name, x))
		assert st.numSignFeatures == sum(1 for y in q if y <= 0.05)
	ck.done()


def test_storey_pi0_deterministic_case(no_dialog):
	"""All p > 0.95: every bootstrap resample gives pi0(lambda) = 1/(1 - lambda), so the MSE
	against min(1, min_lambda pi0(lambda)) = 1 is minimal (zero) at lambda = 0 and pi0 = 1
	regardless of the random stream; the q-values are then plain step-up BH values."""
	st = plugin('StoreyFDR')
	p = [0.96, 0.97, 0.99, 0.999, 0.98]
	q = st.correct(list(p), 0.05)
	assert st.estimated_pi0_hat == 1.0
	for y, o in zip(q, oracle.benjamini_hochberg_stepup(p)):
		oracle.check('corrections/Storey deterministic pi0 = 1', y, o)


def test_storey_lambda_selection_replayed(no_dialog, monkeypatch, vectors):
	"""The bootstrap that selects lambda draws from numpy's global RNG after an unseeded
	numpy.random.seed() (fresh OS entropy every call, so results differ run to run). With
	seed() neutralised and the stream seeded, the oracle replays the same draws and recomputes
	every bootstrap pi0 and MSE in exact rationals; the selected pi0 must match exactly.
	Approximation note: Storey et al. (2004) choose lambda by bootstrap MSE; upstream uses 100
	resamples, so the choice is itself random -- this test checks the arithmetic, not the
	statistical properties of the estimate."""
	from stamp.plugins.common.multipleComparisonCorrections import StoreyFDR as mod
	monkeypatch.setattr(mod.numpy.random, 'seed', lambda *a: None)
	st = plugin('StoreyFDR')
	for name in ['fisher iron (two-sided)', 'anova enterotypes', 'uniform grid']:
		p = vectors[name]
		m = len(p)
		numpy.random.RandomState  # noqa
		numpy.random.set_state(numpy.random.RandomState(12345).get_state())
		st.correct(list(p), 0.05)
		got = st.estimated_pi0_hat
		# replay
		numpy.random.set_state(numpy.random.RandomState(12345).get_state())
		cands = oracle.storey_pi0_candidates(p)
		min_pi0 = min([Fraction(1)] + cands)
		best, best_lam = None, None
		for lam in oracle.STOREY_LAMBDAS:
			mse = Fraction(0)
			for _ in range(100):
				boot = [p[numpy.random.randint(0, m)] for _ in range(m)]
				b = Fraction(sum(1 for x in boot if Q(x) > lam), 1) / (m * (1 - lam))
				mse += (b - min_pi0) ** 2
			mse /= 100
			if best is None or mse < best:
				best, best_lam = mse, lam
		exp = Fraction(sum(1 for x in p if Q(x) > best_lam), 1) / (m * (1 - best_lam))
		oracle.check('corrections/Storey pi0 (replayed bootstrap)', got, exp)
