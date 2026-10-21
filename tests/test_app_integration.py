# End-to-end run of the real application objects: MainWindow with the real plot
# plugins (no stubs), driven through the 109BL lab-manual CI-5 workflow
# (load profile + metadata, two samples / extended error bar, two groups with
# the p-value filter, multiple groups, save the figure at 300 DPI), then every
# plot of every mode at least once. Offscreen Qt; pytest-qt turns any exception
# raised inside a Qt slot into a test failure.
import os
import struct
import zlib

import pytest
from PyQt6 import QtCore, QtWidgets

from test_gui_mainwindow import (EX, PROFILE, METADATA, activate, comboItems, defaultPreferences,
	isolatedSettings, messageBoxes, loadData, activeCountFromResults)  # noqa: F401 (fixtures)


@pytest.fixture
def STAMP(monkeypatch):
	import stamp.STAMP
	# plots that ask "Continue?" above 200 features: answer Yes, as a user following the manual would
	monkeypatch.setattr(QtWidgets.QMessageBox, 'question',
		staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes))
	return stamp.STAMP


@pytest.fixture
def mainWindow(qtbot, STAMP, isolatedSettings, messageBoxes):
	window = STAMP.MainWindow(defaultPreferences())
	qtbot.addWidget(window)
	return window


def pngSize(path):
	with open(path, 'rb') as f:
		header = f.read(24)
	assert header[:8] == b'\x89PNG\r\n\x1a\n'
	return struct.unpack('>II', header[16:24])


def currentPlotCanvas(window):
	index = window.ui.stackedWidgetViews.currentIndex()
	manager = {2: window.samplePlot, 1: window.groupPlot, 0: window.multiGroupPlot}[index]
	return manager.currentPlot


def test_real_plugins_are_loaded(mainWindow):
	ui = mainWindow.ui
	assert comboItems(ui.cboSamplePlots) == ['Profile bar plot', 'Scatter plot', 'Sequence histogram', '',
		'Bar plot', 'Extended error bar', 'Multiple comparison plots', 'p-value histogram']
	assert comboItems(ui.cboGroupPlots) == ['Bar plot', 'Box plot', 'Heatmap plot', 'PCA plot', 'Scatter plot', '', 'Extended error bar']
	assert comboItems(ui.cboMultiGroupPlots) == ['Bar plot', 'Box plot', 'Heatmap plot', 'PCA plot', '', 'Post-hoc plot']
	assert sorted(mainWindow.sampleStatTestDict) == sorted(['Bootstrap', 'Chi-square test', 'Chi-square test (w/ Yates\')',
		'Difference between proportions', 'Fisher\'s exact test', 'G-test', 'G-test (w/ Yates\') + Fisher\'s',
		'G-test (w/ Yates\')', 'Hypergeometric', 'Permutation'])
	assert sorted(mainWindow.groupStatTestDict) == ['Welch\'s t-test', 'White\'s non-parametric t-test', 't-test (equal variance)']
	assert sorted(mainWindow.multiGroupStatTestDict) == ['ANOVA', 'Kruskal-Wallis H-test']
	assert sorted(mainWindow.postHocTestDict) == ['Games-Howell', 'Scheffè', 'Tukey-Kramer', 'Welch\'s (uncorrected)']
	assert sorted(mainWindow.multCompDict) == ['Benjamini-Hochberg FDR', 'Bonferroni', 'No correction', 'Sidak', 'Storey FDR']


def test_lab_manual_ci5_workflow(mainWindow, monkeypatch, STAMP, messageBoxes, tmp_path):
	ui = mainWindow.ui
	# step 2-3: File > Load data (Ctrl+O), profile + metadata
	assert ui.mnuFileOpenProfile.shortcut().toString() == 'Ctrl+O'
	# upstream main.ui: Ctrl+S = "Save plot...", Ctrl+W = "Send plot to window" (the lab manual's
	# "Ctrl + W and Save" means: send the plot to its own window, then save it from there)
	assert ui.mnuFileSavePlot.shortcut().toString() == 'Ctrl+S'
	assert ui.mnuViewSendPlotToWindow.shortcut().toString() == 'Ctrl+W'
	loadData(mainWindow, monkeypatch, STAMP)
	assert messageBoxes.calls == []

	# two samples, extended error bar
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoSamples))
	activate(ui.cboSamplePlots, 'Extended error bar')
	assert currentPlotCanvas(mainWindow).name == 'Extended error bar'
	assert len(currentPlotCanvas(mainWindow).fig.axes) >= 1

	# two groups, metadata field, extended error bar, p-value filter
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoGroups))
	legend = mainWindow.groupLegendDlg
	legend.findChildren(QtWidgets.QComboBox)[0].setCurrentText('Enterotype')
	activate(ui.cboGroup1, 'Enterotype 1')
	activate(ui.cboGroup2, 'Enterotype 2')
	activate(ui.cboGroupPlots, 'Extended error bar')
	results = mainWindow.groupStatsTest.results
	ui.chkGroupEnableSignLevelFilter.setChecked(True)
	ui.spinGroupSignLevelFilter.setValue(0.05)
	ui.spinGroupSignLevelFilter.editingFinished.emit()
	expected = activeCountFromResults(results, 0.05)
	assert ui.txtGroupNumActiveFeatures.text() == str(expected)
	assert sorted(results.getActiveFeatures()) == sorted(f for f, p in zip(results.getColumn('Features', False), results.getColumn('pValuesCorrected', False)) if p <= 0.05)
	canvas = currentPlotCanvas(mainWindow)
	assert canvas.name == 'Extended error bar'
	labels = [t.get_text() for ax in canvas.fig.axes for t in ax.get_yticklabels() if t.get_text()]
	assert set(results.getActiveFeatures()) <= set(labels)

	# step 8: Ctrl+W, 300 DPI
	outFile = str(tmp_path / 'two_groups_extended_error_bar.png')
	monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: (outFile, 'PNG (*.png)')))
	monkeypatch.setattr(QtWidgets.QInputDialog, 'getInt', staticmethod(lambda *a, **k: (300, True)))
	ui.mnuFileSavePlot.trigger()
	w, h = canvas.fig.get_size_inches()
	assert pngSize(outFile) == (round(w * 300), round(h * 300))

	# multiple groups
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabMultipleGroups))
	assert len(mainWindow.multiGroupStatsTest.results.data) > 0
	activate(ui.cboMultiGroupPlots, 'Post-hoc plot')
	assert currentPlotCanvas(mainWindow).name == 'Post-hoc plot'
	assert messageBoxes.calls == []


@pytest.mark.parametrize('tab,combo,plots', [
	('tabTwoSamples', 'cboSamplePlots', ['Bar plot', 'Profile bar plot', 'Scatter plot', 'Sequence histogram', 'Extended error bar', 'Multiple comparison plots', 'p-value histogram']),
	('tabTwoGroups', 'cboGroupPlots', ['Bar plot', 'Box plot', 'Heatmap plot', 'PCA plot', 'Scatter plot', 'Extended error bar']),
	('tabMultipleGroups', 'cboMultiGroupPlots', ['Bar plot', 'Box plot', 'Heatmap plot', 'PCA plot', 'Post-hoc plot']),
])
def test_every_plot_renders_in_every_mode(mainWindow, monkeypatch, STAMP, messageBoxes, tmp_path, tab, combo, plots):
	ui = mainWindow.ui
	loadData(mainWindow, monkeypatch, STAMP)
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(getattr(ui, tab)))
	for level in mainWindow.profileTree.hierarchyHeadings:
		activate(ui.cboProfileLevel, level)
		for name in plots:
			activate(getattr(ui, combo), name)
			canvas = currentPlotCanvas(mainWindow)
			assert canvas.name == name
			assert len(canvas.fig.axes) >= 1, name
			outFile = str(tmp_path / ('%s_%s_%s.png' % (tab, level, name.replace(' ', '_'))))
			canvas.savePlot(outFile, dpi=72)
			assert os.path.getsize(outFile) > 0
	assert messageBoxes.calls == []


def test_statistical_tests_switch_in_every_mode(mainWindow, monkeypatch, STAMP, messageBoxes):
	ui = mainWindow.ui
	loadData(mainWindow, monkeypatch, STAMP)
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoSamples))
	for name in sorted(mainWindow.sampleStatTestDict):
		if name in ('Bootstrap', 'Permutation test'):
			continue  # Monte Carlo over 247 genera; covered headlessly in test_core_samples
		activate(ui.cboSampleStatTests, name)
		assert mainWindow.sampleStatsTest.results.test == name
	for name in sorted(mainWindow.multCompDict):
		if name == 'Storey FDR':
			continue  # shows a message box when p-values are not uniform; covered in test_core_corrections
		activate(ui.cboSampleMultCompMethod, name)
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoGroups))
	for name in ["t-test (equal variance)", "Welch's t-test"]:
		activate(ui.cboGroupStatTests, name)
		assert mainWindow.groupStatsTest.results.test == name
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabMultipleGroups))
	for name in sorted(mainWindow.multiGroupStatTestDict):
		activate(ui.cboMultiGroupStatTests, name)
		assert mainWindow.multiGroupStatsTest.results.test == name
	for name in sorted(mainWindow.postHocTestDict):
		activate(ui.cboPostHocTest, name)
	assert messageBoxes.calls == []
