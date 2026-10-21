'''
Two-group ("groups" mode) plot plugins on real Enterotypes results, headless.

Covers every plot in stamp/plugins/groups/plots/: plot() on Welch's t-test results
(with and without corrections, '<All other samples>', highlighted / selected features,
every sorting / layout option the plot's settings expose), emptyAxis(), savePlot() at
300 dpi to png/pdf/svg, the configure dialog's OK path and the QSettings round trip.
'''

import importlib
import math
import os
import struct
import sys
import types

import numpy as np
import pytest

from PyQt6 import QtCore, QtGui, QtWidgets

import matplotlib as mpl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'stamp', 'examples', 'EnterotypesArumugam')
PLOTS_DIR = os.path.join(ROOT, 'stamp', 'stamp', 'plugins', 'groups', 'plots')

PLOT_NAMES = ['BarPlot', 'BoxPlot', 'ExtendedErrorBar', 'HeatmapPlot', 'pcaPlot', 'ScatterPlot']

# what STAMP.py MainWindow.__init__ and module level set globally
STAMP_RC = {'font.size': 8, 'axes.titlesize': 8, 'axes.labelsize': 8, 'xtick.labelsize': 8,
			'ytick.labelsize': 8, 'legend.fontsize': 8, 'svg.fonttype': 'none'}

GROUP1 = 'Enterotype 1'
GROUP2 = 'Enterotype 2'
OTHERS = '<All other samples>'
EMPTY_LABEL = 'No active features or degenerate plot'


# ---------------------------------------------------------------- fixtures / helpers

@pytest.fixture(scope='module')
def app():
	return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _importPlotEventHandler():
	'''
	ponytail: stamp/plugins/PlotEventHandler.py (not owned here) still imports PyQt4; until its
	owner ports it, import it once against a shim that exists only during the import.
	Upgrade path: delete this function when that file imports PyQt6.
	'''
	try:
		import stamp.plugins.PlotEventHandler  # noqa: F401
	except ImportError:
		shim = types.ModuleType('PyQt4')
		shim.QtGui = types.SimpleNamespace(QMessageBox=QtWidgets.QMessageBox, QIcon=QtGui.QIcon, QPixmap=QtGui.QPixmap)
		sys.modules['PyQt4'] = shim
		try:
			import stamp.plugins.PlotEventHandler  # noqa: F401
		finally:
			del sys.modules['PyQt4']


def plotClass(name):
	_importPlotEventHandler()
	module = importlib.import_module('stamp.plugins.groups.plots.' + name)
	return getattr(module, name)


@pytest.fixture(scope='module')
def data():
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
	prefs = {'Pseudocount': 0.5, 'Replicates': 1000}
	tree, err = StampIO(prefs).read(os.path.join(EX, 'Enterotypes.profile.spf'))
	md, err = MetadataIO(prefs).read(os.path.join(EX, 'Enterotypes.metadata.tsv'), tree)
	md.setActiveField('Enterotype', tree)
	return types.SimpleNamespace(tree=tree, md=md)


def groupProfile(data, group2=GROUP2, level='Phyla'):
	return data.tree.createGroupProfile(GROUP1, group2, 'Entire sample', level, data.md, 'Remove unclassified reads')


def welch(profile, prefs, correction='NoCorrection', signLevel=None):
	'''Welch's t-test as STAMP.py runs it: test, correction, select all, filter.'''
	from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	module = importlib.import_module('stamp.plugins.common.multipleComparisonCorrections.' + correction)
	g = GroupStatsTests(prefs)
	g.run(Welch(prefs), 'Two-sided', None, 0.95, profile)
	g.results.performMultCompCorrection(getattr(module, correction)(prefs))
	g.results.selectAllFeautres()
	g.results.filterFeatures(signLevel, None, None, None, None, None, None, None, None, 'OR', None, None)
	return g.results


# A domain of its own: on macOS QSettings('BeikoLab', 'STAMP-test') is one shared plist, and the
# other plot suites clear() it, so running them concurrently made the round trips flaky.
SETTINGS_APP = 'STAMP-test-groups'


@pytest.fixture
def settings():
	s = QtCore.QSettings('BeikoLab', SETTINGS_APP)
	s.clear()
	yield s
	s.clear()
	s.sync()


@pytest.fixture
def prefs(app, settings):
	return {
		'Settings': settings,
		'Pseudocount': 0.5,
		'Replicates': 1000,
		'Truncate feature names': True,
		'Length of truncated feature names': 50,
		'Axes colour': QtGui.QColor('#7f7f7f'),
		'All other samples colour': QtGui.QColor('#7f7f7f'),
		'Minimum reported p-value exponent': -15.0,
		'Sample 1 colour': QtGui.QColor(128, 177, 211),
		'Sample 2 colour': QtGui.QColor(253, 180, 98),
		'Group colours': {GROUP1: QtGui.QColor(128, 177, 211), GROUP2: QtGui.QColor(253, 180, 98),
							OTHERS: QtGui.QColor('#7f7f7f')},
		'Highlighted sample features': [],
		'Highlighted group features': [],
		'Highlighted multiple group features': [],
		'Selected group feature': '',
		'Selected multiple group feature': '',
		'Last directory': '',
	}


@pytest.fixture(autouse=True)
def stampRc():
	with mpl.rc_context(STAMP_RC):
		yield


@pytest.fixture
def phyla(data, prefs):
	profile = groupProfile(data)
	return profile, welch(profile, prefs)


def hexColour(prefs, group):
	return mpl.colors.to_rgba(prefs['Group colours'][group].name())


def assertEmpty(plot, title=''):
	axes = plot.fig.axes
	assert len(axes) == 1
	assert axes[0].get_xlabel() == EMPTY_LABEL
	assert axes[0].get_ylabel() == EMPTY_LABEL
	assert axes[0].get_title() == title
	assert tuple(plot.fig.get_size_inches()) == (6, 4)


def texts(labels):
	return [t.get_text() for t in labels]


def pngSize(path):
	with open(path, 'rb') as f:
		head = f.read(24)
	assert head[:8] == b'\x89PNG\r\n\x1a\n'
	return struct.unpack('>II', head[16:24])


def acceptDialog(monkeypatch, edit=None, seen=None):
	'''
	Replace the modal exec() of every ConfigureDialog: record the widget state the plot
	loaded, let the test edit widgets, then emit buttonBox.accepted (connected to the
	dialog's accept() slot by the generated UI) and return the dialog result.
	'''
	from stamp.plugins.groups.AbstractGroupPlotPlugin import ConfigureDialog

	def fakeExec(dlg):
		if seen is not None:
			seen['dlg'] = dlg  # keep the dialog (and its widgets) alive
			seen['ui'] = dlg.ui
			seen['initial'] = snapshot(dlg.ui)
		if edit is not None:
			edit(dlg.ui)
		dlg.ui.buttonBox.accepted.emit()
		return dlg.result()

	monkeypatch.setattr(ConfigureDialog, 'exec', fakeExec, raising=False)


def snapshot(ui):
	state = {}
	for name, w in vars(ui).items():
		if isinstance(w, QtWidgets.QComboBox):
			state[name] = w.currentText()
		elif isinstance(w, (QtWidgets.QCheckBox, QtWidgets.QRadioButton)):
			state[name] = w.isChecked()
		elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
			state[name] = w.value()
	return state


def comboItems(uiClass, comboName):
	dlg = QtWidgets.QDialog()
	ui = uiClass()
	ui.setupUi(dlg)
	combo = getattr(ui, comboName)
	return [combo.itemText(i) for i in range(combo.count())]


# ---------------------------------------------------------------- inventory / interface

def test_every_plot_file_is_covered():
	found = sorted(f[:-3] for f in os.listdir(PLOTS_DIR) if f.endswith('.py') and f != '__init__.py')
	assert found == sorted(PLOT_NAMES)
	additional = [f for f in os.listdir(os.path.join(PLOTS_DIR, 'additional')) if f.endswith('.py') and f != '__init__.py']
	assert additional == []


EXPECTED_INTERFACE = {
	'BarPlot': ('Bar plot', 'Exploratory', False, True),
	'BoxPlot': ('Box plot', 'Exploratory', False, True),
	'ExtendedErrorBar': ('Extended error bar', 'Statistical', True, False),
	'HeatmapPlot': ('Heatmap plot', 'Exploratory', False, False),
	'pcaPlot': ('PCA plot', 'Exploratory', False, False),
	'ScatterPlot': ('Scatter plot', 'Exploratory', True, False),
}


@pytest.mark.parametrize('name', PLOT_NAMES)
def test_interface(name, prefs, phyla):
	from stamp.plugins.groups.AbstractGroupPlotPlugin import AbstractGroupPlotPlugin
	cls = plotClass(name)
	plot = cls(prefs)
	assert isinstance(plot, AbstractGroupPlotPlugin)
	assert (plot.name, plot.type, plot.bSupportsHighlight, plot.bPlotFeaturesIndividually) == EXPECTED_INTERFACE[name]
	for attr in ('plot', 'configure', 'savePlot', 'mirrorProperties', 'mouseEventCallback', 'emptyAxis', 'get_width_height', 'clear'):
		assert callable(getattr(plot, attr))
	assert plot.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed

	profile, results = phyla
	prefs['Selected group feature'] = 'Firmicutes'
	plot.plot(profile, results)
	w, h = plot.get_width_height()
	inches = plot.fig.get_size_inches()
	assert (w, h) == (int(inches[0] * 96), int(inches[1] * 96))
	assert plot.sizeHint().width() == w

	# PlotsManager.sendToNewWindow: new instance + mirrorProperties + plot
	copy = cls(prefs)
	copy.mirrorProperties(plot)
	assert copy.name == plot.name
	copy.plot(profile, results)
	assert len(copy.fig.axes) == len(plot.fig.axes)

	# a new callback replaces the previous one
	plot.mouseEventCallback(lambda event: None)
	registered = dict(plot.callbacks.callbacks['button_press_event'])
	plot.mouseEventCallback(lambda event: None)
	assert len(plot.callbacks.callbacks['button_press_event']) == len(registered)
	assert plot.cid not in registered
	plot.clear()
	assert plot.fig.axes == []


@pytest.mark.parametrize('name', PLOT_NAMES)
def test_style_is_scoped(name, prefs, phyla):
	'''classic (matplotlib 1.x) defaults apply inside plot()/draw() only, with STAMP's font sizes.'''
	profile, results = phyla
	prefs['Selected group feature'] = 'Firmicutes'
	before = dict(mpl.rcParams)
	plot = plotClass(name)(prefs)
	plot.plot(profile, results)
	plot.draw()
	assert dict(mpl.rcParams) == before
	label = plot.fig.axes[-1].yaxis.get_ticklabels()[0] if plot.fig.axes[-1].yaxis.get_ticklabels() else None
	if label is not None:
		assert label.get_fontsize() == 8


@pytest.mark.parametrize('name', PLOT_NAMES)
def test_save_png_pdf_svg_300dpi(name, prefs, phyla, tmp_path):
	profile, results = phyla
	prefs['Selected group feature'] = 'Bacteroidetes'
	plot = plotClass(name)(prefs)
	plot.plot(profile, results)
	w, h = plot.fig.get_size_inches()
	for ext in ('png', 'pdf', 'svg'):
		path = str(tmp_path / ('plot.' + ext))
		plot.savePlot(path, dpi=300)
		assert os.path.getsize(path) > 2000, ext
	pw, ph = pngSize(str(tmp_path / 'plot.png'))
	assert abs(pw - w * 300) <= 1 and abs(ph - h * 300) <= 1
	with open(str(tmp_path / 'plot.svg')) as f:
		svg = f.read()
	assert '<text' in svg  # svg.fonttype 'none' from STAMP.py is kept
	plot.savePlot(str(tmp_path / 'plot.bmp'), dpi=300)
	assert not os.path.exists(str(tmp_path / 'plot.bmp'))

	plot.emptyAxis()
	plot.savePlot(str(tmp_path / 'empty.png'), dpi=300)
	assert pngSize(str(tmp_path / 'empty.png')) == (1800, 1200)


# ---------------------------------------------------------------- extended error bar (lab manual plot)

def errorbarAxes(plot):
	'''(axNumSeq or None, axErrorbar, axRight or None) from the figure.'''
	axes = plot.fig.axes
	axErrorbar = [a for a in axes if a.get_xlabel() == 'Difference in mean proportions (%)'][0]
	axNumSeq = [a for a in axes if a.get_xlabel() == 'Mean proportion (%)']
	axRight = [a for a in axes if a.get_ylabel().startswith(('p-value', 'q-value'))]
	return (axNumSeq[0] if axNumSeq else None), axErrorbar, (axRight[0] if axRight else None)


def rowFeatures(ax):
	return texts(ax.get_yticklabels())


def test_eeb_default_matches_results(prefs, phyla):
	profile, results = phyla
	plot = plotClass('ExtendedErrorBar')(prefs)
	plot.plot(profile, results)
	axNumSeq, axErrorbar, axRight = errorbarAxes(plot)
	assert len(plot.fig.axes) == 3

	n = len(results.getActiveFeatures())
	assert n == 16
	features = rowFeatures(axNumSeq)
	assert sorted(features) == sorted(results.getActiveFeatures())

	# default sort: p-values, largest at the bottom row (y=0)
	pByFeature = {row[0]: row[results.dataHeadings['pValues']] for row in results.data}
	pValues = [pByFeature[f] for f in features]
	assert pValues == sorted(pValues, reverse=True)

	# error bars: centre = effect size, ends = CI, per row, in the plotted order
	byFeature = {row[0]: row for row in results.data}
	container = axErrorbar.containers[0]
	dataLine, caplines, barcols = container.lines
	assert list(dataLine.get_ydata()) == list(range(n))
	for i, f in enumerate(features):
		row = byFeature[f]
		assert dataLine.get_xdata()[i] == pytest.approx(row[7], rel=1e-12)
		seg = barcols[0].get_segments()[i]
		assert seg[0][0] == pytest.approx(row[8], rel=1e-9, abs=1e-12)
		assert seg[1][0] == pytest.approx(row[9], rel=1e-9, abs=1e-12)
	assert len(caplines) == 2 and caplines[0].get_markersize() == 6  # 1.x errorbar capsize 3 -> marker size 6
	assert dataLine.get_markersize() == pytest.approx(math.sqrt(30))
	assert mpl.colors.to_rgba(dataLine.get_markerfacecolor()) == hexColour(prefs, GROUP1)

	# rows dominated by group 2 get a second marker in the group 2 colour
	group2Line = [l for l in axErrorbar.lines if l is not dataLine and l.get_marker() == 'o'][0]
	assert len(group2Line.get_xdata()) == sum(1 for f in features if byFeature[f][7] < 0)
	assert mpl.colors.to_rgba(group2Line.get_markerfacecolor()) == hexColour(prefs, GROUP2)

	# bar subplot: two edge-aligned bars per row (1.x barh default align='edge')
	bars = axNumSeq.patches
	barsG1 = [p for p in bars if p.get_facecolor() == hexColour(prefs, GROUP1)]
	barsG2 = [p for p in bars if p.get_facecolor() == hexColour(prefs, GROUP2)]
	assert len(barsG1) == n and len(barsG2) == n
	assert [b.get_y() for b in barsG1] == pytest.approx(list(range(n)))
	assert [b.get_y() for b in barsG2] == pytest.approx([i - 0.3 for i in range(n)])
	assert barsG1[0].get_height() == pytest.approx(0.3)
	assert barsG1[0].get_edgecolor() == (0, 0, 0, 1)  # 1.x patch edges
	assert [b.get_width() for b in barsG1] == pytest.approx([byFeature[f][1] for f in features])
	maxPercentage = max(max(r[1] for r in results.activeData), max(r[3] for r in results.activeData))
	assert texts(axNumSeq.get_xticklabels()) == ['0.0', '%.1f' % maxPercentage]
	assert axNumSeq.get_ylim() == (-1, n)

	# p-value labels on the right, corrected (upstream titles them '(corrected)' even without a correction)
	assert axRight.get_ylabel() == 'p-value (corrected)'
	assert rowFeatures(axRight) == [results.getFeatureStatisticAsStr(f, 'pValuesCorrected') for f in features]
	assert axErrorbar.get_title() == '95% confidence intervals'

	# ticks: x bottom only, no y ticks; the error-bar axes hides its shared y labels
	assert all(t.tick1line.get_visible() and not t.tick2line.get_visible() for t in axErrorbar.xaxis.get_major_ticks())
	assert not any(t.tick1line.get_visible() or t.tick2line.get_visible() for t in axNumSeq.yaxis.get_major_ticks())
	assert not any(t.get_visible() for t in axErrorbar.yaxis.get_major_ticks())
	assert axErrorbar.spines['top'].get_edgecolor()[3] == 0

	# figure size: rows * 0.2 + bottom labels 0.4 + top 0.25, width 7
	assert tuple(plot.fig.get_size_inches()) == pytest.approx((7.0, 0.2 * n + 0.4 + 0.25))
	# without custom limits the plot reports its automatic x limits back
	assert (plot.minX, plot.maxX) == axErrorbar.get_xlim()
	assert plot.fig.legends == []


def test_eeb_pvalue_filter_matches_active_features(data, prefs):
	'''CI-5: Genera, Welch, p < 0.05 filter: rows are exactly getActiveFeatures().'''
	profile = groupProfile(data, level='Genera')
	results = welch(profile, prefs, signLevel=0.05)
	active = results.getActiveFeatures()
	assert 0 < len(active) < len(results.data) and len(active) <= 200
	assert all(row[results.dataHeadings['pValuesCorrected']] <= 0.05 for row in results.activeData)

	plot = plotClass('ExtendedErrorBar')(prefs)
	plot.plot(profile, results)
	axNumSeq, axErrorbar, axRight = errorbarAxes(plot)
	features = rowFeatures(axNumSeq)
	assert len(features) == len(active)
	assert set(features) == set(f if len(f) <= 53 else f[:50] + '...' for f in active)
	assert len(axErrorbar.containers[0].lines[0].get_xdata()) == len(active)
	assert all(float(p) <= 0.05 for p in rowFeatures(axRight) if not p.startswith('<'))
	assert tuple(plot.fig.get_size_inches()) == pytest.approx((7.0, 0.2 * len(active) + 0.65))

	# a stricter filter shrinks the plot in step with getActiveFeatures()
	results.filterFeatures(0.001, None, None, None, None, None, None, None, None, 'OR', None, None)
	plot.plot(profile, results)
	assert len(rowFeatures(errorbarAxes(plot)[0])) == len(results.getActiveFeatures())


@pytest.mark.parametrize('correction,title', [
	('NoCorrection', 'p-value (corrected)'),  # upstream compares .method to 'No correction' (a name), so always '(corrected)'
	('Bonferroni', 'p-value (corrected)'),
	('BenjaminiHochbergFDR', 'q-value (corrected)'),
])
def test_eeb_corrections(correction, title, prefs, data):
	profile = groupProfile(data)
	results = welch(profile, prefs, correction=correction)
	plot = plotClass('ExtendedErrorBar')(prefs)
	plot.plot(profile, results)
	axNumSeq, axErrorbar, axRight = errorbarAxes(plot)
	assert axRight.get_ylabel() == title
	features = rowFeatures(axNumSeq)
	assert rowFeatures(axRight) == [results.getFeatureStatisticAsStr(f, 'pValuesCorrected') for f in features]

	plot.bShowCorrectedPvalues = False
	plot.plot(profile, results)
	axNumSeq, axErrorbar, axRight = errorbarAxes(plot)
	assert axRight.get_ylabel() == ('q-value' if correction == 'BenjaminiHochbergFDR' else 'p-value')
	assert rowFeatures(axRight) == [results.getFeatureStatisticAsStr(f, 'pValues') for f in rowFeatures(axNumSeq)]


def test_eeb_sorting_fields(prefs, phyla):
	from stamp.plugins.groups.plots.configGUI.extendedErrorBarUI import Ui_ExtendedErrorBarDialog
	fields = comboItems(Ui_ExtendedErrorBarDialog, 'cboSortingField')
	assert fields == ['p-values', 'Effect sizes', 'Feature labels']
	profile, results = phyla
	byFeature = {row[0]: row for row in results.data}
	plot = plotClass('ExtendedErrorBar')(prefs)
	for field in fields:
		plot.sortingField = field
		plot.plot(profile, results)
		features = rowFeatures(errorbarAxes(plot)[0])
		if field == 'p-values':
			key = [byFeature[f][5] for f in features]
			assert key == sorted(key, reverse=True)
		elif field == 'Effect sizes':
			key = [abs(byFeature[f][7]) for f in features]
			assert key == sorted(key)
		else:
			assert features == sorted(features, key=str.lower, reverse=True)


def test_eeb_all_other_samples_and_legend(data, prefs):
	profile = groupProfile(data, group2=OTHERS)
	results = welch(profile, prefs)
	assert profile.groupName2 == OTHERS and len(profile.samplesInGroup2) > 6
	plot = plotClass('ExtendedErrorBar')(prefs)
	for legendPos, bottom in ((2, 0.4), (3, 0.56), (4, 0.56), (8, 0.56)):
		plot.legendPos = legendPos
		plot.plot(profile, results)
		assert len(plot.fig.legends) == 1
		legend = plot.fig.legends[0]
		assert texts(legend.get_texts()) == [GROUP1, OTHERS]
		assert legend._loc == legendPos
		assert legend.get_frame().get_linewidth() == 0
		assert [p.get_facecolor() for p in legend.get_patches()] == [hexColour(prefs, GROUP1), hexColour(prefs, OTHERS)]
		n = len(results.getActiveFeatures())
		assert plot.fig.get_size_inches()[1] == pytest.approx(0.2 * n + bottom + 0.25)


def test_eeb_options(prefs, phyla):
	profile, results = phyla
	plot = plotClass('ExtendedErrorBar')(prefs)
	n = len(results.getActiveFeatures())

	plot.bShowBarPlot = False
	plot.plot(profile, results)
	axNumSeq, axErrorbar, axRight = errorbarAxes(plot)
	assert axNumSeq is None and len(plot.fig.axes) == 2
	assert len(rowFeatures(axErrorbar)) == n

	plot.bShowPValueLabels = False
	plot.plot(profile, results)
	assert len(plot.fig.axes) == 1

	plot.bShowBarPlot = True
	plot.bShowStdDev = True
	plot.endCapSize = 4
	plot.bCustomLimits = True
	plot.minX, plot.maxX = -40.0, 25.0
	plot.markerSize = 50
	plot.figWidth, plot.figHeightPerRow = 9.0, 0.3
	plot.plot(profile, results)
	axNumSeq, axErrorbar, axRight = errorbarAxes(plot)
	assert axRight is None and len(plot.fig.axes) == 2
	assert axErrorbar.get_xlim() == (-40.0, 25.0)
	assert axErrorbar.containers[0].lines[0].get_markersize() == pytest.approx(math.sqrt(50))
	stdBars = [c for c in axNumSeq.containers if hasattr(c, 'errorbar') and c.errorbar is not None]
	assert len(stdBars) == 2
	caps = stdBars[0].errorbar.lines[1]
	assert caps and caps[0].get_markersize() == 8  # capsize 4 -> marker size 8
	assert tuple(plot.fig.get_size_inches()) == pytest.approx((9.0, 0.3 * n + 0.65))


def test_eeb_highlighted_and_truncated(prefs, phyla):
	profile, results = phyla
	prefs['Highlighted group features'] = ['Firmicutes', 'Bacteroidetes']
	plot = plotClass('ExtendedErrorBar')(prefs)
	plot.plot(profile, results)
	axNumSeq = errorbarAxes(plot)[0]
	red = {l.get_text() for l in axNumSeq.get_yticklabels() if mpl.colors.to_rgba(l.get_color()) == (1, 0, 0, 1)}
	assert red == {'Firmicutes', 'Bacteroidetes'}

	plot.bShowBarPlot = False
	plot.plot(profile, results)
	axErrorbar = errorbarAxes(plot)[1]
	red = {l.get_text() for l in axErrorbar.get_yticklabels() if mpl.colors.to_rgba(l.get_color()) == (1, 0, 0, 1)}
	assert red == {'Firmicutes', 'Bacteroidetes'}

	prefs['Length of truncated feature names'] = 5
	plot.bShowBarPlot = True
	plot.plot(profile, results)
	labels = rowFeatures(errorbarAxes(plot)[0])
	assert 'Firmi...' in labels and 'Other' in labels
	assert all(len(l) <= 8 for l in labels)
	red = {l.get_text() for l in errorbarAxes(plot)[0].get_yticklabels() if mpl.colors.to_rgba(l.get_color()) == (1, 0, 0, 1)}
	assert red == {'Firmi...', 'Bacte...'}


def test_eeb_many_features_question(data, prefs, monkeypatch):
	profile = groupProfile(data, level='Genera')
	results = welch(profile, prefs)
	assert len(results.getActiveFeatures()) == 247
	asked = []

	def question(*args):
		asked.append(args)
		return answer[0]

	monkeypatch.setattr(QtWidgets.QMessageBox, 'question', staticmethod(question))
	plot = plotClass('ExtendedErrorBar')(prefs)
	answer = [QtWidgets.QMessageBox.StandardButton.No]
	plot.plot(profile, results)
	assert len(asked) == 1 and 'Profile contains 247 features' in asked[0][2]
	assertEmpty(plot)
	answer = [QtWidgets.QMessageBox.StandardButton.Yes]
	plot.plot(profile, results)
	assert len(rowFeatures(errorbarAxes(plot)[0])) == 247
	assert QtWidgets.QApplication.overrideCursor() is None


def test_eeb_empty(prefs, phyla):
	profile, results = phyla
	results.filterFeatures(0.0, None, None, None, None, None, None, None, None, 'OR', None, None)
	assert results.activeData == []
	plot = plotClass('ExtendedErrorBar')(prefs)
	plot.plot(profile, results)
	assertEmpty(plot)


def test_eeb_configure_round_trip(prefs, phyla, monkeypatch, settings):
	profile, results = phyla
	cls = plotClass('ExtendedErrorBar')
	plot = cls(prefs)
	plot.legendPos = 3
	seen = {}

	def edit(ui):
		ui.cboSortingField.setCurrentIndex(ui.cboSortingField.findText('Feature labels'))
		ui.spinFigWidth.setValue(8.5)
		ui.spinFigRowHeight.setValue(0.25)
		ui.chkShowBarPlot.setChecked(False)
		ui.chkPValueLabels.setChecked(False)
		ui.chkCorrectedPvalues.setChecked(False)
		ui.chkCustomLimits.click()
		ui.spinMinimumX.setValue(-5.0)
		ui.spinMaximumX.setValue(5.0)
		ui.spinMarkerSize.setValue(40)
		ui.chkShowStdDev.setChecked(True)
		ui.spinEndCapSize.setValue(3)
		ui.radioLegendPosLowerCentre.setChecked(True)

	acceptDialog(monkeypatch, edit, seen)
	plot.configure(profile, results)

	initial = seen['initial']
	assert initial['cboSortingField'] == 'p-values'
	assert initial['spinFigWidth'] == 7.0 and initial['spinFigRowHeight'] == 0.2
	assert initial['chkShowBarPlot'] and initial['chkPValueLabels'] and initial['chkCorrectedPvalues']
	assert not initial['chkCustomLimits'] and initial['radioLegendPosLowerLeft']
	assert initial['spinMarkerSize'] == 30 and not initial['chkShowStdDev'] and initial['spinEndCapSize'] == 0
	assert seen['ui'].spinMinimumX.isEnabled()  # chkCustomLimits.clicked -> setEnabled (from the .ui)

	assert plot.sortingField == 'Feature labels'
	assert (plot.figWidth, plot.figHeightPerRow) == (8.5, 0.25)
	assert (plot.bShowBarPlot, plot.bShowPValueLabels, plot.bShowCorrectedPvalues) == (False, False, False)
	assert (plot.bCustomLimits, plot.minX, plot.maxX) == (True, -5.0, 5.0)
	assert (plot.markerSize, plot.bShowStdDev, plot.endCapSize, plot.legendPos) == (40, True, 3, 8)
	# configure re-plots with the new options
	assert len(plot.fig.axes) == 1 and plot.fig.axes[0].get_xlim() == (-5.0, 5.0)
	assert QtWidgets.QApplication.overrideCursor() is None

	key = 'group: Extended error bar/'
	assert settings.value(key + 'field', type=str) == 'Feature labels'
	assert settings.value(key + 'legend position', type=int) == 8
	fresh = cls(prefs)
	for attr in ('figWidth', 'figHeightPerRow', 'sortingField', 'bShowBarPlot', 'bShowPValueLabels', 'bShowCorrectedPvalues',
				'bCustomLimits', 'minX', 'maxX', 'markerSize', 'bShowStdDev', 'endCapSize', 'legendPos'):
		assert getattr(fresh, attr) == getattr(plot, attr), attr
	assert type(fresh.sortingField) is str and type(fresh.markerSize) is int and type(fresh.bShowBarPlot) is bool


def test_eeb_configure_cancel_keeps_state(prefs, phyla, monkeypatch):
	from stamp.plugins.groups.AbstractGroupPlotPlugin import ConfigureDialog
	profile, results = phyla
	plot = plotClass('ExtendedErrorBar')(prefs)

	def reject(dlg):
		dlg.ui.spinFigWidth.setValue(12.0)
		dlg.ui.buttonBox.rejected.emit()
		return dlg.result()

	monkeypatch.setattr(ConfigureDialog, 'exec', reject, raising=False)
	plot.configure(profile, results)
	assert plot.figWidth == 7.0


# ---------------------------------------------------------------- bar plot

def test_bar_plot(data, prefs):
	plot = plotClass('BarPlot')(prefs)
	for group2 in (GROUP2, OTHERS):
		profile = groupProfile(data, group2=group2)
		results = welch(profile, prefs)
		prefs['Selected group feature'] = 'Firmicutes'
		for field in ('Proportion of sequences (%)', 'Number of sequences'):
			plot.fieldToPlot = field
			plot.plot(profile, results)
			ax = plot.fig.axes[0]
			assert len(plot.fig.axes) == 1
			n1, n2 = len(profile.samplesInGroup1), len(profile.samplesInGroup2)
			assert len(ax.patches) == n1 + n2
			if field == 'Number of sequences':
				d1, d2 = profile.getFeatureCounts('Firmicutes')
			else:
				d1, d2 = profile.getFeatureProportions('Firmicutes')
			assert [p.get_height() for p in ax.patches] == pytest.approx(list(d1) + list(d2))
			colWidth = plot.figColWidth
			assert [p.get_x() for p in ax.patches] == pytest.approx([i * colWidth for i in range(n1 + n2)])  # align='edge'
			assert ax.patches[0].get_facecolor() == hexColour(prefs, GROUP1)
			assert ax.patches[-1].get_facecolor() == hexColour(prefs, group2)
			assert texts(ax.get_xticklabels()) == profile.samplesInGroup1 + profile.samplesInGroup2
			assert ax.get_title() == 'Firmicutes' and ax.get_ylabel() == field
			assert [t.get_text() for t in ax.texts] == ['$p$ = ' + results.getFeatureStatisticAsStr('Firmicutes', 'pValuesCorrected')]
			avgLines = ax.lines
			assert len(avgLines) == 2
			assert avgLines[0].get_ydata()[0] == pytest.approx(sum(d1) / len(d1))
			assert avgLines[1].get_ydata()[0] == pytest.approx(sum(d2) / len(d2))
			assert not any(t.tick1line.get_visible() or t.tick2line.get_visible() for t in ax.xaxis.get_major_ticks())
			assert all(t.label1.get_rotation() == 90 for t in ax.xaxis.get_major_ticks())

	plot.bShowAverages = False
	plot.bShowPvalue = False
	for legendPos in (0, 1, 7, 4, 2, 6, 3):
		plot.legendPos = legendPos
		plot.plot(profile, results)
		ax = plot.fig.axes[0]
		assert len(ax.lines) == 0 and len(ax.texts) == 0
		legend = ax.get_legend()
		assert legend._loc == legendPos and texts(legend.get_texts()) == [GROUP1, OTHERS]


def test_bar_plot_empty(prefs, phyla):
	profile, results = phyla
	plot = plotClass('BarPlot')(prefs)
	prefs['Selected group feature'] = ''
	plot.plot(profile, results)
	assertEmpty(plot)


def test_bar_plot_configure_round_trip(prefs, phyla, monkeypatch, settings):
	profile, results = phyla
	prefs['Selected group feature'] = 'Firmicutes'
	cls = plotClass('BarPlot')
	plot = cls(prefs)
	seen = {}

	def edit(ui):
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.spinFigColWidth.setValue(0.3)
		ui.spinFigHeight.setValue(5.0)
		ui.chkShowAverage.setChecked(False)
		ui.radioLegendPosCentreLeft.setChecked(True)
		ui.chkShowPvalue.setChecked(False)

	acceptDialog(monkeypatch, edit, seen)
	plot.configure(profile, results)
	assert seen['initial']['cboFieldToPlot'] == 'Proportion of sequences (%)' and seen['initial']['radioLegendPosNone']
	assert (plot.fieldToPlot, plot.figColWidth, plot.figHeight) == ('Number of sequences', 0.3, 5.0)
	assert (plot.bShowAverages, plot.legendPos, plot.bShowPvalue) == (False, 6, False)
	assert plot.fig.axes[0].get_ylabel() == 'Number of sequences'
	fresh = cls(prefs)
	for attr in ('figColWidth', 'figHeight', 'fieldToPlot', 'bShowAverages', 'legendPos', 'bShowPvalue'):
		assert getattr(fresh, attr) == getattr(plot, attr), attr
	assert settings.value('group: Bar plot/legend position', type=int) == 6


# ---------------------------------------------------------------- box plot

def test_box_plot(data, prefs):
	plot = plotClass('BoxPlot')(prefs)
	for group2 in (GROUP2, OTHERS):
		profile = groupProfile(data, group2=group2)
		results = welch(profile, prefs)
		prefs['Selected group feature'] = 'Bacteroidetes'
		for field in ('Proportion of sequences (%)', 'Number of sequences'):
			plot.fieldToPlot = field
			plot.plot(profile, results)
			ax = plot.fig.axes[0]
			if field == 'Number of sequences':
				d1, d2 = profile.getFeatureCounts('Bacteroidetes')
			else:
				d1, d2 = profile.getFeatureProportions('Bacteroidetes')
			boxes = [p for p in ax.patches if isinstance(p, mpl.patches.Polygon)]
			assert [b.get_facecolor() for b in boxes] == [hexColour(prefs, GROUP1), hexColour(prefs, group2)]
			# filled box spans the quartiles (1.x boxplot, whis=1.5)
			for box, d in zip(boxes, (d1, d2)):
				ys = box.get_xy()[:, 1]
				assert min(ys) == pytest.approx(np.percentile(d, 25)) and max(ys) == pytest.approx(np.percentile(d, 75))
			stars = [l for l in ax.lines if l.get_marker() == '*']
			assert [s.get_ydata()[0] for s in stars] == pytest.approx([np.average(d1), np.average(d2)])
			assert texts(ax.get_xticklabels()) == [GROUP1, group2]
			assert ax.get_title() == 'Bacteroidetes' and ax.get_ylabel() == field
			assert ax.texts[0].get_text() == '$p$ = ' + results.getFeatureStatisticAsStr('Bacteroidetes', 'pValuesCorrected')
			assert all(t.tick1line.get_visible() and not t.tick2line.get_visible() for t in ax.yaxis.get_major_ticks())

	plot.bShowAverages = False
	plot.bShowPvalue = False
	plot.plot(profile, results)
	ax = plot.fig.axes[0]
	assert not [l for l in ax.lines if l.get_marker() == '*'] and len(ax.texts) == 0


def test_box_plot_empty(prefs, phyla):
	profile, results = phyla
	plot = plotClass('BoxPlot')(prefs)
	plot.plot(profile, results)  # no selected feature
	assertEmpty(plot)


def test_box_plot_configure_round_trip(prefs, phyla, monkeypatch, settings):
	profile, results = phyla
	prefs['Selected group feature'] = 'Firmicutes'
	cls = plotClass('BoxPlot')
	plot = cls(prefs)
	seen = {}

	def edit(ui):
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.spinFigWidth.setValue(5.0)
		ui.spinFigHeight.setValue(6.0)
		ui.chkShowAverage.setChecked(False)
		ui.chkShowPvalue.setChecked(False)

	acceptDialog(monkeypatch, edit, seen)
	plot.configure(profile, results)
	assert seen['initial']['spinFigWidth'] == 7.0 and seen['initial']['chkShowAverage']
	assert (plot.fieldToPlot, plot.figWidth, plot.figHeight, plot.bShowAverages, plot.bShowPvalue) == ('Number of sequences', 5.0, 6.0, False, False)
	assert tuple(plot.fig.get_size_inches()) == (5.0, 6.0)
	# upstream writes the width under '/column width' but reads '/width' (kept as is)
	assert settings.value('group: Box plot/column width', type=float) == 5.0
	fresh = cls(prefs)
	assert (fresh.figWidth, fresh.figHeight, fresh.fieldToPlot, fresh.bShowAverages, fresh.bShowPvalue) == (7.0, 6.0, 'Number of sequences', False, False)


# ---------------------------------------------------------------- heatmap

def test_heatmap_dendrogram_layout(prefs, phyla):
	import scipy.cluster.hierarchy as cluster
	import scipy.spatial.distance as dist
	profile, results = phyla
	plot = plotClass('HeatmapPlot')(prefs)
	plot.plot(profile, results)
	axes = plot.fig.axes
	assert len(axes) == 6  # row dendrogram, column dendrogram, two cluster bars, heatmap, colour bar
	rowDendrogram, colDendrogram = axes[0], axes[1]
	# root on the left, leaves next to the heatmap (upstream's scipy < 0.17 'right')
	assert rowDendrogram.get_xlim()[0] > rowDendrogram.get_xlim()[1]
	assert colDendrogram.get_ylim()[0] < colDendrogram.get_ylim()[1]

	features = list(profile.profileDict.keys())
	d1, d2 = profile.getActiveFeatureProportions(features)
	matrix = np.array([list(a) + list(b) for a, b in zip(d1, d2)])
	link = cluster.linkage(dist.squareform(dist.pdist(matrix)), method='average')
	rowLeaves = cluster.dendrogram(link, no_plot=True)['leaves']
	link = cluster.linkage(dist.squareform(dist.pdist(matrix.T)), method='average')
	colLeaves = cluster.dendrogram(link, no_plot=True)['leaves']

	heatmap = axes[4]
	image = heatmap.images[0].get_array()
	assert image.shape == (len(features), len(colLeaves))
	assert np.allclose(image, matrix[:, colLeaves][rowLeaves, :])
	samples = profile.samplesInGroup1 + profile.samplesInGroup2
	labels = [t.get_text().strip() for t in heatmap.texts]
	assert labels[:len(features)] == [features[i] for i in rowLeaves]
	assert labels[len(features):] == [samples[i] for i in colLeaves]
	assert heatmap.images[0].cmap.name == 'Blues'

	colourBar = axes[5]
	assert colourBar.get_title() == 'abundance (%)'
	assert texts(colourBar.get_xticklabels()) == ['%.1f' % matrix.min(), '%.1f' % (0.5 * (matrix.max() - matrix.min()) + matrix.min()), '%.1f' % matrix.max()]
	assert len(plot.plotEventHandler.data) == matrix.size
	legend = plot.fig.legends[0]
	assert texts(legend.get_texts()) == [GROUP1, GROUP2] and legend._loc == 3


def test_heatmap_every_option(data, prefs):
	from stamp.plugins.groups.plots.configGUI.HeatmapPlotUI import Ui_HeatmapPlotDialog
	rowMethods = comboItems(Ui_HeatmapPlotDialog, 'cboRowSortMethod')
	colMethods = comboItems(Ui_HeatmapPlotDialog, 'cboColSortMethod')
	colourMaps = comboItems(Ui_HeatmapPlotDialog, 'cboColourMap')
	assert len(colourMaps) == 14 and 'Spectral' in colourMaps and 'Mean abundance' in rowMethods
	cls = plotClass('HeatmapPlot')
	profile = groupProfile(data, group2=OTHERS)
	results = welch(profile, prefs, signLevel=0.5)
	nActive = len(results.getActiveFeatures())

	for rowMethod in rowMethods:
		for colMethod in colMethods:
			plot = cls(prefs)
			plot.sortRowMethod, plot.sortColMethod = rowMethod, colMethod
			plot.plot(profile, results)
			clustered = [m not in ('Alphabetical order', 'Mean abundance') for m in (rowMethod, colMethod)]
			assert len(plot.fig.axes) == 2 + 2 * sum(clustered), (rowMethod, colMethod)
			heatmap = [a for a in plot.fig.axes if a.images and a.texts][0]
			rowLabels = [t.get_text().strip() for t in heatmap.texts][:len(profile.profileDict)]
			if rowMethod == 'Alphabetical order':
				assert rowLabels == sorted(rowLabels, reverse=True)
			if rowMethod == 'Mean abundance':
				means = heatmap.images[0].get_array().mean(axis=1)
				assert list(means) == sorted(means)

	plot = cls(prefs)
	for colourMap in colourMaps:
		plot.colourmap = colourMap
		plot.plot(profile, results)
		assert plot.matrixColourmap.name in ('Blues', 'brg', 'bwr', 'cool', 'gist_yarg', 'jet', 'OrRd', 'Paired', 'PRGn',
												'Reds', 'RdBu', 'RdYlBu', 'nipy_spectral', 'YlOrRd')

	plot.fieldToPlot = 'Number of sequences'
	plot.bPlotOnlyActiveFeatures = True
	plot.bShowRowDendrogram = False
	plot.bShowColDendrogram = False
	for legendPos in (1, 4, 2, 3, -1):
		plot.legendPos = legendPos
		plot.plot(profile, results)
		heatmap = [a for a in plot.fig.axes if a.images and a.texts][0]
		assert heatmap.images[0].get_array().shape[0] == nActive
		assert [a for a in plot.fig.axes if a.get_title() == '# sequences']
		assert len(plot.fig.legends) == (0 if legendPos == -1 else 1)
	assert '%' not in plot.plotEventHandler.data[0][2]


def test_heatmap_empty(prefs, phyla):
	profile, results = phyla
	results.filterFeatures(0.0, None, None, None, None, None, None, None, None, 'OR', None, None)
	plot = plotClass('HeatmapPlot')(prefs)
	plot.bPlotOnlyActiveFeatures = True
	plot.plot(profile, results)
	assertEmpty(plot)


def test_heatmap_configure_round_trip(prefs, phyla, monkeypatch, settings):
	profile, results = phyla
	cls = plotClass('HeatmapPlot')
	plot = cls(prefs)
	seen = {}

	def edit(ui):
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.chkPlotOnlyActiveFeatures.setChecked(True)
		ui.spinFigWidth.setValue(8.0)
		ui.spinFigHeight.setValue(9.0)
		ui.cboColSortMethod.setCurrentIndex(ui.cboColSortMethod.findText('Ward'))
		ui.cboRowSortMethod.setCurrentIndex(ui.cboRowSortMethod.findText('Centroid'))
		ui.chkShowColDendrogram.setChecked(True)
		ui.chkShowRowDendrogram.setChecked(False)
		ui.cboColourMap.setCurrentIndex(ui.cboColourMap.findText('Spectral'))
		ui.radioLegendPosUpperRight.setChecked(True)
		ui.spinColClusteringThreshold.setValue(0.5)
		ui.spinRowClusteringThreshold.setValue(0.6)
		ui.spinDendrogramColHeight.setValue(1.0)
		ui.spinDendrogramRowWidth.setValue(1.2)

	acceptDialog(monkeypatch, edit, seen)
	plot.configure(profile, results)
	initial = seen['initial']
	assert initial['cboColSortMethod'] == initial['cboRowSortMethod'] == 'Average neighbour (UPGMA)'
	assert initial['cboColourMap'] == 'Blues' and initial['radioLegendPosLowerLeft']
	assert initial['spinColClusteringThreshold'] == 0.75 and initial['spinDendrogramColHeight'] == 1.5
	assert (plot.fieldToPlot, plot.bPlotOnlyActiveFeatures, plot.figWidth, plot.figHeight) == ('Number of sequences', True, 8.0, 9.0)
	assert (plot.sortColMethod, plot.sortRowMethod, plot.bShowColDendrogram, plot.bShowRowDendrogram) == ('Ward', 'Centroid', True, False)
	assert (plot.colourmap, plot.legendPos) == ('Spectral', 1)
	assert (plot.clusteringColThreshold, plot.clusteringRowThreshold, plot.dendrogramHeight, plot.dendrogramWidth) == (0.5, 0.6, 1.0, 1.2)
	assert plot.matrixColourmap.name == 'nipy_spectral'
	fresh = cls(prefs)
	for attr in ('fieldToPlot', 'bPlotOnlyActiveFeatures', 'figWidth', 'figHeight', 'sortColMethod', 'sortRowMethod',
				'bShowColDendrogram', 'bShowRowDendrogram', 'colourmap', 'legendPos', 'clusteringColThreshold',
				'clusteringRowThreshold', 'dendrogramHeight', 'dendrogramWidth'):
		assert getattr(fresh, attr) == getattr(plot, attr), attr


# ---------------------------------------------------------------- PCA

def test_pca_layouts(prefs, data):
	from stamp.metagenomics.PCA import pca
	profile = groupProfile(data)
	results = welch(profile, prefs)
	embedding, capturedVar = pca(profile.getFeatureMatrix())
	pcLabels = ['PC%d (%.1f%%)' % (i + 1, capturedVar[i] * 100) for i in range(3)]
	n1 = len(profile.samplesInGroup1)

	plot = plotClass('pcaPlot')(prefs)
	expected = {(True, True): 3, (True, False): 2, (False, True): 2, (False, False): 1}
	for (pc1vs3, pc3vs2), nAxes in expected.items():
		for fixed in (True, False):
			plot.bShowPC1vsPC3, plot.bShowPC3vsPC2, plot.bFixedPixelsPerUnitDistance = pc1vs3, pc3vs2, fixed
			plot.plot(profile, results)
			axes = plot.fig.axes
			assert len(axes) == nAxes, (pc1vs3, pc3vs2, fixed)
			first = axes[0]
			assert first.get_ylabel() == pcLabels[1]
			offsets = np.vstack([c.get_offsets() for c in first.collections])
			assert np.allclose(offsets[:, 0], embedding[:, 0]) and np.allclose(offsets[:, 1], embedding[:, 1])
			assert len(first.collections[0].get_offsets()) == n1
			assert first.collections[0].get_facecolor()[0].tolist() == list(hexColour(prefs, GROUP1))
			assert first.collections[0].get_edgecolor()[0].tolist() == [0, 0, 0, 1]  # 1.x scatter edges
			xOffset = (max(embedding[:, 0]) - min(embedding[:, 0])) * 0.1
			assert first.get_xlim() == pytest.approx((min(embedding[:, 0]) - xOffset, max(embedding[:, 0]) + xOffset))
			allLabels = [a.get_xlabel() for a in axes] + [a.get_ylabel() for a in axes]
			assert pcLabels[0] in allLabels
			if pc1vs3 or pc3vs2:
				assert pcLabels[2] in allLabels
			if not fixed:
				assert plot.fig.get_size_inches()[1] == pytest.approx(6.0)
			assert len(plot.plotEventHandler.data) == nAxes

	plot.bUniqueShapes = False
	plot.bRotateLabels = False
	plot.markerSize = 50
	for legendPos in (2, 3, 4, 9, 1):
		plot.legendPos = legendPos
		plot.plot(profile, results)
		assert plot.fig.legends[0]._loc == legendPos
		assert plot.fig.axes[0].collections[0].get_sizes()[0] == 50


def test_pca_all_other_samples(prefs, data):
	profile = groupProfile(data, group2=OTHERS)
	results = welch(profile, prefs)
	plot = plotClass('pcaPlot')(prefs)
	plot.legendPos = 1
	plot.plot(profile, results)
	assert texts(plot.fig.legends[0].get_texts()) == [GROUP1, OTHERS]
	assert len(plot.fig.axes[0].collections[1].get_offsets()) == len(profile.samplesInGroup2)


def test_pca_empty(prefs, phyla):
	profile, results = phyla
	plot = plotClass('pcaPlot')(prefs)
	few = types.SimpleNamespace(profileDict={'a': 1}, samplesInGroup1=['s1'], samplesInGroup2=['s2'])
	plot.plot(few, results)
	assertEmpty(plot, 'There are 2 or fewer samples.')


def test_pca_configure_round_trip(prefs, phyla, monkeypatch):
	profile, results = phyla
	cls = plotClass('pcaPlot')
	plot = cls(prefs)
	seen = {}

	def edit(ui):
		ui.spinFigWidth.setValue(6.0)
		ui.chkFixedPixelsPerUnitDistance.click()
		ui.spinFigHeight.setValue(5.0)
		ui.spinMarkerSize.setValue(20)
		ui.chkRotateLabels.setChecked(False)
		ui.chkPC1vsPC3.setChecked(False)
		ui.chkPC3vsPC2.setChecked(True)
		ui.radioLegendPosUpperCentre.setChecked(True)
		ui.chkUniqueShapes.setChecked(False)

	acceptDialog(monkeypatch, edit, seen)
	plot.configure(profile, results)
	assert seen['initial']['chkFixedPixelsPerUnitDistance'] and seen['initial']['radioLegendPosNone']
	assert seen['ui'].spinFigHeight.isEnabled()  # clicked(bool) -> setDisabled (from the .ui)
	assert (plot.figWidth, plot.figHeight, plot.bFixedPixelsPerUnitDistance, plot.markerSize) == (6.0, 5.0, False, 20)
	assert (plot.bRotateLabels, plot.bShowPC1vsPC3, plot.bShowPC3vsPC2, plot.legendPos, plot.bUniqueShapes) == (False, False, True, 9, False)
	assert tuple(plot.fig.get_size_inches()) == (6.0, 5.0) and len(plot.fig.axes) == 2
	fresh = cls(prefs)
	for attr in ('figWidth', 'figHeight', 'bFixedPixelsPerUnitDistance', 'markerSize', 'bRotateLabels', 'bShowPC1vsPC3',
				'bShowPC3vsPC2', 'legendPos', 'bUniqueShapes'):
		assert getattr(fresh, attr) == getattr(plot, attr), attr


# ---------------------------------------------------------------- scatter

def test_scatter_every_spread_method(prefs, data):
	from scipy.stats import linregress
	from stamp.plugins.groups.plots.configGUI.scatterPlotUI import Ui_ScatterPlotDialog
	methods = comboItems(Ui_ScatterPlotDialog, 'cboSpreadMethod')
	assert len(methods) == 7
	profile = groupProfile(data)
	results = welch(profile, prefs)
	g1, g2 = profile.getFeatureProportionsAll()
	means1, means2 = [np.mean(x) for x in g1], [np.mean(x) for x in g2]
	r2 = linregress(means1, means2)[2] ** 2

	plot = plotClass('ScatterPlot')(prefs)
	for method in methods:
		plot.spreadMethod = method
		plot.plot(profile, results)
		assert len(plot.fig.axes) == 3
		ax = plot.fig.axes[0]
		offsets = ax.collections[0].get_offsets()
		assert np.allclose(offsets[:, 0], means1) and np.allclose(offsets[:, 1], means2)
		assert ax.get_xlabel() == GROUP1 + ' (%)' and ax.get_ylabel() == GROUP2 + ' (%)'
		assert ax.texts[0].get_text() == r'R$^2$ = ' + ('%0.3f' % r2)
		spreadLines = [l for l in ax.lines if l.get_color() == 'gray']
		assert len(spreadLines) == (0 if method == 'None' else 1)
		maxProportion = max(max(means1), max(means2)) * 1.05
		assert ax.get_xlim() == pytest.approx((0, maxProportion)) and ax.get_ylim() == pytest.approx((0, maxProportion))
		top, right = plot.fig.axes[1], plot.fig.axes[2]
		assert len(top.patches) == plot.numBins and len(right.patches) == plot.numBins
		assert top.get_xlim() == ax.get_xlim()
		assert len(plot.plotEventHandler.data) == len(means1)


def test_scatter_options_highlight_and_others(prefs, data):
	profile = groupProfile(data, group2=OTHERS)
	results = welch(profile, prefs)
	prefs['Highlighted group features'] = ['Firmicutes', 'Proteobacteria']
	plot = plotClass('ScatterPlot')(prefs)
	plot.bShowHistograms = False
	plot.bShowR2 = False
	plot.markerSize = 35
	plot.numBins = 10
	plot.plot(profile, results)
	assert len(plot.fig.axes) == 1
	ax = plot.fig.axes[0]
	assert len(ax.texts) == 0
	assert len(ax.collections) == 2
	highlighted = ax.collections[1]
	assert len(highlighted.get_offsets()) == 2
	assert highlighted.get_edgecolor()[0].tolist() == [1, 0, 0, 1] and highlighted.get_linewidths()[0] == 2
	assert ax.collections[0].get_sizes()[0] == 35
	assert ax.get_ylabel() == OTHERS + ' (%)'
	assert ax.spines['top'].get_edgecolor()[3] == 0

	plot.bShowHistograms = True
	plot.plot(profile, results)
	assert len(plot.fig.axes[1].patches) == 10


def test_scatter_empty(prefs, phyla):
	profile, results = phyla
	plot = plotClass('ScatterPlot')(prefs)
	plot.plot(types.SimpleNamespace(profileDict={}), results)
	assertEmpty(plot)


def test_scatter_configure_round_trip(prefs, phyla, monkeypatch, settings):
	profile, results = phyla
	cls = plotClass('ScatterPlot')
	plot = cls(prefs)
	seen = {}

	def edit(ui):
		ui.spinFigWidth.setValue(6.0)
		ui.spinFigHeight.setValue(6.5)
		ui.cboSpreadMethod.setCurrentIndex(ui.cboSpreadMethod.findText('standard deviation'))
		ui.spinNumBins.setValue(20)
		ui.spinHistogramSize.setValue(0.75)
		ui.chkShowHistogram.click()
		ui.spinMarkerSize.setValue(25)
		ui.chkShowR2.setChecked(False)

	acceptDialog(monkeypatch, edit, seen)
	plot.configure(profile, results)
	initial = seen['initial']
	assert initial['cboSpreadMethod'] == '2nd and 98th percentile' and initial['spinNumBins'] == 30
	assert initial['chkShowHistogram'] and initial['spinMarkerSize'] == 20
	assert not seen['ui'].spinNumBins.isEnabled()  # chkShowHistogram.clicked -> setEnabled (from the .ui)
	assert (plot.figWidth, plot.figHeight, plot.spreadMethod, plot.numBins, plot.histogramSize) == (6.0, 6.5, 'standard deviation', 20, 0.75)
	assert (plot.bShowHistograms, plot.markerSize, plot.bShowR2) == (False, 25, False)
	assert len(plot.fig.axes) == 1
	fresh = cls(prefs)
	for attr in ('figWidth', 'figHeight', 'spreadMethod', 'histogramSize', 'bShowHistograms', 'markerSize', 'bShowR2'):
		assert getattr(fresh, attr) == getattr(plot, attr), attr
	# upstream writes bins under '/bin' but reads '/bins' (kept as is)
	assert settings.value('group: Scatter plot/bin', type=int) == 20 and fresh.numBins == 30


# ---------------------------------------------------------------- dialog helpers

def test_configure_dialog_centres(app):
	from stamp.plugins.groups.AbstractGroupPlotPlugin import ConfigureDialog
	from stamp.plugins.groups.plots.configGUI.BoxPlotUI import Ui_BoxPlotDialog
	dlg = ConfigureDialog(Ui_BoxPlotDialog)
	assert isinstance(dlg, QtWidgets.QDialog)
	screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
	assert dlg.x() == (screen.width() - dlg.geometry().width()) // 2
