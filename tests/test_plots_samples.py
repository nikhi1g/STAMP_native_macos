"""Two-sample ("samples" mode) plot plugins on real Enterotypes results, headless.

Covers every plot in stamp/plugins/samples/plots (plus the examples/ plugin): plotting with
and without a multiple-comparison correction, highlighted features, every sorting field /
option the settings expose, the empty-results path, 300 dpi export to png/pdf/svg, and each
configure dialog's OK path (the dialog's buttonBox.accepted signal, which the .ui wires to
QDialog.accept) round-tripped through QSettings.
"""
import copy
import itertools
import os
import struct
import sys
import types

import numpy as np
import pytest
from PyQt6 import QtCore, QtGui, QtWidgets

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stamp', 'examples', 'EnterotypesArumugam')

EMPTY_LABEL = 'No active features or degenerate plot'


# ---------------------------------------------------------------------------------------
# fixtures

def _importPlotEventHandler():
	# ponytail: stamp/plugins/PlotEventHandler.py (not owned by this worker) still imports the
	# Qt 4 bindings at module level, and ScatterPlot imports it. Until it is ported, satisfy
	# that one import with a stand-in whose QtGui is PyQt6.QtWidgets (the handler touches Qt
	# only on a mouse click, which these tests never trigger). Remove once it is ported.
	try:
		import stamp.plugins.PlotEventHandler  # noqa: F401
	except ModuleNotFoundError as e:
		legacy = e.name
		if legacy is None or not legacy.startswith('PyQt') or legacy == 'PyQt6':
			raise
		shim = types.ModuleType(legacy)
		shim.QtGui = QtWidgets
		sys.modules[legacy] = shim
		try:
			import stamp.plugins.PlotEventHandler  # noqa: F401
		finally:
			del sys.modules[legacy]


def makePreferences(highlighted=()):
	settings = privateSettings()
	prefs = {}
	prefs['Settings'] = settings
	prefs['Pseudocount'] = 0.5
	prefs['Replicates'] = 1000
	prefs['Truncate feature names'] = True
	prefs['Length of truncated feature names'] = 50
	prefs['Axes colour'] = QtGui.QColor('#7f7f7f')
	prefs['All other samples colour'] = QtGui.QColor('#7f7f7f')
	prefs['Minimum reported p-value exponent'] = -15.0
	prefs['Sample 1 colour'] = QtGui.QColor(128, 177, 211)
	prefs['Sample 2 colour'] = QtGui.QColor(253, 180, 98)
	prefs['Group colours'] = {}
	prefs['Highlighted sample features'] = list(highlighted)
	prefs['Highlighted group features'] = []
	prefs['Highlighted multiple group features'] = []
	prefs['Selected group feature'] = ''
	prefs['Selected multiple group feature'] = ''
	prefs['Last directory'] = ''
	return prefs


def privateSettings():
	# Native QSettings('BeikoLab', 'STAMP-test') lives in ~/Library/Preferences and is shared
	# with other suites (and concurrently running worktrees), so clear() and round-trips race.
	# Same organization/application, but an INI store under a private directory (set below);
	# values are still stored as strings, as in a macOS plist.
	return QtCore.QSettings(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, 'BeikoLab', 'STAMP-test')


# rcParams STAMP.py sets at start-up (module level and MainWindow.__init__)
STAMP_RC = {'svg.fonttype': 'none', 'font.size': 8, 'axes.titlesize': 8, 'axes.labelsize': 8,
						'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 8}


@pytest.fixture(scope='module', autouse=True)
def stampRcParams():
	import matplotlib
	with matplotlib.rc_context(STAMP_RC):
		yield


@pytest.fixture(scope='module', autouse=True)
def privateSettingsStore(tmp_path_factory):
	QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, str(tmp_path_factory.mktemp('qsettings')))
	yield


@pytest.fixture(autouse=True)
def cleanSettings(qapp, privateSettingsStore):
	settings = privateSettings()
	settings.clear()
	settings.sync()
	yield
	settings.clear()
	settings.sync()


@pytest.fixture(scope='module')
def baseResults():
	"""Fishers + DP (difference) and RP (ratio) CIs on genera of the first two Enterotypes samples."""
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.stats.SampleStatsTests import SampleStatsTests
	from stamp.plugins.samples.statisticalTests.Fishers import Fishers
	from stamp.plugins.samples.confidenceIntervalMethods.DiffBetweenPropAsymptotic import DiffBetweenPropAsymptotic
	from stamp.plugins.samples.confidenceIntervalMethods.RatioProportions import RatioProportions
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	from stamp.plugins.common.multipleComparisonCorrections.BenjaminiHochbergFDR import BenjaminiHochbergFDR

	prefs = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15.0}	# no QSettings: results are deep-copied
	tree, err = StampIO(prefs).read(os.path.join(EX, 'Enterotypes.profile.spf'))
	names = tree.sampleNames
	profile = tree.createSampleProfile(names[0], names[1], 'Entire sample', tree.hierarchyHeadings[-1], 'Remove unclassified reads')

	out = {}
	for ciName, ciClass in [('DP', DiffBetweenPropAsymptotic), ('RP', RatioProportions)]:
		t = SampleStatsTests(prefs)
		t.run(Fishers(prefs), 'Two-sided', ciClass(prefs), 0.95, profile)
		for corrName, corrClass in [('none', NoCorrection), ('BH', BenjaminiHochbergFDR)]:
			r = copy.deepcopy(t.results)
			r.performMultCompCorrection(corrClass(prefs))
			r.selectAllFeautres()
			out[(ciName, corrName)] = r
	return out


def results(baseResults, ci='DP', corr='BH', signLevel=0.05):
	"""Fresh (deep-copied) results with the STAMP p-value filter applied; plots sort activeData in place."""
	r = copy.deepcopy(baseResults[(ci, corr)])
	r.filterFeatures(signLevel, None, 0, 0, None, 0, 0, None, 0, 'AND', None, 0)
	return r


def emptyInputs(baseResults):
	"""Results with no active features and a profile with no features."""
	r = results(baseResults, signLevel=-1.0)
	assert len(r.activeData) == 0
	profile = copy.copy(r.profile)
	profile.profileDict = {}
	return profile, r


def pngSize(path):
	with open(path, 'rb') as f:
		head = f.read(24)
	assert head[:8] == b'\x89PNG\r\n\x1a\n'
	return struct.unpack('>II', head[16:24])


def assertSaves(plot, tmp_path, stem):
	w, h = plot.fig.get_size_inches()
	for ext in ['png', 'pdf', 'svg']:
		fn = str(tmp_path / (stem + '.' + ext))
		plot.savePlot(fn, dpi=300)
		assert os.path.exists(fn), fn
		assert os.path.getsize(fn) > 2000, fn
	pw, ph = pngSize(str(tmp_path / (stem + '.png')))
	assert abs(pw - w * 300) <= 1 and abs(ph - h * 300) <= 1, (pw, ph, w, h)


def assertEmpty(plot):
	assert len(plot.fig.axes) == 1
	ax = plot.fig.axes[0]
	assert ax.get_xlabel() == EMPTY_LABEL and ax.get_ylabel() == EMPTY_LABEL
	assert tuple(plot.fig.get_size_inches()) == (6.0, 4.0)


def tickTexts(labels):
	return [t.get_text() for t in labels]


def redLabels(labels):
	return [t.get_text() for t in labels if t.get_color() == 'red']


def configureWith(monkeypatch, edit):
	"""Replace the blocking ConfigureDialog.exec() by: edit widgets, then take the OK path.

	OK is the dialog's buttonBox.accepted signal, which the generated UI connects to
	QDialog.accept; exec() then returns the dialog's result code, as Qt does."""
	from stamp.plugins.samples.AbstractSamplePlotPlugin import ConfigureDialog
	seen = {}

	def fakeExec(dlg):
		seen['dlg'] = dlg
		edit(dlg.ui)
		dlg.ui.buttonBox.accepted.emit()
		return dlg.result()
	monkeypatch.setattr(ConfigureDialog, 'exec', fakeExec)
	return seen


def answer(monkeypatch, button):
	calls = []

	def question(*args, **kwargs):
		calls.append(args)
		return button
	monkeypatch.setattr(QtWidgets.QMessageBox, 'question', staticmethod(question))
	return calls


# ---------------------------------------------------------------------------------------
# plugin discovery and interface

PLOT_FILES = ['Bar', 'ExtendedErrorBar', 'MultCompCorrectionPlots', 'ProfileBarPlots', 'ScatterPlot', 'SeqHistogram', 'pValueHistogram']


def loadClass(name, module='stamp.plugins.samples.plots.'):
	import importlib
	if name == 'ScatterPlot':
		_importPlotEventHandler()
	return getattr(importlib.import_module(module + name), name)


def test_every_plot_file_is_covered():
	import stamp.plugins.samples.plots as pkg
	files = sorted(f[:-3] for f in os.listdir(os.path.dirname(pkg.__file__)) if f.endswith('.py') and f != '__init__.py')
	assert files == sorted(PLOT_FILES)


@pytest.mark.parametrize('name, title, kind', [
	('Bar', 'Bar plot', 'Statistical'),
	('ExtendedErrorBar', 'Extended error bar', 'Statistical'),
	('MultCompCorrectionPlots', 'Multiple comparison plots', 'Statistical'),
	('ProfileBarPlots', 'Profile bar plot', 'Exploratory'),
	('ScatterPlot', 'Scatter plot', 'Exploratory'),
	('SeqHistogram', 'Sequence histogram', 'Exploratory'),
	('pValueHistogram', 'p-value histogram', 'Statistical'),
])
def test_interface(qapp, baseResults, tmp_path, name, title, kind):
	cls = loadClass(name)
	plot = cls(makePreferences())
	assert isinstance(plot, QtWidgets.QWidget)
	assert plot.name == title and plot.type == kind
	for attr in ['plot', 'configure', 'savePlot', 'mirrorProperties', 'mouseEventCallback', 'emptyAxis', 'get_width_height', 'clear']:
		assert callable(getattr(plot, attr)), attr
	assert plot.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed

	# PlotsManager.display() path with no data, then the empty-results path
	plot.emptyAxis()
	assertEmpty(plot)
	profile, r = emptyInputs(baseResults)
	plot.plot(profile, r)
	assertEmpty(plot)
	assert plot.get_width_height() == (6 * 96, 4 * 96)
	assertSaves(plot, tmp_path, name + '_empty')

	# PlotsManager.sendToNewWindow(): new instance mirrors the current one, then plots
	r = results(baseResults)
	plot.plot(r.profile, r)
	twin = cls(plot.preferences)
	twin.mirrorProperties(plot)
	twin.plot(r.profile, results(baseResults))
	assert twin.get_width_height() == plot.get_width_height()

	# mouseEventCallback replaces the previous callback
	from matplotlib.backend_bases import MouseEvent
	hits = []
	plot.mouseEventCallback(lambda e: hits.append(1))
	plot.mouseEventCallback(lambda e: hits.append(2))
	MouseEvent('button_press_event', plot, 10, 10, button=1)._process()
	assert hits == [2]


# ---------------------------------------------------------------------------------------
# Bar plot

BAR_FIELDS = ['Effect size', 'Number of sequences', 'Number of parental sequences', 'p-values', 'p-values (corrected)', 'Proportion of sequences (%)']


@pytest.mark.parametrize('field, bSort, corr, ci', [(f, s, c, ci) for f in BAR_FIELDS for s in [True, False] for c in ['none', 'BH'] for ci in ['DP', 'RP'] if ci == 'DP' or f == 'Effect size'])
def test_bar(qapp, baseResults, field, bSort, corr, ci):
	from stamp.plugins.samples.plots.Bar import Bar
	r = results(baseResults, ci=ci, corr=corr)
	highlight = [r.activeData[3][0]]
	plot = Bar(makePreferences(highlight))
	plot.fieldToPlot = field
	plot.bSortFeatures = bSort
	plot.plot(r.profile, r)

	n = len(r.activeData)
	twoFields = field in ['Number of sequences', 'Number of parental sequences', 'Proportion of sequences (%)']
	assert len(plot.fig.axes) == 1
	ax = plot.fig.axes[0]
	assert len(ax.patches) == (2 * n if twoFields else n)
	assert tickTexts(ax.get_yticklabels()) == r.getColumn('Features')
	assert redLabels(ax.get_yticklabels()) == highlight
	if field == 'Effect size':
		label = r.confIntervMethod.plotLabel
		assert ax.get_xlabel() == ('log(' + label + ')' if ci == 'RP' else label)
	else:
		assert ax.get_xlabel() == field
	assert (ax.get_legend() is not None) == twoFields  # default legend position 0 ('best')

	# bars are edge-aligned on integer rows, as with matplotlib 1.4
	ys = sorted(p.get_y() for p in ax.patches)
	assert ys[0] == 0.0
	assert np.allclose(ax.get_yticks(), np.arange(n) + (0.35 if twoFields else 0.5 * 0.35))

	if bSort and field in ['Number of sequences', 'Proportion of sequences (%)', 'Number of parental sequences']:
		col = {'Number of sequences': 'Seq1', 'Number of parental sequences': 'ParentalSeq1', 'Proportion of sequences (%)': 'RelFreq1'}[field]
		values = r.getColumn(col)
		assert values == sorted(values)

	# y ticks off, x ticks only at the bottom (upstream tick1On/tick2On), after a full draw
	plot.draw()
	# layout: label extents measured at 8 pt (STAMP's rcParams) keep the feature names inside the figure
	renderer = plot.get_renderer()
	assert min(l.get_window_extent(renderer).x0 for l in ax.get_yticklabels()) >= 0
	assert ax.yaxis.get_ticklabels()[0].get_fontsize() == 8
	for t in ax.yaxis.majorTicks:
		assert not t.tick1line.get_visible() and not t.tick2line.get_visible()
	for t in ax.xaxis.majorTicks:
		assert t.tick1line.get_visible() and not t.tick2line.get_visible()


@pytest.mark.parametrize('legendPos', [0, 1, 7, 4, 2, 6, 3, -1])
def test_bar_legend_positions(qapp, baseResults, legendPos):
	from stamp.plugins.samples.plots.Bar import Bar
	r = results(baseResults)
	plot = Bar(makePreferences())
	plot.legendPos = legendPos
	plot.plot(r.profile, r)
	legend = plot.fig.axes[0].get_legend()
	if legendPos == -1:
		assert legend is None
	else:
		assert legend._loc == legendPos
		assert tickTexts(legend.get_texts()) == r.profile.sampleNames[:2]
		assert legend.get_frame().get_linewidth() == 0


def test_bar_many_features_prompt(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.Bar import Bar
	r = results(baseResults, signLevel=None)
	assert len(r.activeData) > 200
	plot = Bar(makePreferences())
	calls = answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.No)
	plot.plot(r.profile, r)
	assert len(calls) == 1
	assertEmpty(plot)
	answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Yes)
	plot.plot(r.profile, r)
	assert len(plot.fig.axes[0].patches) == 2 * len(r.activeData)


def test_bar_truncated_names(qapp, baseResults):
	from stamp.plugins.samples.plots.Bar import Bar
	r = results(baseResults)
	feature = max(r.getColumn('Features'), key=len)
	prefs = makePreferences([feature])
	prefs['Length of truncated feature names'] = 5
	plot = Bar(prefs)
	plot.plot(r.profile, r)
	labels = tickTexts(plot.fig.axes[0].get_yticklabels())
	assert all(len(l) <= 8 for l in labels)
	assert redLabels(plot.fig.axes[0].get_yticklabels()) == [feature[0:5] + '...']


def test_bar_configure(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.Bar import Bar
	r = results(baseResults)
	plot = Bar(makePreferences())

	def edit(ui):
		assert ui.cboFieldToPlot.currentText() == 'Proportion of sequences (%)'
		assert ui.radioLegendPosBest.isChecked()
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.chkSort.setChecked(False)
		ui.spinFigWidth.setValue(9.5)
		ui.spinFigRowHeight.setValue(0.3)
		ui.radioLegendPosLowerLeft.setChecked(True)
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	assert (plot.fieldToPlot, plot.bSortFeatures, plot.figWidth, plot.figHeightPerRow, plot.legendPos) == ('Number of sequences', False, 9.5, 0.3, 3)
	assert plot.fig.get_size_inches()[0] == 9.5
	assert plot.fig.axes[0].get_legend()._loc == 3

	again = Bar(makePreferences())
	assert (again.fieldToPlot, again.bSortFeatures, again.figWidth, again.figHeightPerRow, again.legendPos) == ('Number of sequences', False, 9.5, 0.3, 3)

	# every legend radio button maps back to its matplotlib location code
	for radio, code in [('radioLegendPosBest', 0), ('radioLegendPosUpperRight', 1), ('radioLegendPosCentreRight', 7), ('radioLegendPosLowerRight', 4),
											('radioLegendPosUpperLeft', 2), ('radioLegendPosCentreLeft', 6), ('radioLegendPosLowerLeft', 3), ('radioLegendPosNone', -1)]:
		configureWith(monkeypatch, lambda ui, radio=radio: getattr(ui, radio).setChecked(True))
		plot.configure(r.profile, results(baseResults))
		assert plot.legendPos == code


# ---------------------------------------------------------------------------------------
# Extended error bar

EEB_GRID = list(itertools.product(['p-values', 'Effect sizes', 'Feature labels'], [True, False], [True, False], [True, False]))


@pytest.mark.parametrize('sortingField, bBar, bPLabels, bCorrected', EEB_GRID)
@pytest.mark.parametrize('ci, corr', [('DP', 'BH'), ('RP', 'none')])
def test_extended_error_bar(qapp, baseResults, ci, corr, sortingField, bBar, bPLabels, bCorrected):
	from stamp.plugins.samples.plots.ExtendedErrorBar import ExtendedErrorBar
	r = results(baseResults, ci=ci, corr=corr)
	highlight = [r.activeData[1][0]]
	plot = ExtendedErrorBar(makePreferences(highlight))
	plot.sortingField = sortingField
	plot.bShowBarPlot = bBar
	plot.bShowPValueLabels = bPLabels
	plot.bShowCorrectedPvalues = bCorrected
	plot.plot(r.profile, r)

	n = len(r.activeData)
	features = r.getColumn('Features')
	if sortingField == 'Feature labels':
		assert features == sorted(features, key=str.lower, reverse=True)
	elif sortingField == 'p-values':
		p = r.getColumn('pValues')
		assert p == sorted(p, reverse=True)

	axes = plot.fig.axes
	assert len(axes) == 1 + int(bBar) + int(bPLabels)
	axErrorbar = axes[1] if bBar else axes[0]
	assert axErrorbar.get_title() == '95% confidence intervals'
	assert axErrorbar.get_xlabel() == r.confIntervMethod.plotLabel
	# error bar line plus the markers of features dominating in sample 2
	assert len(axErrorbar.lines) >= 2
	labelAxes = axes[0]
	assert tickTexts(labelAxes.get_yticklabels())[:n] == features
	assert redLabels(labelAxes.get_yticklabels()) == highlight
	if bBar:
		assert len([p for p in axes[0].patches if p.get_height() == pytest.approx(0.3)]) == 2 * n	# plus axhspan row shading
		assert axes[0].get_xlabel() == plot.percentageOrSeqCount
		assert all(not t.get_visible() for t in axErrorbar.yaxis.majorTicks)
	if bPLabels:
		axRight = axes[-1]
		title = 'q-value' if corr == 'BH' else 'p-value'
		if bCorrected:	# upstream compares the method ('Per comparison error rate') with 'No correction', so this is always appended
			title += ' (corrected)'
		assert axRight.get_ylabel() == title
		assert tickTexts(axRight.get_yticklabels()) == r.getColumnAsStr('pValuesCorrected' if bCorrected else 'pValues')

	plot.draw()
	# no left tick marks on the error bar axes (twinx() would re-enable them in matplotlib 3)
	assert all(not l.get_visible() for l in axErrorbar.yaxis.get_ticklines()[0::2])
	assert all(not t.tick2line.get_visible() for t in axErrorbar.xaxis.majorTicks)
	if not plot.bCustomLimits:
		assert (plot.minX, plot.maxX) == tuple(axErrorbar.get_xlim())


@pytest.mark.parametrize('percentageOrSeqCount', ['Proportion (%)', 'Sequences'])
@pytest.mark.parametrize('legendPos', [-1, 2, 3, 4, 8])
def test_extended_error_bar_options(qapp, baseResults, percentageOrSeqCount, legendPos):
	from stamp.plugins.samples.plots.ExtendedErrorBar import ExtendedErrorBar
	r = results(baseResults)
	plot = ExtendedErrorBar(makePreferences())
	plot.percentageOrSeqCount = percentageOrSeqCount
	plot.legendPos = legendPos
	plot.bCustomLimits = True
	plot.minX, plot.maxX = -20.0, 15.0
	plot.markerSize = 50
	plot.plot(r.profile, r)
	axNumSeq, axErrorbar = plot.fig.axes[0], plot.fig.axes[1]
	assert tuple(axErrorbar.get_xlim()) == (-20.0, 15.0)
	assert axNumSeq.get_xlabel() == percentageOrSeqCount
	assert len(axNumSeq.get_xticklabels()) == 2
	assert len(plot.fig.legends) == (0 if legendPos == -1 else 1)
	if legendPos != -1:
		assert tickTexts(plot.fig.legends[0].get_texts()) == r.profile.sampleNames[:2]
	assert axErrorbar.lines[0].get_markersize() == pytest.approx(np.sqrt(50))
	# bar plot rows edge-aligned: sample 1 bar spans [i, i+0.3], sample 2 bar [i-0.3, i]
	ys = sorted(round(p.get_y(), 6) for p in axNumSeq.patches if p.get_height() == pytest.approx(0.3))
	assert ys[0] == -0.3 and ys[1] == 0.0
	heightBottom = 0.56 if legendPos in [3, 4, 8] else 0.4
	assert plot.fig.get_size_inches()[1] == pytest.approx(0.2 * len(r.activeData) + heightBottom + 0.25)


def test_extended_error_bar_large(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.ExtendedErrorBar import ExtendedErrorBar
	r = results(baseResults, signLevel=None)
	plot = ExtendedErrorBar(makePreferences())
	calls = answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.No)
	plot.plot(r.profile, r)
	assert len(calls) == 1
	assertEmpty(plot)

	r = results(baseResults)
	plot.figHeightPerRow = 10.0	# > 256 inches in total
	calls = answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Ok)
	plot.plot(r.profile, r)
	assert calls[0][1] == 'Excessively large plot'
	assertEmpty(plot)


def test_extended_error_bar_configure(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.ExtendedErrorBar import ExtendedErrorBar
	r = results(baseResults)
	plot = ExtendedErrorBar(makePreferences())
	plot.plot(r.profile, r)

	def edit(ui):
		assert ui.cboSortingField.currentText() == 'p-values'
		assert ui.radioLegendPosNone.isChecked()
		ui.cboSortingField.setCurrentIndex(ui.cboSortingField.findText('Effect sizes'))
		ui.spinFigWidth.setValue(8.0)
		ui.spinFigRowHeight.setValue(0.25)
		ui.chkShowBarPlot.setChecked(False)
		ui.chkPValueLabels.setChecked(False)
		ui.chkCorrectedPvalues.setChecked(False)
		ui.chkCustomLimits.click()	# .ui wiring enables the limit spin boxes
		assert ui.spinMinimumX.isEnabled() and ui.spinMaximumX.isEnabled()
		ui.spinMinimumX.setValue(-25.0)
		ui.spinMaximumX.setValue(12.5)
		ui.spinMarkerSize.setValue(40)
		ui.cboPercentageOrSeqCount.setCurrentIndex(ui.cboPercentageOrSeqCount.findText('Sequences'))
		ui.radioLegendPosLowerCentre.setChecked(True)
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	assert QtWidgets.QApplication.overrideCursor() is None
	state = lambda p: (p.sortingField, p.figWidth, p.figHeightPerRow, p.bShowBarPlot, p.bShowPValueLabels, p.bShowCorrectedPvalues,
										p.bCustomLimits, p.minX, p.maxX, p.markerSize, p.percentageOrSeqCount, p.legendPos)
	expected = ('Effect sizes', 8.0, 0.25, False, False, False, True, -25.0, 12.5, 40, 'Sequences', 8)
	assert state(plot) == expected
	assert len(plot.fig.axes) == 1 and tuple(plot.fig.axes[0].get_xlim()) == (-25.0, 12.5)
	assert len(plot.fig.legends) == 1

	again = ExtendedErrorBar(makePreferences())
	# upstream stores 'use custom limits' under '<name>use custom limits' (no '/'), so it does not round-trip
	assert state(again) == expected[:6] + (False,) + expected[7:]

	for radio, code in [('radioLegendPosUpperLeft', 2), ('radioLegendPosLowerLeft', 3), ('radioLegendPosLowerCentre', 8), ('radioLegendPosLowerRight', 4), ('radioLegendPosNone', -1)]:
		configureWith(monkeypatch, lambda ui, radio=radio: getattr(ui, radio).setChecked(True))
		plot.configure(r.profile, results(baseResults))
		assert plot.legendPos == code


# ---------------------------------------------------------------------------------------
# Multiple comparison correction plots

@pytest.mark.parametrize('corr', ['none', 'BH'])
@pytest.mark.parametrize('bLog', [False, True])
def test_mult_comp_correction(qapp, baseResults, corr, bLog):
	from stamp.plugins.samples.plots.MultCompCorrectionPlots import MultCompCorrectionPlots
	r = results(baseResults, corr=corr, signLevel=None)
	plot = MultCompCorrectionPlots(makePreferences())
	plot.yAxisLogScale = bLog
	plot.plot(r.profile, r)
	ax1, ax2, ax3 = plot.fig.axes
	xLabel = 'q-value' if corr == 'BH' else 'corrected p-value'
	assert [a.get_xlabel() for a in plot.fig.axes] == [xLabel] * 3
	assert ax2.get_ylabel() == ('p-value' if corr == 'BH' else 'raw p-value')
	assert ax1.get_ylabel() == 'Number of features' and ax3.get_ylabel() == '# significant features'
	assert len(ax1.patches) == 10	# bins of width 0.01 up to 0.1
	assert ax1.get_yscale() == ('log' if bLog else 'linear')
	assert tuple(ax1.get_xlim()) == (0, 0.1) and tuple(ax2.get_xlim()) == (0, 1.0) and tuple(ax3.get_xlim()) == (0, 0.1)
	assert plot.xMax == max(r.getColumn('pValuesCorrected'))
	corrected = sorted(r.getColumn('pValuesCorrected'))
	assert len(ax2.lines[0].get_xdata()) == len([v for v in corrected if v <= 1.0])
	assert len(ax3.lines[0].get_xdata()) == len([v for v in corrected if v <= 0.1]) + 1
	plot.draw()
	for ax in plot.fig.axes:
		assert all(t.tick1line.get_visible() and not t.tick2line.get_visible() for t in ax.xaxis.majorTicks + ax.yaxis.majorTicks)


def test_mult_comp_correction_configure(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.MultCompCorrectionPlots import MultCompCorrectionPlots
	r = results(baseResults, signLevel=None)
	plot = MultCompCorrectionPlots(makePreferences())
	plot.plot(r.profile, r)
	xMax = plot.xMax

	def edit(ui):
		ui.spinFigWidth.setValue(8.5)
		ui.spinFigHeight.setValue(4.0)
		ui.spinBinWidth.setValue(0.02)
		ui.chkLogScale.setChecked(True)
		ui.btnXmaxFig1.click()
		ui.btnXmaxFig2.click()
		ui.btnXmaxFig3.click()
		assert ui.spinXlimitFig1.value() == pytest.approx(round(xMax, ui.spinXlimitFig1.decimals()))
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	state = lambda p: (p.figWidth, p.figHeight, p.binWidth, p.yAxisLogScale, p.xLimitFig1, p.xLimitFig2, p.xLimitFig3)
	s = state(plot)
	assert s[:4] == (8.5, 4.0, 0.02, True)
	assert s[4] == s[5] == s[6] and s[4] == pytest.approx(xMax, abs=1e-2)
	assert tuple(plot.fig.get_size_inches()) == (8.5, 4.0)
	assert state(MultCompCorrectionPlots(makePreferences())) == s


# ---------------------------------------------------------------------------------------
# p-value histogram

@pytest.mark.parametrize('field', ['p-values', 'p-values (corrected)'])
@pytest.mark.parametrize('bLog, bInset, bInsetLog', [(False, True, False), (True, True, True), (False, False, False), (True, False, False)])
@pytest.mark.parametrize('corr', ['none', 'BH'])
def test_pvalue_histogram(qapp, baseResults, field, bLog, bInset, bInsetLog, corr):
	from stamp.plugins.samples.plots.pValueHistogram import pValueHistogram
	r = results(baseResults, corr=corr, signLevel=None)
	plot = pValueHistogram(makePreferences())
	plot.fieldToPlot = field
	plot.yAxisLogScale = bLog
	plot.bShowInset = bInset
	plot.insetLogScale = bInsetLog
	plot.plot(r.profile, r)
	assert len(plot.fig.axes) == (2 if bInset else 1)
	axesHist = plot.fig.axes[0]
	assert axesHist.get_xlabel() == {'p-values': 'p-value', 'p-values (corrected)': 'p-value (corrected)'}[field]
	assert axesHist.get_ylabel() == 'Number of features'
	assert axesHist.get_yscale() == ('log' if bLog else 'linear')
	assert len(axesHist.patches) in (99, 100, 101)	# bins of width 0.01 accumulated in floating point up to 1.0
	data = r.getColumn('pValues' if field == 'p-values' else 'pValuesCorrected')
	assert sum(p.get_height() for p in axesHist.patches) == len([d for d in data if d <= axesHist.patches[-1].get_x() + axesHist.patches[-1].get_width()])
	if bInset:
		axins = plot.fig.axes[1]
		assert tuple(axins.get_xlim()) == (0, 0.05)
		assert axins.get_yscale() == ('log' if bInsetLog else 'linear')
		# inset at upper right, 60% x 60% of the parent axes
		pos, parent = axins.get_position(), axesHist.get_position()
		assert pos.width == pytest.approx(0.6 * parent.width, rel=1e-6) and pos.height == pytest.approx(0.6 * parent.height, rel=1e-6)
		assert pos.x1 < parent.x1 and pos.y1 < parent.y1 and pos.x0 > parent.x0 + 0.3 * parent.width


def test_pvalue_histogram_configure(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.pValueHistogram import pValueHistogram
	r = results(baseResults, signLevel=None)
	plot = pValueHistogram(makePreferences())

	def edit(ui):
		assert ui.cboFieldToPlot.currentText() == 'p-values (corrected)'
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('p-values'))
		ui.spinFigWidth.setValue(6.5)
		ui.spinFigHeight.setValue(5.5)
		ui.spinBinWidth.setValue(0.02)
		ui.chkLogScale.setChecked(True)
		ui.chkShowInset.setChecked(True)
		ui.spinInsetWidth.setValue(40.0)
		ui.spinInsetHeight.setValue(50.0)
		ui.spinInsetBinWidth.setValue(0.005)
		ui.chkInsetLogScale.setChecked(True)
		ui.btnXmax.click()
		assert ui.spinXlimit.value() == pytest.approx(round(max(r.getColumn('pValues')), ui.spinXlimit.decimals()))
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	state = lambda p: (p.fieldToPlot, p.figWidth, p.figHeight, p.binWidth, p.yAxisLogScale, p.bShowInset, p.insetWidth, p.insetHeight, p.insetBinWidth, p.insetLogScale, p.xLimit)
	s = state(plot)
	assert s[:10] == ('p-values', 6.5, 5.5, 0.02, True, True, 40.0, 50.0, 0.005, True)
	assert isinstance(plot.fieldToPlot, str)
	assert plot.fig.axes[0].get_xlabel() == 'p-value'
	assert state(pValueHistogram(makePreferences())) == s


# ---------------------------------------------------------------------------------------
# Profile bar plot

PBP_GRID = list(itertools.product(['Number of sequences', 'Proportion of sequences (%)'], [True, False], [True, False], [True, False]))


@pytest.mark.parametrize('field, bCIs, bPvalue, bOnlyActive', PBP_GRID)
def test_profile_bar_plot(qapp, baseResults, field, bCIs, bPvalue, bOnlyActive):
	from stamp.plugins.samples.plots.ProfileBarPlots import ProfileBarPlots
	r = results(baseResults)
	highlight = [r.activeData[0][0]]
	plot = ProfileBarPlots(makePreferences(highlight))
	plot.fieldToPlot = field
	plot.bShowCIs = bCIs
	plot.bShowPvalue = bPvalue
	plot.bOnlyActiveFeatures = bOnlyActive
	plot.endCapSize = 2
	plot.plot(r.profile, r)

	n = min(plot.numFeaturesToShow, len(r.activeData) if bOnlyActive else len(r.profile.profileDict))
	assert len(plot.fig.axes) == 1
	ax = plot.fig.axes[0]
	bars = [p for p in ax.patches if p.get_width() > 0]
	assert len(bars) == 2 * n
	assert len(ax.get_xticklabels()) == n
	assert ax.get_ylabel() == field
	assert ax.get_ylim()[0] == 0
	assert ax.get_legend() is not None	# default legend position 0
	assert tickTexts(ax.get_legend().get_texts()) == r.profile.sampleNames[:2]
	if highlight[0] in tickTexts(ax.get_xticklabels()):
		assert redLabels(ax.get_xticklabels()) == highlight
	assert all(l.get_rotation() == 90 for l in ax.get_xticklabels())
	# error bars: one LineCollection per sample, caps of size endCapSize
	assert len(ax.collections) == (2 if bCIs else 0)
	stars = [l for l in ax.lines if l.get_marker() == '*']
	assert len(stars) == (1 if bPvalue else 0)
	# edge-aligned bars: sample 1 starts at column i*colWidth, sample 2 right after it
	colWidth = plot.figColWidth
	barWidth = (colWidth * (plot.barWidth / 100.0)) / 2
	assert sorted(p.get_x() for p in bars)[:2] == pytest.approx([0.0, barWidth])
	assert np.allclose(ax.get_xticks(), np.arange(n) * colWidth + barWidth)


@pytest.mark.parametrize('legendPos', [0, 1, 7, 4, 2, 6, 3, -1])
def test_profile_bar_plot_legend(qapp, baseResults, legendPos):
	from stamp.plugins.samples.plots.ProfileBarPlots import ProfileBarPlots
	r = results(baseResults)
	plot = ProfileBarPlots(makePreferences())
	plot.legendPos = legendPos
	plot.numFeaturesToShow = 10
	plot.plot(r.profile, r)
	legend = plot.fig.axes[0].get_legend()
	assert (legend is None) == (legendPos == -1)
	assert len(plot.fig.axes[0].get_xticklabels()) == 10


def test_profile_bar_plot_too_large(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.ProfileBarPlots import ProfileBarPlots
	r = results(baseResults)
	plot = ProfileBarPlots(makePreferences())
	plot.figColWidth = 10.0
	calls = answer(monkeypatch, QtWidgets.QMessageBox.StandardButton.Ok)
	plot.plot(r.profile, r)
	assert calls and calls[0][1] == 'Excessively large plot'
	assertEmpty(plot)


def test_profile_bar_plot_configure(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.ProfileBarPlots import ProfileBarPlots
	r = results(baseResults)
	plot = ProfileBarPlots(makePreferences())

	def edit(ui):
		assert ui.spinBarWidth.value() == 80
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.spinFigColWidth.setValue(0.3)
		ui.spinFigHeight.setValue(5.0)
		ui.chkShowCIs.click()	# .ui wiring disables the cap size spin box
		assert not ui.spinEndCapSize.isEnabled()
		ui.spinEndCapSize.setValue(3)
		ui.spinFeaturesToShow.setValue(20)
		ui.chkOnlyActiveFeatures.setChecked(False)
		ui.radioLegendPosUpperLeft.setChecked(True)
		ui.spinBarWidth.setValue(60)
		ui.chkShowPvalue.setChecked(False)
		ui.spinPvalueThreshold.setValue(0.01)
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	state = lambda p: (p.fieldToPlot, p.figColWidth, p.figHeight, p.bShowCIs, p.endCapSize, p.numFeaturesToShow, p.bOnlyActiveFeatures, p.legendPos, p.barWidth, p.bShowPvalue, p.pValueThreshold)
	expected = ('Number of sequences', 0.3, 5.0, False, 3, 20, False, 2, 60, False, 0.01)
	assert state(plot) == expected
	assert len(plot.fig.axes[0].get_xticklabels()) == 20
	assert state(ProfileBarPlots(makePreferences())) == expected

	for radio, code in [('radioLegendPosUpperRight', 1), ('radioLegendPosCentreRight', 7), ('radioLegendPosLowerRight', 4),
											('radioLegendPosCentreLeft', 6), ('radioLegendPosLowerLeft', 3), ('radioLegendPosNone', -1), ('radioLegendPosBest', 0)]:
		configureWith(monkeypatch, lambda ui, radio=radio: getattr(ui, radio).setChecked(True))
		plot.configure(r.profile, results(baseResults))
		assert plot.legendPos == code


# ---------------------------------------------------------------------------------------
# Scatter plot

@pytest.mark.parametrize('bCIs, bHist, bR2', list(itertools.product([True, False], repeat=3)))
@pytest.mark.parametrize('corr', ['none', 'BH'])
def test_scatter_plot(qapp, baseResults, bCIs, bHist, bR2, corr):
	ScatterPlot = loadClass('ScatterPlot')
	r = results(baseResults, corr=corr)
	features = list(r.profile.profileDict.keys())
	highlight = [features[0], features[5]]
	plot = ScatterPlot(makePreferences(highlight))
	plot.bShowCIs = bCIs
	plot.bShowHistograms = bHist
	plot.bShowR2 = bR2
	plot.plot(r.profile, r)

	n = len(features)
	axes = plot.fig.axes
	assert len(axes) == (3 if bHist else 1)
	ax = axes[0]
	assert ax.get_xlabel() == r.profile.sampleNames[0] + ' (%)'
	assert ax.get_ylabel() == r.profile.sampleNames[1] + ' (%)'
	assert len(ax.collections) == 2	# all points + highlighted points
	assert len(ax.collections[0].get_offsets()) == n and len(ax.collections[1].get_offsets()) == 2
	assert ax.collections[0].get_sizes()[0] == 20
	assert len(ax.lines) == (2 if bCIs else 1)	# CI segments + y=x line
	r2 = [t.get_text() for t in ax.texts]
	assert (len(r2) == 1 and r2[0].startswith('R$^2$ = ')) if bR2 else r2 == []
	assert ax.get_xlim() == ax.get_ylim() and ax.get_xlim()[0] == 0
	if bHist:
		assert len(axes[1].patches) == plot.numBins and len(axes[2].patches) == plot.numBins
		assert axes[1].get_xlim() == ax.get_xlim() and axes[2].get_ylim() == ax.get_ylim()
	assert plot.cid is not None
	assert len(plot.plotEventHandler.data) == n
	tip = plot.plotEventHandler.data[0][2]
	assert tip.startswith(features[0] + '\n\n') and 'Corrected p-value: ' in tip


def test_scatter_plot_configure(qapp, baseResults, monkeypatch):
	ScatterPlot = loadClass('ScatterPlot')
	r = results(baseResults)
	plot = ScatterPlot(makePreferences())

	def edit(ui):
		ui.spinFigWidth.setValue(6.0)
		ui.spinFigHeight.setValue(6.5)
		ui.chkShowCIs.setChecked(False)
		ui.spinNumBins.setValue(25)
		ui.spinHistogramSize.setValue(0.75)
		ui.chkShowHistogram.setChecked(True)
		ui.spinMarkerSize.setValue(35)
		ui.chkShowR2.setChecked(False)
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	state = lambda p: (p.figWidth, p.figHeight, p.bShowCIs, p.numBins, p.histogramSize, p.bShowHistograms, p.markerSize, p.bShowR2)
	expected = (6.0, 6.5, False, 25, 0.75, True, 35, False)
	assert state(plot) == expected
	assert len(plot.fig.axes[1].patches) == 25
	assert plot.fig.axes[0].collections[0].get_sizes()[0] == 35
	# upstream writes the bin count under '/bin' but reads '/bins', so it does not round-trip
	assert state(ScatterPlot(makePreferences())) == expected[:3] + (30,) + expected[4:]


# ---------------------------------------------------------------------------------------
# Sequence histogram

@pytest.mark.parametrize('bCustomBin, bLog, bCustomX', list(itertools.product([True, False], repeat=3)))
def test_seq_histogram(qapp, baseResults, bCustomBin, bLog, bCustomX):
	from stamp.plugins.samples.plots.SeqHistogram import SeqHistogram
	r = results(baseResults)
	plot = SeqHistogram(makePreferences())
	plot.bCustomBinWidth = bCustomBin
	plot.binWidth = 250.0
	plot.yAxisLogScale = bLog
	plot.bCustomXaxis = bCustomX
	plot.xLimitLeft, plot.xLimitRight = 10.0, 2000.0
	plot.plot(r.profile, r)

	seqs1, seqs2 = r.profile.getSequenceCounts(0), r.profile.getSequenceCounts(1)
	xMax, xMin = max(max(seqs1), max(seqs2)), min(min(seqs1), min(seqs2))
	binWidth = 250.0 if bCustomBin else (xMax - xMin) / 40
	assert plot.binWidth == binWidth
	nBins = int(xMax // binWidth) + 1
	ax = plot.fig.axes[0]
	assert len(plot.fig.axes) == 1
	assert len(ax.patches) in (2 * nBins, 2 * (nBins + 1))
	assert sum(p.get_height() for p in ax.patches) == len(seqs1) + len(seqs2)
	assert ax.get_yscale() == ('log' if bLog else 'linear')
	if bCustomX:
		assert tuple(ax.get_xlim()) == (10.0, 2000.0)
	assert ax.get_xlabel() == 'Sequences' and ax.get_ylabel() == 'Number of features'
	assert ax.get_legend() is not None
	assert tickTexts(ax.get_legend().get_texts()) == r.profile.sampleNames[:2]
	colours = {p.get_facecolor()[:3] for p in ax.patches}
	assert colours == {tuple(c / 255.0 for c in (128, 177, 211)), tuple(c / 255.0 for c in (253, 180, 98))}


@pytest.mark.parametrize('legendPos', [0, 1, 7, 4, 2, 6, 3, -1])
def test_seq_histogram_legend(qapp, baseResults, legendPos):
	from stamp.plugins.samples.plots.SeqHistogram import SeqHistogram
	r = results(baseResults)
	plot = SeqHistogram(makePreferences())
	plot.legendPos = legendPos
	plot.plot(r.profile, r)
	legend = plot.fig.axes[0].get_legend()
	assert (legend is None) == (legendPos == -1)
	if legend is not None:
		assert legend._loc == legendPos


def test_seq_histogram_configure(qapp, baseResults, monkeypatch):
	from stamp.plugins.samples.plots.SeqHistogram import SeqHistogram
	r = results(baseResults)
	plot = SeqHistogram(makePreferences())
	plot.plot(r.profile, r)
	seqs = r.profile.getSequenceCounts(0) + r.profile.getSequenceCounts(1)

	def edit(ui):
		assert not ui.spinBinWidth.isEnabled() and not ui.spinXmin.isEnabled()
		assert ui.spinBinWidth.value() == int(plot.binWidth)
		ui.chkCustomBinWidth.setChecked(True)	# toggled -> changeCustomBinWidth
		assert ui.spinBinWidth.isEnabled()
		ui.spinBinWidth.setValue(300)
		ui.chkLogScale.setChecked(True)
		ui.chkCustomXaxis.setChecked(True)	# toggled -> changeCustomXaxis
		assert ui.spinXmin.isEnabled() and ui.spinXmax.isEnabled()
		ui.btnXmin.click()
		ui.btnXmax.click()
		assert ui.spinXmin.value() == pytest.approx(round(min(seqs), ui.spinXmin.decimals()))
		assert ui.spinXmax.value() == pytest.approx(round(max(seqs), ui.spinXmax.decimals()))
		ui.spinFigWidth.setValue(5.0)
		ui.spinFigHeight.setValue(4.5)
		ui.radioLegendPosCentreRight.setChecked(True)
	configureWith(monkeypatch, edit)
	plot.configure(r.profile, r)
	state = lambda p: (p.figWidth, p.figHeight, p.bCustomBinWidth, p.binWidth, p.yAxisLogScale, p.bCustomXaxis, p.xLimitLeft, p.xLimitRight, p.legendPos)
	s = state(plot)
	assert s[:6] == (5.0, 4.5, True, 300, True, True) and s[8] == 7
	assert s[6] == pytest.approx(min(seqs), abs=1) and s[7] == pytest.approx(max(seqs), abs=1)	# spin boxes show 0 decimals
	assert plot.fig.axes[0].get_legend()._loc == 7
	assert state(SeqHistogram(makePreferences())) == s

	for radio, code in [('radioLegendPosBest', 0), ('radioLegendPosUpperRight', 1), ('radioLegendPosLowerRight', 4), ('radioLegendPosUpperLeft', 2),
											('radioLegendPosCentreLeft', 6), ('radioLegendPosLowerLeft', 3), ('radioLegendPosNone', -1)]:
		configureWith(monkeypatch, lambda ui, radio=radio: getattr(ui, radio).setChecked(True))
		plot.configure(r.profile, results(baseResults))
		assert plot.legendPos == code


# ---------------------------------------------------------------------------------------
# export of every plot with real data

@pytest.mark.parametrize('name', PLOT_FILES)
def test_save_plot(qapp, baseResults, tmp_path, name):
	cls = loadClass(name)
	r = results(baseResults, signLevel=0.05 if name not in ['MultCompCorrectionPlots', 'pValueHistogram'] else None)
	plot = cls(makePreferences([r.activeData[0][0]]))
	plot.plot(r.profile, r)
	assert len(plot.fig.axes) >= 1
	assertSaves(plot, tmp_path, name)


def test_example_plugin(qapp, baseResults, tmp_path):
	MyScatterPlot = loadClass('MyScatterPlot', 'stamp.plugins.samples.plots.examples.')
	r = results(baseResults)
	plot = MyScatterPlot(makePreferences())
	plot.plot(r.profile, r)
	ax = plot.fig.axes[0]
	assert len(ax.collections) == 1 and len(ax.collections[0].get_offsets()) == len(r.activeData)
	assert plot.sampleName1 == r.profile.sampleNames[0]
	assertSaves(plot, tmp_path, 'MyScatterPlot')


def test_configure_dialog_cancel(qapp, baseResults, monkeypatch):
	"""Rejecting a dialog leaves the plot and its settings unchanged."""
	from stamp.plugins.samples.plots.Bar import Bar
	from stamp.plugins.samples.AbstractSamplePlotPlugin import ConfigureDialog
	r = results(baseResults)
	plot = Bar(makePreferences())

	def fakeExec(dlg):
		dlg.ui.spinFigWidth.setValue(12.0)
		dlg.ui.buttonBox.rejected.emit()
		return dlg.result()
	monkeypatch.setattr(ConfigureDialog, 'exec', fakeExec)
	plot.configure(r.profile, r)
	assert plot.figWidth == 7.0
	assert Bar(makePreferences()).figWidth == 7.0
