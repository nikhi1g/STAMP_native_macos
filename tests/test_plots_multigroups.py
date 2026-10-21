'''Headless tests for the multiple group plot plugins (stamp/stamp/plugins/multiGroups/plots).

Every plot is drawn from real Enterotypes ANOVA + eta-squared results, with each option its
settings expose, then saved to png/pdf/svg at 300 dpi. Each configure dialog is driven through
its OK path by emitting the button box's accepted() signal, which the generated UI connects to
QDialog.accept.
'''

import copy
import os
import struct
import sys
import types

import pytest

from PyQt6 import QtCore, QtGui, QtWidgets

import matplotlib as mpl
from matplotlib.collections import PathCollection, LineCollection
from matplotlib.patches import Rectangle, Polygon

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stamp', 'examples', 'EnterotypesArumugam')

ACTIVE_GROUPS = ['Enterotype 1', 'Enterotype 2', 'Enterotype 3', 'Infant']
GROUP_SIZES = [8, 6, 18, 4]
NUM_SAMPLES = sum(GROUP_SIZES)
FEATURE = 'Bacteroidetes'		# ANOVA p = 7.77e-8 on the four active groups
POST_HOC_TESTS = ['GamesHowell', 'Scheffe', 'TukeyKramer', 'WelchUncorrected']


# ---------------------------------------------------------------------------
# Work-arounds for files owned by other workers (applied only while they are unported).

def _stubPlotEventHandler():
	# stamp/plugins/PlotEventHandler.py is not importable until its owner ports it to PyQt6; the plots
	# only construct the handlers and pass them to mpl_connect, so a stub is enough here.
	try:
		import stamp.plugins.PlotEventHandler  # noqa: F401
	except ImportError:
		mod = types.ModuleType('stamp.plugins.PlotEventHandler')

		class PlotEventHandler(object):
			def __init__(self, *args, **kwargs):
				self.args = args

			def __call__(self, event):
				pass

		mod.PlotEventHandler = PlotEventHandler
		mod.MultiPlotEventHandler = PlotEventHandler
		sys.modules['stamp.plugins.PlotEventHandler'] = mod


def _fixGetPValueStr():
	# MultiGroupStatTestResults.getPValueStr compares the formatted *string* with a float, a
	# TypeError on Python 3 for any p < 0.01 (Python 2 always evaluated it False).
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatTestResults
	try:
		MultiGroupStatTestResults({'Minimum reported p-value exponent': -15}).getPValueStr(0.001)
	except TypeError:
		def getPValueStr(self, pValue):
			if pValue < 0.01:
				valueStr = '%.2e' % pValue
				if pValue < 10**self.preferences['Minimum reported p-value exponent']:
					valueStr = '< 1e' + str(int(self.preferences['Minimum reported p-value exponent']))
				elif 'e-00' in valueStr:
					valueStr = valueStr.replace('e-00', 'e-')
				elif 'e-0' in valueStr:
					valueStr = valueStr.replace('e-0', 'e-')
			else:
				valueStr = '%.3f' % pValue
			return valueStr
		MultiGroupStatTestResults.getPValueStr = getPValueStr


# ---------------------------------------------------------------------------
# Fixtures

@pytest.fixture(scope='module')
def app():
	_stubPlotEventHandler()
	_fixGetPValueStr()
	a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
	yield a


@pytest.fixture(scope='module')
def tree():
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
	prefs = {'Pseudocount': 0.5, 'Replicates': 1000}
	t, err = StampIO(prefs).read(os.path.join(EX, 'Enterotypes.profile.spf'))
	md, err = MetadataIO(prefs).read(os.path.join(EX, 'Enterotypes.metadata.tsv'), t)
	md.setActiveField('Enterotype', t)
	return t, md


def makeProfile(tree, activeGroups):
	t, md = tree
	for g in t.groupActive:
		t.groupActive[g] = g in activeGroups
	return t.createMultiGroupProfile(list(t.groupDict.keys()), 'Entire sample', t.hierarchyHeadings[0], md, 'Remove unclassified reads')


def runStats(profile, prefs, correction='NoCorrection'):
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatsTests
	from stamp.plugins.multiGroups.statisticalTests.ANOVA import ANOVA
	from stamp.plugins.multiGroups.effectSizeFilters.EtaSquared import EtaSquared
	mod = __import__('stamp.plugins.common.multipleComparisonCorrections.' + correction, fromlist=[correction])
	m = MultiGroupStatsTests(prefs)
	m.run(ANOVA(prefs), EtaSquared(prefs), profile)
	m.results.performMultCompCorrection(getattr(mod, correction)(prefs))
	m.results.selectAllFeautres()
	m.results.filterFeatures(0.05, None, 0)		# as STAMP does with the default p-value filter
	return m


@pytest.fixture
def prefs(app):
	settings = QtCore.QSettings('BeikoLab', 'STAMP-test')
	settings.clear()
	p = {}
	p['Settings'] = settings
	p['Pseudocount'] = 0.5
	p['Replicates'] = 1000
	p['Truncate feature names'] = True
	p['Length of truncated feature names'] = 50
	p['Axes colour'] = QtGui.QColor('#7f7f7f')
	p['All other samples colour'] = QtGui.QColor('#7f7f7f')
	p['Minimum reported p-value exponent'] = -15
	p['Sample 1 colour'] = QtGui.QColor(128, 177, 211)
	p['Sample 2 colour'] = QtGui.QColor(253, 180, 98)
	p['Group colours'] = {'Enterotype 1': QtGui.QColor(141, 211, 199), 'Enterotype 2': QtGui.QColor(255, 255, 179),
							'Enterotype 3': QtGui.QColor(190, 186, 218), 'Infant': QtGui.QColor(251, 128, 114),
							'Enterotype 3 - twin': QtGui.QColor(128, 177, 211), 'Unclassified': QtGui.QColor(253, 180, 98)}
	p['Highlighted sample features'] = []
	p['Highlighted group features'] = []
	p['Highlighted multiple group features'] = []
	p['Selected group feature'] = ''
	p['Selected multiple group feature'] = FEATURE
	p['Last directory'] = ''
	yield p
	settings.clear()


@pytest.fixture(scope='module')
def data(app, tree):
	statPrefs = {'Pseudocount': 0.5, 'Replicates': 1000, 'Minimum reported p-value exponent': -15}
	profile = makeProfile(tree, ACTIVE_GROUPS)
	stats = runStats(profile, statPrefs)
	statsBonf = runStats(profile, statPrefs, 'Bonferroni')
	smallProfile = makeProfile(tree, ['Unclassified'])		# 2 samples: degenerate for PCA
	return profile, stats, statsBonf, smallProfile


def assertSaves(plot, tmp_path, stem):
	w, h = plot.fig.get_size_inches()
	for ext in ['png', 'pdf', 'svg']:
		f = str(tmp_path / (stem + '.' + ext))
		plot.savePlot(f, dpi=300)
		assert os.path.exists(f), f
		assert os.path.getsize(f) > 2000, f
	with open(str(tmp_path / (stem + '.png')), 'rb') as fh:
		header = fh.read(24)
	pw, ph = struct.unpack('>II', header[16:24])
	assert abs(pw - w * 300) <= 1 and abs(ph - h * 300) <= 1, (pw, ph, w, h)


def assertEmpty(plot, title=''):
	axes = plot.fig.get_axes()
	assert len(axes) == 1
	assert axes[0].get_xlabel() == 'No active features or degenerate plot'
	assert axes[0].get_title() == title


def tickVisible(axis, which):
	tick = axis.get_major_ticks()[0]
	return (tick.tick1line if which == 1 else tick.tick2line).get_visible()


def acceptWith(monkeypatch, changes):
	'''Make ConfigureDialog.exec apply widget changes and take the OK path.'''
	from stamp.plugins.multiGroups.AbstractMultiGroupPlotPlugin import ConfigureDialog
	seen = {}

	def fakeExec(dlg):
		seen['dlg'] = dlg
		seen['before'] = changes(dlg.ui)
		dlg.ui.buttonBox.accepted.emit()		# connected to QDialog.accept by the generated UI
		return dlg.result()

	monkeypatch.setattr(ConfigureDialog, 'exec', fakeExec)
	return seen


def newPlot(name, prefs):
	mod = __import__('stamp.plugins.multiGroups.plots.' + name, fromlist=[name])
	return getattr(mod, name)(prefs)


# ---------------------------------------------------------------------------
# Interface (what PlotsManager / STAMP.py use)

@pytest.mark.parametrize('name,plotName,plotType,individually', [
	('BarPlot', 'Bar plot', 'Exploratory', True),
	('BoxPlot', 'Box plot', 'Exploratory', True),
	('HeatmapPlot', 'Heatmap plot', 'Exploratory', False),
	('pcaPlot', 'PCA plot', 'Exploratory', False),
	('PostHocPlot', 'Post-hoc plot', 'Statistical', True),
])
def test_interface(prefs, name, plotName, plotType, individually):
	plot = newPlot(name, prefs)
	assert plot.name == plotName and plot.type == plotType
	assert plot.bSupportsHighlight is False
	assert plot.bPlotFeaturesIndividually is individually
	assert plot.bRunPostHocTest is (name == 'PostHocPlot')
	for attr in ['plot', 'configure', 'savePlot', 'mirrorProperties', 'mouseEventCallback', 'emptyAxis', 'get_width_height', 'clear']:
		assert callable(getattr(plot, attr)), attr
	plot.emptyAxis()		# what PlotsManager.display does before any data is loaded
	assertEmpty(plot)
	other = newPlot(name, prefs)
	other.mirrorProperties(plot)
	assert other.name == plot.name
	w, h = plot.get_width_height()
	assert (w, h) == (576, 384)		# 6 x 4 inches at 96 dpi
	plot.mouseEventCallback(lambda event: None)
	plot.mouseEventCallback(lambda event: None)		# reconnect path
	assert mpl.rcParams['xtick.direction'] == mpl.rcParamsDefault['xtick.direction']		# rc restored


def test_ui_modules_generated_by_pyuic6():
	here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stamp', 'stamp', 'plugins', 'multiGroups', 'plots', 'configGUI')
	for name in ['BarPlot', 'BoxPlot', 'HeatmapPlot', 'pcaPlot', 'PostHocPlot']:
		with open(os.path.join(here, name + 'UI.py')) as fh:
			src = fh.read()
		assert 'PyQt6 UI code generator' in src
		assert "reading ui file '" + name + ".ui'" in src


# ---------------------------------------------------------------------------
# Bar plot

@pytest.mark.parametrize('field', ['Proportion of sequences (%)', 'Number of sequences'])
@pytest.mark.parametrize('legendPos', [-1, 0, 1, 7, 4, 2, 6, 3])
def test_bar_plot(prefs, data, tmp_path, field, legendPos):
	profile, stats, statsBonf, _ = data
	plot = newPlot('BarPlot', prefs)
	plot.fieldToPlot = field
	plot.legendPos = legendPos
	plot.plot(profile, stats.results)

	axes = plot.fig.get_axes()
	assert len(axes) == 1
	ax = axes[0]
	bars = [p for p in ax.patches if isinstance(p, Rectangle)]
	assert len(bars) == NUM_SAMPLES
	assert bars[0].get_x() == pytest.approx(0.0)		# align='edge' (matplotlib 1.4 default)
	assert bars[0].get_width() == pytest.approx(0.2 * 0.9 / 2)
	assert tuple(bars[0].get_edgecolor()) == (0, 0, 0, 1)		# 1.4 patches had black edges
	assert len(ax.get_lines()) == len(ACTIVE_GROUPS)		# average lines
	assert ax.get_title() == FEATURE
	assert ax.get_ylabel() == field
	assert [t.get_text() for t in ax.texts] == [r'$p$ = 7.77e-8']
	labels = [t.get_text() for t in ax.get_xticklabels()]
	assert len(labels) == NUM_SAMPLES and labels[0] == profile.activeSamplesInGroups[0][0]
	assert not tickVisible(ax.xaxis, 1) and not tickVisible(ax.yaxis, 2)
	if legendPos == -1:
		assert ax.get_legend() is None
	else:
		assert [t.get_text() for t in ax.get_legend().get_texts()] == ACTIVE_GROUPS
	if field == 'Number of sequences':
		assert max(b.get_height() for b in bars) > 100
	else:
		assert max(b.get_height() for b in bars) <= 100
	if legendPos in (-1, 1):
		assertSaves(plot, tmp_path, 'bar')


def test_bar_plot_options(prefs, data):
	profile, stats, statsBonf, _ = data
	plot = newPlot('BarPlot', prefs)
	plot.bShowAverages = False
	plot.bShowPvalue = False
	prefs['Highlighted multiple group features'] = [FEATURE, 'Firmicutes']
	prefs['Selected multiple group feature'] = 'Firmicutes'
	plot.plot(profile, statsBonf.results)
	ax = plot.fig.get_axes()[0]
	assert len(ax.get_lines()) == 0 and len(ax.texts) == 0
	assert ax.get_title() == 'Firmicutes'
	plot.bShowPvalue = True
	plot.plot(profile, statsBonf.results)
	ax = plot.fig.get_axes()[0]
	assert ax.texts[0].get_text() == r'$p$ = ' + statsBonf.results.getFeatureStatisticAsStr('Firmicutes', 'pValuesCorrected')
	assert ax.texts[0].get_text() != r'$p$ = ' + stats.results.getFeatureStatisticAsStr('Firmicutes', 'pValuesCorrected')
	# truncated feature name
	prefs['Length of truncated feature names'] = 4
	plot.plot(profile, statsBonf.results)
	assert plot.fig.get_axes()[0].get_title() == 'Firm...'


def test_bar_plot_empty(prefs, data):
	profile, stats, _, _ = data
	plot = newPlot('BarPlot', prefs)
	prefs['Selected multiple group feature'] = ''
	plot.plot(profile, stats.results)
	assertEmpty(plot)
	from stamp.metagenomics.MultiGroupProfile import MultiGroupProfile
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatTestResults
	prefs['Selected multiple group feature'] = FEATURE
	plot.plot(MultiGroupProfile(), MultiGroupStatTestResults(prefs))
	assertEmpty(plot)


def test_bar_plot_configure(prefs, data, monkeypatch):
	profile, stats, _, _ = data
	plot = newPlot('BarPlot', prefs)

	def change(ui):
		before = (str(ui.cboFieldToPlot.currentText()), ui.spinFigColWidth.value(), ui.spinFigHeight.value(),
					ui.chkShowAverage.isChecked(), ui.radioLegendPosNone.isChecked(), ui.chkShowPvalue.isChecked())
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.spinFigColWidth.setValue(0.3)
		ui.spinFigHeight.setValue(5.0)
		ui.chkShowAverage.setChecked(False)
		ui.radioLegendPosCentreLeft.setChecked(True)
		ui.chkShowPvalue.setChecked(False)
		return before

	seen = acceptWith(monkeypatch, change)
	plot.configure(profile, stats.results)
	assert seen['before'] == ('Proportion of sequences (%)', 0.2, 6.0, True, True, True)
	assert (plot.fieldToPlot, plot.figColWidth, plot.figHeight, plot.bShowAverages, plot.legendPos, plot.bShowPvalue) == \
			('Number of sequences', 0.3, 5.0, False, 6, False)
	s = prefs['Settings']
	k = 'multiple group: Bar plot/'
	assert s.value(k + 'column width', type=float) == 0.3
	assert s.value(k + 'height', type=float) == 5.0
	assert s.value(k + 'field to plot', type=str) == 'Number of sequences'
	assert s.value(k + 'show averages', type=bool) is False
	assert s.value(k + 'legend position', type=int) == 6
	assert s.value(k + 'show p-value', type=bool) is False
	# settings round-trip into a new instance
	again = newPlot('BarPlot', prefs)
	assert (again.fieldToPlot, again.figColWidth, again.legendPos, again.bShowAverages) == ('Number of sequences', 0.3, 6, False)
	assert plot.fig.get_axes()[0].get_legend() is not None		# configure re-plotted


# ---------------------------------------------------------------------------
# Box plot

@pytest.mark.parametrize('field', ['Proportion of sequences (%)', 'Number of sequences'])
@pytest.mark.parametrize('averages,pvalue', [(True, True), (False, False)])
def test_box_plot(prefs, data, tmp_path, field, averages, pvalue):
	profile, stats, _, _ = data
	plot = newPlot('BoxPlot', prefs)
	plot.fieldToPlot = field
	plot.bShowAverages = averages
	plot.bShowPvalue = pvalue
	plot.plot(profile, stats.results)

	axes = plot.fig.get_axes()
	assert len(axes) == 1
	ax = axes[0]
	assert len([p for p in ax.patches if isinstance(p, Polygon)]) == len(ACTIVE_GROUPS)
	assert ax.get_xlim() == (0.5, len(ACTIVE_GROUPS) + 0.5)		# set by matplotlib 1.4 boxplot
	assert [t.get_text() for t in ax.get_xticklabels()] == ACTIVE_GROUPS
	stars = [l for l in ax.get_lines() if l.get_marker() == '*']
	assert len(stars) == (len(ACTIVE_GROUPS) if averages else 0)
	assert ax.get_title() == FEATURE and ax.get_ylabel() == field
	assert len(ax.texts) == (1 if pvalue else 0)
	assert tickVisible(ax.xaxis, 1) and not tickVisible(ax.xaxis, 2)
	assert ax.xaxis.get_major_ticks()[0]._tickdir == 'in'		# matplotlib 1.4 tick direction
	assert plot.fig.get_size_inches().tolist() == [7.0, 7.0]
	if averages:
		assertSaves(plot, tmp_path, 'box')


def test_box_plot_empty_and_configure(prefs, data, monkeypatch):
	profile, stats, _, _ = data
	plot = newPlot('BoxPlot', prefs)
	prefs['Selected multiple group feature'] = ''
	plot.plot(profile, stats.results)
	assertEmpty(plot)
	prefs['Selected multiple group feature'] = FEATURE

	def change(ui):
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.spinFigWidth.setValue(5.5)
		ui.spinFigHeight.setValue(4.5)
		ui.chkShowAverage.setChecked(False)
		ui.chkShowPvalue.setChecked(False)
		return None

	acceptWith(monkeypatch, change)
	plot.configure(profile, stats.results)
	assert (plot.fieldToPlot, plot.figWidth, plot.figHeight, plot.bShowAverages, plot.bShowPvalue) == \
			('Number of sequences', 5.5, 4.5, False, False)
	s = prefs['Settings']
	k = 'multiple group: Box plot/'
	assert s.value(k + 'column width', type=float) == 5.5		# upstream stores the width under this key
	assert s.value(k + 'field to plot', type=str) == 'Number of sequences'
	assert plot.fig.get_size_inches().tolist() == [5.5, 4.5]


# ---------------------------------------------------------------------------
# Heatmap plot

ROW_METHODS = ['Alphabetical order', 'Mean abundance', 'Average neighbour (UPGMA)', 'Centroid', 'Furthest neighbour', 'Nearest neighbour', 'Ward']
COL_METHODS = ['Alphabetical order', 'Average neighbour (UPGMA)', 'Centroid', 'Furthest neighbour', 'Nearest neighbour', 'Ward']
COLOUR_MAPS = ['Blues', 'Blue to red to green', 'Blue to white to red', 'Cool to warm', 'Grayscale', 'Jet', 'Orange to red',
				'Paired', 'Purple to green', 'Reds', 'Red to blue', 'Red to yellow to blue', 'Spectral', 'Yellow to orange to red']


@pytest.mark.parametrize('rowMethod', ROW_METHODS)
@pytest.mark.parametrize('colMethod', COL_METHODS)
def test_heatmap_sorting(prefs, data, rowMethod, colMethod):
	profile, stats, _, _ = data
	plot = newPlot('HeatmapPlot', prefs)
	plot.sortRowMethod = rowMethod
	plot.sortColMethod = colMethod
	plot.plot(profile, stats.results)

	numFeatures = len(profile.profileDict)
	rowDend = rowMethod not in ('Alphabetical order', 'Mean abundance')
	colDend = colMethod not in ('Alphabetical order', 'Mean abundance')
	# heatmap + colour bar, plus dendrogram and cluster bar axes for each clustered dimension
	assert len(plot.fig.get_axes()) == 2 + 2 * rowDend + 2 * colDend
	heat = [ax for ax in plot.fig.get_axes() if ax.images and ax.images[0].get_array().shape == (numFeatures, NUM_SAMPLES)]
	assert len(heat) == 1
	assert len(heat[0].texts) == numFeatures + NUM_SAMPLES
	assert len(heat[0].get_lines()) == numFeatures + NUM_SAMPLES		# white grid lines
	if rowMethod == 'Alphabetical order':
		rows = [t.get_text().strip() for t in heat[0].texts[:numFeatures]]
		assert rows == sorted(rows, reverse=True)
	if rowDend:
		dend = plot.fig.get_axes()[0]
		assert len(dend.collections) == 1 and isinstance(dend.collections[0], LineCollection)
		xmin, xmax = dend.get_xlim()
		assert xmin > xmax		# root on the left, leaves next to the heatmap (scipy 0.15 'right')
	assert plot.fig.legends and [t.get_text() for t in plot.fig.legends[0].get_texts()] == ACTIVE_GROUPS
	assert plot.fig.legends[0]._ncols == len(ACTIVE_GROUPS) // 2


@pytest.mark.parametrize('colourmap', COLOUR_MAPS)
def test_heatmap_colourmaps(prefs, data, colourmap):
	profile, stats, _, _ = data
	plot = newPlot('HeatmapPlot', prefs)
	plot.colourmap = colourmap
	plot.plot(profile, stats.results)
	expected = {'Spectral': 'nipy_spectral', 'Blues': 'Blues', 'Jet': 'jet', 'Grayscale': 'gist_yarg'}
	if colourmap in expected:
		assert plot.matrixColourmap.name == expected[colourmap]


@pytest.mark.parametrize('field', ['Proportion of sequences (%)', 'Number of sequences'])
@pytest.mark.parametrize('legendPos', [1, 4, 2, 3, -1])
def test_heatmap_options(prefs, data, tmp_path, field, legendPos):
	profile, stats, _, _ = data
	plot = newPlot('HeatmapPlot', prefs)
	plot.fieldToPlot = field
	plot.legendPos = legendPos
	plot.bShowColDendrogram = legendPos != 4
	plot.bShowRowDendrogram = legendPos != 2
	plot.plot(profile, stats.results)
	titles = [ax.get_title() for ax in plot.fig.get_axes()]
	assert ('# sequences' if field == 'Number of sequences' else 'abundance (%)') in titles
	assert bool(plot.fig.legends) == (legendPos != -1)
	if legendPos == 1:
		assertSaves(plot, tmp_path, 'heatmap')


def test_heatmap_active_features_and_empty(prefs, data):
	profile, stats, _, _ = data
	plot = newPlot('HeatmapPlot', prefs)
	plot.bPlotOnlyActiveFeatures = True
	results = copy.copy(stats.results)
	results.activeFeatures = list(stats.results.activeFeatures)
	assert len(results.activeFeatures) > 1
	plot.plot(profile, results)
	heat = [ax for ax in plot.fig.get_axes() if ax.images and ax.images[0].get_array().shape == (len(results.activeFeatures), NUM_SAMPLES)]
	assert len(heat) == 1
	results.activeFeatures = []
	plot.plot(profile, results)
	assertEmpty(plot)


def test_heatmap_configure(prefs, data, monkeypatch):
	profile, stats, _, _ = data
	plot = newPlot('HeatmapPlot', prefs)

	def change(ui):
		before = (str(ui.cboColourMap.currentText()), str(ui.cboRowSortMethod.currentText()), ui.radioLegendPosLowerLeft.isChecked())
		ui.cboFieldToPlot.setCurrentIndex(ui.cboFieldToPlot.findText('Number of sequences'))
		ui.chkPlotOnlyActiveFeatures.setChecked(True)
		ui.spinFigWidth.setValue(8.0)
		ui.spinFigHeight.setValue(9.0)
		ui.cboColSortMethod.setCurrentIndex(ui.cboColSortMethod.findText('Ward'))
		ui.cboRowSortMethod.setCurrentIndex(ui.cboRowSortMethod.findText('Centroid'))
		ui.chkShowColDendrogram.setChecked(False)
		ui.chkShowRowDendrogram.setChecked(True)
		ui.cboColourMap.setCurrentIndex(ui.cboColourMap.findText('Spectral'))
		ui.radioLegendPosUpperRight.setChecked(True)
		ui.spinColClusteringThreshold.setValue(0.5)
		ui.spinRowClusteringThreshold.setValue(0.6)
		ui.spinDendrogramColHeight.setValue(1.0)
		ui.spinDendrogramRowWidth.setValue(1.25)
		return before

	seen = acceptWith(monkeypatch, change)
	plot.configure(profile, stats.results)
	assert seen['before'] == ('Blues', 'Average neighbour (UPGMA)', True)
	assert (plot.fieldToPlot, plot.bPlotOnlyActiveFeatures, plot.figWidth, plot.figHeight) == ('Number of sequences', True, 8.0, 9.0)
	assert (plot.sortColMethod, plot.sortRowMethod, plot.bShowColDendrogram, plot.bShowRowDendrogram) == ('Ward', 'Centroid', False, True)
	assert (plot.colourmap, plot.legendPos) == ('Spectral', 1)
	assert (plot.clusteringColThreshold, plot.clusteringRowThreshold, plot.dendrogramHeight, plot.dendrogramWidth) == (0.5, 0.6, 1.0, 1.25)
	again = newPlot('HeatmapPlot', prefs)
	for attr in ['fieldToPlot', 'bPlotOnlyActiveFeatures', 'figWidth', 'figHeight', 'sortColMethod', 'sortRowMethod',
					'bShowColDendrogram', 'bShowRowDendrogram', 'colourmap', 'legendPos', 'clusteringColThreshold',
					'clusteringRowThreshold', 'dendrogramHeight', 'dendrogramWidth']:
		assert getattr(again, attr) == getattr(plot, attr), attr


# ---------------------------------------------------------------------------
# PCA plot

@pytest.mark.parametrize('pc13,pc32,numAxes', [(True, True, 3), (True, False, 2), (False, True, 2), (False, False, 1)])
@pytest.mark.parametrize('fixed', [True, False])
def test_pca_layouts(prefs, data, tmp_path, pc13, pc32, numAxes, fixed):
	profile, stats, _, _ = data
	plot = newPlot('pcaPlot', prefs)
	plot.bShowPC1vsPC3 = pc13
	plot.bShowPC3vsPC2 = pc32
	plot.bFixedPixelsPerUnitDistance = fixed
	plot.plot(profile, stats.results)
	axes = plot.fig.get_axes()
	assert len(axes) == numAxes
	for ax in axes:
		scatters = [c for c in ax.collections if isinstance(c, PathCollection)]
		assert len(scatters) == len(ACTIVE_GROUPS)
		assert [len(c.get_offsets()) for c in scatters] == GROUP_SIZES
		assert tuple(scatters[0].get_edgecolor()[0]) == (0, 0, 0, 1)		# 1.4 scatter edges were black
		assert scatters[0].get_sizes()[0] == 30
		assert len(ax.get_lines()) == 2		# x = 0 and y = 0 lines
	assert axes[0].get_ylabel().startswith('PC2 (')
	xlabels = [ax.get_xlabel() for ax in axes]
	assert any(l.startswith('PC1 (') for l in xlabels)
	if pc32:
		assert xlabels[1].startswith('PC3 (')
		assert all(t.get_rotation() == 45 for t in axes[1].get_xticklabels())
	if not fixed:
		assert plot.fig.get_size_inches().tolist() == [7.0, 6.0]
	if pc13 and pc32 and fixed:
		assertSaves(plot, tmp_path, 'pca')


@pytest.mark.parametrize('legendPos', [-1, 2, 3, 4, 9, 1])
@pytest.mark.parametrize('unique', [True, False])
def test_pca_legend_and_shapes(prefs, data, legendPos, unique):
	profile, stats, _, _ = data
	plot = newPlot('pcaPlot', prefs)
	plot.legendPos = legendPos
	plot.bUniqueShapes = unique
	plot.bRotateLabels = False
	plot.markerSize = 50
	plot.plot(profile, stats.results)
	assert bool(plot.fig.legends) == (legendPos != -1)
	if legendPos != -1:
		assert [t.get_text() for t in plot.fig.legends[0].get_texts()] == ACTIVE_GROUPS
		assert plot.fig.legends[0]._ncols == len(ACTIVE_GROUPS)
	scatters = [c for c in plot.fig.get_axes()[0].collections if isinstance(c, PathCollection)]
	assert scatters[0].get_sizes()[0] == 50
	paths = set(len(c.get_paths()[0].vertices) for c in scatters)
	assert (len(paths) > 1) == unique


def test_pca_empty_and_configure(prefs, data, monkeypatch):
	profile, stats, _, smallProfile = data
	plot = newPlot('pcaPlot', prefs)
	plot.plot(smallProfile, stats.results)
	assertEmpty(plot, 'There are 2 or fewer active samples.')

	def change(ui):
		before = (ui.spinFigHeight.isEnabled(), ui.spinMarkerSize.value(), ui.radioLegendPosNone.isChecked())
		ui.spinFigWidth.setValue(6.5)
		ui.chkFixedPixelsPerUnitDistance.click()		# connected to spinFigHeight.setDisabled
		ui.spinFigHeight.setValue(5.5)
		ui.spinMarkerSize.setValue(40)
		ui.chkRotateLabels.setChecked(False)
		ui.chkPC1vsPC3.setChecked(False)
		ui.chkPC3vsPC2.setChecked(True)
		ui.radioLegendPosUpperCentre.setChecked(True)
		ui.chkUniqueShapes.setChecked(False)
		return before + (ui.spinFigHeight.isEnabled(),)

	seen = acceptWith(monkeypatch, change)
	plot.configure(profile, stats.results)
	assert seen['before'] == (False, 30, True, True)
	assert (plot.figWidth, plot.figHeight, plot.bFixedPixelsPerUnitDistance, plot.markerSize) == (6.5, 5.5, False, 40)
	assert (plot.bRotateLabels, plot.bShowPC1vsPC3, plot.bShowPC3vsPC2, plot.legendPos, plot.bUniqueShapes) == (False, False, True, 9, False)
	assert len(plot.fig.get_axes()) == 2 and plot.fig.legends
	again = newPlot('pcaPlot', prefs)
	for attr in ['figWidth', 'figHeight', 'bFixedPixelsPerUnitDistance', 'markerSize', 'bRotateLabels', 'bShowPC1vsPC3',
					'bShowPC3vsPC2', 'legendPos', 'bUniqueShapes']:
		assert getattr(again, attr) == getattr(plot, attr), attr


# ---------------------------------------------------------------------------
# Post-hoc plot

def postHocResults(data, test, feature=FEATURE):
	profile, stats, _, _ = data
	mod = __import__('stamp.plugins.multiGroups.postHoc.' + test, fromlist=[test])
	results = copy.copy(stats.results)
	from stamp.metagenomics.stats.MultiGroupStatsTests import PostHocResults
	results.postHocResults = PostHocResults()
	from stamp.metagenomics.stats.MultiGroupStatsTests import MultiGroupStatsTests
	m = MultiGroupStatsTests(stats.preferences)
	m.results = results
	m.runPostHocTest(getattr(mod, test)(stats.preferences), profile, feature, 0.95)
	return results


@pytest.mark.parametrize('test', POST_HOC_TESTS)
@pytest.mark.parametrize('sortingField', ['p-values', 'Effect sizes', 'Group labels'])
@pytest.mark.parametrize('pFilter', [True, False])
def test_post_hoc_plot(prefs, data, tmp_path, test, sortingField, pFilter):
	profile, stats, _, _ = data
	results = postHocResults(data, test)
	plot = newPlot('PostHocPlot', prefs)
	plot.sortingField = sortingField
	plot.bPvalueFilter = pFilter
	plot.plot(profile, results)

	numPairs = len(ACTIVE_GROUPS) * (len(ACTIVE_GROUPS) - 1) // 2
	axes = plot.fig.get_axes()
	if len(axes) == 1 and axes[0].get_xlabel() == 'No active features or degenerate plot':
		assert pFilter		# only the p-value filter can empty this plot
		assert axes[0].get_title() == 'No rows above nominal level.'
		return
	# bar subplot, error bar subplot, p-value twin axis
	assert len(axes) == 3
	axNumSeq, axErrorbar, axRight = axes
	rows = len(axNumSeq.get_yticklabels())
	assert (rows <= numPairs) if pFilter else (rows == numPairs)
	labels = [t.get_text() for t in axNumSeq.get_yticklabels()]
	assert all(' : ' in l for l in labels)
	assert len([p for p in axNumSeq.patches if isinstance(p, Rectangle) and p.get_height() == pytest.approx(0.3)]) == 2 * rows
	assert axErrorbar.get_title() == '95% confidence intervals'
	assert axErrorbar.get_xlabel() == 'Difference in mean proportions (%)'
	assert axNumSeq.get_xlabel() == 'Mean proportion (%)'
	assert axRight.get_ylabel() == 'p-value'
	assert len(axRight.get_yticklabels()) == rows
	assert [t.get_text() for t in plot.fig.texts] == [FEATURE]
	# error bars: 1.4 drew caps (capsize 3) by default
	caps = [l for l in axErrorbar.get_lines() if l.get_marker() in ('|', 3, '_')]
	assert len(caps) == 2
	if sortingField == 'Group labels':
		assert labels == sorted(labels, key=lambda s: s.lower(), reverse=True)
	assert plot.minX < plot.maxX
	if sortingField == 'p-values' and not pFilter:
		assertSaves(plot, tmp_path, 'posthoc_' + test)


@pytest.mark.parametrize('barPlot,pLabels,stdDev,custom', [
	(False, False, False, False), (True, False, True, True), (False, True, True, False), (True, True, False, True)])
def test_post_hoc_options(prefs, data, barPlot, pLabels, stdDev, custom):
	profile, stats, _, _ = data
	results = postHocResults(data, 'TukeyKramer')
	plot = newPlot('PostHocPlot', prefs)
	plot.bShowBarPlot = barPlot
	plot.bShowPValueLabels = pLabels
	plot.bShowStdDev = stdDev
	plot.endCapSize = 4
	plot.bCustomLimits = custom
	plot.minX, plot.maxX = -10.0, 80.0
	plot.bPvalueFilter = False
	plot.plot(profile, results)
	axes = plot.fig.get_axes()
	assert len(axes) == 1 + barPlot + pLabels
	axErrorbar = axes[1] if barPlot else axes[0]
	if custom:
		assert axErrorbar.get_xlim() == (-10.0, 80.0)
	if not barPlot:
		assert len(axErrorbar.get_yticklabels()) == 6
		assert axErrorbar.get_ylim() == (-1, 6)


def test_post_hoc_empty(prefs, data):
	profile, stats, _, _ = data
	plot = newPlot('PostHocPlot', prefs)
	plot.plot(profile, stats.results)		# no post-hoc test run yet
	assertEmpty(plot, 'No post-hoc test results')


def test_post_hoc_configure(prefs, data, monkeypatch):
	profile, stats, _, _ = data
	results = postHocResults(data, 'Scheffe')
	plot = newPlot('PostHocPlot', prefs)

	def change(ui):
		before = (ui.spinMinimumX.isEnabled(), str(ui.cboSortingField.currentText()), ui.spinEndCapSize.value())
		ui.cboSortingField.setCurrentIndex(ui.cboSortingField.findText('Effect sizes'))
		ui.spinFigWidth.setValue(8.0)
		ui.spinFigRowHeight.setValue(0.3)
		ui.chkShowBarPlot.setChecked(True)
		ui.chkPValueLabels.setChecked(False)
		ui.chkCustomLimits.click()		# connected to spinMinimumX/spinMaximumX.setEnabled
		ui.spinMinimumX.setValue(-20.0)
		ui.spinMaximumX.setValue(90.0)
		ui.spinMarkerSize.setValue(20)
		ui.chkShowStdDev.setChecked(True)
		ui.spinEndCapSize.setValue(5)
		ui.chkFilterPvalue.setChecked(False)
		return before + (ui.spinMinimumX.isEnabled(),)

	seen = acceptWith(monkeypatch, change)
	plot.configure(profile, results)
	assert seen['before'] == (False, 'p-values', 0, True)
	assert (plot.sortingField, plot.figWidth, plot.figHeightPerRow, plot.bShowBarPlot, plot.bShowPValueLabels) == ('Effect sizes', 8.0, 0.3, True, False)
	assert (plot.bCustomLimits, plot.minX, plot.maxX, plot.markerSize, plot.bShowStdDev, plot.endCapSize, plot.bPvalueFilter) == \
			(True, -20.0, 90.0, 20, True, 5, False)
	assert plot.fig.get_axes()[1].get_xlim() == (-20.0, 90.0)
	assert QtWidgets.QApplication.overrideCursor() is None		# configure restores the wait cursor
	again = newPlot('PostHocPlot', prefs)
	for attr in ['sortingField', 'figWidth', 'figHeightPerRow', 'bShowBarPlot', 'bShowPValueLabels', 'bCustomLimits',
					'minX', 'maxX', 'markerSize', 'bShowStdDev', 'endCapSize', 'bPvalueFilter']:
		assert getattr(again, attr) == getattr(plot, attr), attr
