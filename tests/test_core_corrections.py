"""Multiple-comparison corrections.

Input: the 247 Fisher's exact p-values of the iron-mine two-sample comparison (plus a small
hand-made list). Benjamini-Hochberg and Storey are cross-checked against
scipy.stats.false_discovery_control; the family-wise methods against their closed forms.
"""
import os

import numpy as np
import pytest
from scipy import stats

from stamp.metagenomics.fileIO.StampIO import StampIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IRON = os.path.join(ROOT, 'stamp', 'examples', 'IronMineEdwards', 'EdwardsIronMine.spf')
PREFS = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15}
REL = 1e-9


def approx(x):
	return pytest.approx(x, rel=REL, abs=1e-300)


@pytest.fixture(scope='module')
def results():
	from stamp.metagenomics.stats.SampleStatsTests import SampleStatsTests
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptotic import DiffBetweenPropAsymptotic
	tree, err = StampIO(PREFS).read(IRON)
	sp = tree.createSampleProfile('Red', 'Black', 'Entire sample', 'Subsystem', 'Remove unclassified reads')
	t = SampleStatsTests(PREFS)
	t.run(Fishers(PREFS), 'Two-sided', DiffBetweenPropAsymptotic(PREFS), 0.95, sp)
	return t.results


@pytest.fixture
def pValues(results):
	return results.getColumn('pValues', False)


def test_no_correction(pValues):
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	nc = NoCorrection(PREFS)
	assert nc.correct(list(pValues), 0.05) == pValues
	assert nc.additionalInfo() == [['Number of significant features', sum(p <= 0.05 for p in pValues)]]


def test_bonferroni(pValues):
	from stamp.plugins.common.multipleComparisonCorrections.Bonferroni import Bonferroni
	b = Bonferroni(PREFS)
	m = len(pValues)
	corrected = b.correct(list(pValues), 0.05)
	assert corrected == [approx(p * m) for p in pValues]  # upstream does not cap at 1
	assert b.additionalInfo() == [['Number of significant features', sum(p * m <= 0.05 for p in pValues)],
								['Corrected error rate', approx(0.05 / m)]]


def test_sidak(pValues):
	from stamp.plugins.common.multipleComparisonCorrections.Sidak import Sidak
	s = Sidak(PREFS)
	m = len(pValues)
	corrected = s.correct(list(pValues), 0.05)
	assert corrected == [approx(1 - (1 - p) ** m) for p in pValues]
	assert s.additionalInfo()[1] == ['Corrected error rate', approx(1 - 0.95 ** (1 / m))]


def test_holm_bonferroni(pValues):
	from stamp.plugins.common.multipleComparisonCorrections.additional.HolmBonferroni import HolmBonferroni
	hb = HolmBonferroni(PREFS)
	m = len(pValues)
	corrected = hb.correct(list(pValues), 0.05)
	# Holm step-down: reject the i-th smallest while p_(i) <= alpha / (m - i)
	order = np.argsort(pValues, kind='stable')
	rejected = 0
	for i, idx in enumerate(order):
		if pValues[idx] > 0.05 / (m - i):
			break
		rejected += 1
	assert hb.numSignFeatures == rejected > 0
	for i, idx in enumerate(order):
		assert corrected[idx] == (pValues[idx] if i < rejected else float('inf'))
	# upstream bug kept for parity: when every feature is significant nonSignIndex is unbound
	with pytest.raises(UnboundLocalError):
		hb.correct([1e-9, 1e-8], 0.05)


def test_benjamini_hochberg_matches_scipy_after_step_up(pValues):
	"""STAMP reports p * m / rank without the step-up minimum or the cap at 1; applying the
	running minimum (from the largest p down) to its output reproduces scipy's BH values."""
	from stamp.plugins.common.multipleComparisonCorrections.BenjaminiHochbergFDR import BenjaminiHochbergFDR
	bh = BenjaminiHochbergFDR(PREFS)
	m = len(pValues)
	q = np.array(bh.correct(list(pValues), 0.05))
	order = np.argsort(pValues, kind='stable')
	ranks = np.empty(m)
	ranks[order] = np.arange(1, m + 1)
	# ties: STAMP sorts [p, index] pairs descending, so tied p-values are ranked by index,
	# exactly as a stable ascending argsort does
	assert _ties(pValues)
	assert np.allclose(q, np.array(pValues) * m / ranks, rtol=REL, atol=0)
	stepped = np.empty(m)
	stepped[order] = np.minimum(1.0, np.minimum.accumulate(q[order][::-1])[::-1])
	assert stepped == pytest.approx(_bh(pValues), rel=REL)
	assert bh.numSignFeatures == int(np.sum(q < 0.05))


def _bh(values):
	# Fisher p-values summed from pmfs can exceed 1 by ~1e-10; scipy rejects them
	return stats.false_discovery_control(np.minimum(values, 1.0), method='bh')


def _ties(values):
	return len(set(values)) != len(values)


def test_storey_fdr(pValues, monkeypatch):
	"""Storey's q-values are pi0 times the step-up BH values. pi0 is chosen by bootstrap
	(upstream reseeds numpy from OS entropy; the reseed is disabled here to pin the value)."""
	from stamp.plugins.common.multipleComparisonCorrections.StoreyFDR import StoreyFDR
	np.random.seed(2)
	monkeypatch.setattr(np.random, 'seed', lambda *args: None)
	storey = StoreyFDR(PREFS)
	q = storey.correct(list(pValues), 0.05)
	pi0 = storey.estimated_pi0_hat
	assert 0.01 < pi0 <= 1.0  # below 0.01 upstream opens a QMessageBox
	lambdas = np.arange(0.0, 0.951, 0.05)
	candidates = [np.sum(np.array(pValues) > lam) / (len(pValues) * (1 - lam)) for lam in lambdas]
	assert any(pi0 == pytest.approx(c, rel=REL) for c in candidates)
	assert q == pytest.approx(pi0 * _bh(pValues), rel=REL)
	assert storey.additionalInfo() == [['Number of significant features', sum(x <= 0.05 for x in q)], ['Estimated pi_0', pi0]]
	assert pi0 == pytest.approx(STOREY_PI0_SEED2, rel=REL)


def test_upstream_list():
	from stamp.plugins.common.multipleComparisonCorrections.BenjaminiHochbergFDR import BenjaminiHochbergFDR
	ps = [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1]
	assert BenjaminiHochbergFDR(PREFS).correct(list(ps), 0.05) == pytest.approx(
		list(stats.false_discovery_control(ps, method='bh')), rel=REL)


def test_results_apply_correction(results, pValues):
	from stamp.plugins.common.multipleComparisonCorrections.Bonferroni import Bonferroni
	results.performMultCompCorrection(Bonferroni(PREFS))
	m = len(pValues)
	assert results.getColumn('pValuesCorrected', False) == [approx(p * m) for p in pValues]
	assert results.multCompCorrectionInfo[0][0] == 'Number of significant features'


STOREY_PI0_SEED2 = 0.6477732793522267
