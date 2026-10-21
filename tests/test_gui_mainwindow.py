'''Headless tests of the STAMP main window (QT_QPA_PLATFORM=offscreen, see conftest.py).

The plot plugins are ported separately, so plot discovery is redirected to dummy matplotlib canvases
that implement the interface PlotsManager and STAMP.py use. Everything else (stat plugins, dialogs,
data loading, statistics, filtering, tables) is the real code.
'''

import os
import sys
import types

import pytest

# ponytail: metagenomics/DirectoryHelper.py still imports the removed 'imp' module on this branch's base
# (fixed on port/core). Stub it only while that import fails; remove once port/core is merged.
try:
	import stamp.metagenomics.DirectoryHelper  # noqa: F401
except ModuleNotFoundError:
	sys.modules['imp'] = types.SimpleNamespace(is_frozen=lambda name: False)

from PyQt6 import QtCore, QtGui, QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'stamp', 'examples', 'EnterotypesArumugam')
PROFILE = os.path.join(EX, 'Enterotypes.profile.spf')
METADATA = os.path.join(EX, 'Enterotypes.metadata.tsv')

_RealQSettings = QtCore.QSettings


class DummyPlot(FigureCanvasQTAgg):
	'''Minimal plot plugin: the attributes and methods PlotsManager and STAMP.py call on a plot.'''
	plotName = 'Dummy plot'
	plotType = 'Statistical'

	def __init__(self, preferences, parent=None):
		self.fig = Figure(figsize=(3, 2), dpi=50)
		FigureCanvasQTAgg.__init__(self, self.fig)
		self.preferences = preferences
		self.name = self.plotName
		self.type = self.plotType
		self.bSupportsHighlight = True
		self.bPlotFeaturesIndividually = True
		self.bRunPostHocTest = True
		self.calls = []

	def plot(self, profile, statsResults):
		self.calls.append(('plot', profile, statsResults))
		self.fig.clear()
		self.fig.add_subplot(111).plot([0, 1], [0, 1])
		self.draw()

	def emptyAxis(self):
		self.calls.append(('emptyAxis',))

	def configure(self, profile, statsResults):
		self.calls.append(('configure', profile, statsResults))

	def savePlot(self, filename, dpi=300):
		self.fig.savefig(filename, format=filename[len(filename) - 3:len(filename)], dpi=dpi)

	def mirrorProperties(self, plotToCopy):
		self.calls.append(('mirrorProperties', plotToCopy))


DEFAULT_PLOTS = {'samples': 'Scatter plot', 'groups': 'PCA plot', 'multiGroups': 'PCA plot'}


def fakePluginModules(pluginFolder):
	'''Stand-in for loadPluginModules on plot folders: one exploratory plot named like the folder's
	default plot and one statistical plot, each in its own fake module.'''
	kind = pluginFolder.strip('/').split('/')[2]
	exploratory = type('ExploratoryDummy', (DummyPlot,), {'plotName': DEFAULT_PLOTS[kind], 'plotType': 'Exploratory'})
	statistical = type('StatisticalDummy', (DummyPlot,), {'plotName': 'Dummy statistical plot', 'plotType': 'Statistical'})
	return [('ExploratoryDummy', types.SimpleNamespace(ExploratoryDummy=exploratory)),
			('StatisticalDummy', types.SimpleNamespace(StatisticalDummy=statistical))]


class MessageBoxes:
	def __init__(self):
		self.calls = []

	def record(self, kind):
		def f(*args, **kwargs):
			self.calls.append((kind, args))
			return QtWidgets.QMessageBox.StandardButton.Ok
		return staticmethod(f)


@pytest.fixture
def isolatedSettings(monkeypatch, tmp_path):
	'''Route QSettings("BeikoLab", "STAMP") to an ini file so tests never touch the user's preferences.'''
	iniPath = str(tmp_path / 'STAMP.ini')

	class IsolatedSettings(_RealQSettings):
		def __init__(self, *args):
			if len(args) == 2 and all(isinstance(a, str) for a in args):
				_RealQSettings.__init__(self, iniPath, _RealQSettings.Format.IniFormat)
			else:
				_RealQSettings.__init__(self, *args)

	monkeypatch.setattr(QtCore, 'QSettings', IsolatedSettings)
	return iniPath


@pytest.fixture
def messageBoxes(monkeypatch):
	boxes = MessageBoxes()
	for kind in ('information', 'warning', 'critical', 'about'):
		monkeypatch.setattr(QtWidgets.QMessageBox, kind, boxes.record(kind))
	return boxes


def defaultPreferences():
	# the values main() builds when no settings are stored
	return {
		'Pseudocount': 0.5, 'Replicates': 1000, 'Truncate feature names': True,
		'Length of truncated feature names': 50, 'Axes colour': QtGui.QColor('#7f7f7f'),
		'All other samples colour': QtGui.QColor('#7f7f7f'), 'Minimum reported p-value exponent': -15.0,
		'Sample 1 colour': QtGui.QColor(128, 177, 211), 'Sample 2 colour': QtGui.QColor(253, 180, 98),
		'Group colours': {}, 'Highlighted sample features': [], 'Highlighted group features': [],
		'Highlighted multiple group features': [], 'Selected group feature': '',
		'Selected multiple group feature': '', 'Last directory': '',
	}


@pytest.fixture
def STAMP(monkeypatch):
	import stamp.STAMP
	import stamp.plugins.PlotsManager
	monkeypatch.setattr(stamp.plugins.PlotsManager, 'loadPluginModules', fakePluginModules)
	return stamp.STAMP


@pytest.fixture
def mainWindow(qtbot, STAMP, isolatedSettings, messageBoxes):
	window = STAMP.MainWindow(defaultPreferences())
	qtbot.addWidget(window)
	return window


class FakeLoadDataDlg:
	'''Stands in for the File > Load data dialog: returns fixed paths instead of asking the user.'''
	profileFile = PROFILE
	metadataFile = METADATA

	def __init__(self, preferences, parent=None):
		pass

	def exec(self):
		return QtWidgets.QDialog.DialogCode.Accepted

	def getProfileFile(self):
		return self.profileFile

	def getMetadataFile(self):
		return self.metadataFile


def loadData(window, monkeypatch, STAMP, profile=PROFILE, metadata=METADATA):
	monkeypatch.setattr(STAMP, 'LoadDataDlg', type('Dlg', (FakeLoadDataDlg,), {'profileFile': profile, 'metadataFile': metadata}))
	window.ui.mnuFileOpenProfile.trigger()


def comboItems(combo):
	return [combo.itemText(i) for i in range(combo.count())]


def activate(combo, text):
	index = combo.findText(text)
	assert index != -1, (text, comboItems(combo))
	combo.setCurrentIndex(index)
	combo.activated.emit(index)


def activeCountFromResults(results, threshold):
	pValues = results.getColumn('pValuesCorrected', False)
	return len([p for p in pValues if p <= threshold])


def test_window_title_menus_and_shortcuts(mainWindow):
	ui = mainWindow.ui
	assert mainWindow.windowTitle() == 'STAMP - Statistical analysis of metagenomic profiles'
	assert mainWindow.menuBar().isNativeMenuBar() is False

	menus = [a.text() for a in mainWindow.menuBar().actions()]
	assert menus == ['&File', '&View', '&Settings', '&Help']

	fileMenu = [a.text() for a in ui.menu_File.actions() if not a.isSeparator()]
	assert fileMenu == ['Load data...', 'Create STAMP profile from...', 'Append COG categories to IMG/M profile...', 'Save plot...', 'E&xit']
	createMenu = [a.text() for a in ui.menuCreate_profile_from_an_MG_RAST_table.actions()]
	assert createMenu == ['MG-RAST profile', 'BIOM profile', 'RITA profiles', 'mothur data', 'CoMet profiles']
	assert [a.text() for a in ui.menuSettings.actions()] == ['&Preferences...']
	assert [a.text() for a in ui.menu_Help.actions()] == ['&About...']

	viewMenu = [(a.text(), a.shortcut().toString()) for a in ui.menuView.actions() if not a.isSeparator()]

	assert viewMenu == [('Send plot to &window', 'Ctrl+W'), ('Properties', 'Ctrl+P'),
						('Group legend', 'Ctrl+L'), ('Metadata table', 'Ctrl+M'),
						('Two sample statistics table', 'Ctrl+T'), ('Two group statistics table', 'Ctrl+G'),
						('Multiple group statistics table', 'Ctrl+M')]

	shortcuts = {a.objectName(): a.shortcut().toString() for a in (ui.mnuFileOpenProfile, ui.mnuFileSavePlot, ui.mnuFileExit, ui.mnuViewSendPlotToWindow)}
	assert shortcuts == {'mnuFileOpenProfile': 'Ctrl+O', 'mnuFileSavePlot': 'Ctrl+S', 'mnuFileExit': 'Ctrl+Q', 'mnuViewSendPlotToWindow': 'Ctrl+W'}
	# Qt maps Ctrl to Command on macOS: the portable text stays 'Ctrl+O'
	assert ui.mnuFileOpenProfile.shortcut() == QtGui.QKeySequence('Ctrl+O')

	assert not ui.mnuFileOpenProfile.icon().isNull()
	assert not mainWindow.windowIcon().isNull()


def test_combo_boxes_and_plots_populated(mainWindow):
	ui = mainWindow.ui
	assert ui.cboSampleStatTests.currentText() == "G-test (w/ Yates') + Fisher's"
	assert ui.cboSampleConfIntervMethods.currentText() == 'DP: Asymptotic-CC'
	assert ui.cboSampleMultCompMethod.currentText() == 'No correction'
	assert comboItems(ui.cboSampleMultCompMethod) == ['Benjamini-Hochberg FDR', 'Bonferroni', 'No correction', 'Sidak', 'Storey FDR']
	assert ui.cboGroupStatTests.currentText() == "Welch's t-test"
	assert comboItems(ui.cboGroupStatTests) == ['t-test (equal variance)', "Welch's t-test", "White's non-parametric t-test"]
	assert ui.cboMultiGroupStatTests.currentText() == 'ANOVA'
	assert ui.cboPostHocTest.currentText() == 'Tukey-Kramer'
	assert comboItems(ui.cboPostHocTest) == ['Games-Howell', 'Scheff\xe8', 'Tukey-Kramer', "Welch's (uncorrected)"]
	assert ui.cboMultiGroupEffectSizeMeasure.currentText() == 'Eta-squared'
	# exploratory plots, separator, statistical plots; default selected
	assert comboItems(ui.cboSamplePlots) == ['Scatter plot', '', 'Dummy statistical plot']
	assert ui.cboSamplePlots.currentText() == 'Scatter plot'
	assert ui.cboGroupPlots.currentText() == 'PCA plot'
	assert ui.plotSampleScrollArea.widget() is mainWindow.samplePlot.currentPlot


def test_load_data_run_statistics_filter_and_tables(mainWindow, monkeypatch, STAMP, messageBoxes, tmp_path):
	ui = mainWindow.ui
	loadData(mainWindow, monkeypatch, STAMP)
	assert messageBoxes.calls == []
	assert mainWindow.preferences['Last directory'] == EX

	tree = mainWindow.profileTree
	assert comboItems(ui.cboProfileLevel) == tree.hierarchyHeadings
	assert comboItems(ui.cboParentalLevel) == ['Entire sample'] + tree.hierarchyHeadings[0:-1]
	assert comboItems(ui.cboSample1) == sorted(tree.sampleNames)
	assert ui.cboSample1.currentIndex() == 0 and ui.cboSample2.currentIndex() == 1
	assert mainWindow.metadataDlg.ui.tableMetadata.rowCount() == len(tree.sampleNames)

	# statistics ran on all three views at the first profile level
	sampleResults = mainWindow.sampleStatsTest.results
	assert len(sampleResults.data) > 0
	groupResults = mainWindow.groupStatsTest.results
	assert len(groupResults.data) > 0
	assert len(mainWindow.multiGroupStatsTest.results.data) > 0
	assert ui.txtSampleNumActiveFeatures.text() == str(activeCountFromResults(sampleResults, ui.spinSampleSignLevelFilter.value()))

	# tabs switch the plot view
	for name in ('Two samples', 'Two groups', 'Multiple groups'):
		index = [ui.tabWidgetProperties.tabText(i) for i in range(ui.tabWidgetProperties.count())].index(name)
		ui.tabWidgetProperties.setCurrentIndex(index)
		assert ui.stackedWidgetViews.currentIndex() == index
		assert mainWindow.lblStatusBar.text().startswith('Parent categories: ')

	# profile level change reruns all tests at the new level
	deepest = tree.hierarchyHeadings[-1]
	activate(ui.cboProfileLevel, deepest)
	assert mainWindow.sampleProfile.getNumFeatures() == len(mainWindow.sampleStatsTest.results.data)
	assert len(mainWindow.groupStatsTest.results.data) == mainWindow.groupProfile.getNumFeatures()

	# group field change through the legend
	legend = mainWindow.groupLegendDlg
	cboField = legend.findChildren(QtWidgets.QComboBox)[0]
	assert cboField.currentText() == mainWindow.metadata.activeField
	cboField.setCurrentText('Nationality')
	assert mainWindow.metadata.activeField == 'Nationality'
	groups = sorted(mainWindow.profileTree.groupDict.keys())
	assert comboItems(ui.cboGroup1) == [g for g in groups if mainWindow.profileTree.groupActive[g]]
	assert comboItems(ui.cboGroup2)[-1] == '<All other samples>'
	cboField.setCurrentText('Enterotype')
	activate(ui.cboGroup1, 'Enterotype 1')
	activate(ui.cboGroup2, 'Enterotype 2')
	groupProfile = mainWindow.groupProfile
	assert (groupProfile.groupName1, groupProfile.groupName2) == ('Enterotype 1', 'Enterotype 2')

	# p-value filter (enabled by default): tighten it and check the active features and tables
	groupResults = mainWindow.groupStatsTest.results
	ui.spinGroupSignLevelFilter.setValue(0.05)
	ui.spinGroupSignLevelFilter.editingFinished.emit()
	expected = activeCountFromResults(groupResults, 0.05)
	assert 0 < expected < len(groupResults.data)
	assert ui.txtGroupNumActiveFeatures.text() == str(expected)
	ui.chkShowActiveFeaturesGroupTable.setChecked(True)
	ui.chkShowActiveFeaturesGroupTable.clicked.emit(True)
	assert mainWindow.groupFeatureTable.rowCount(None) == expected

	ui.chkGroupEnableSignLevelFilter.setChecked(False)
	assert ui.txtGroupNumActiveFeatures.text() == str(len(groupResults.data))
	ui.chkGroupEnableSignLevelFilter.setChecked(True)

	# statistics table dock
	table = mainWindow.groupTable
	assert table.table.rowCount(None) == len(groupResults.data)
	tableData, headings = groupResults.tableData(False)
	assert [table.table.headerData(c, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.DisplayRole) for c in range(len(headings))] == headings
	table.ui.chkShowActiveFeatures.setChecked(True)
	table.ui.chkShowActiveFeatures.clicked.emit(True)
	assert table.table.rowCount(None) == expected

	# save the statistics table
	outFile = str(tmp_path / 'groupStats.tsv')
	monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: (outFile, 'Tab-separated values (*.tsv)')))
	table.ui.btnSave.click()
	lines = open(outFile).read().splitlines()
	assert lines[0].split('\t')[0:len(headings)] == headings
	assert len(lines) == 1 + expected
	assert mainWindow.preferences['Last directory'] == str(tmp_path)

	# sample selection change
	sample2 = comboItems(ui.cboSample2)[3]
	activate(ui.cboSample2, sample2)
	assert mainWindow.sampleProfile.sampleNames[1] == sample2

	# selecting a feature in the side table feeds the plot
	ui.tableGroupFeatures.selectRow(0)
	assert mainWindow.preferences['Selected group feature'] == mainWindow.groupFeatureTable.arraydata[0][0]

	# multiple groups: post-hoc test runs for the selected feature (the dummy plot asks for it)
	ui.tableMultiGroupFeatures.selectRow(0)
	feature = mainWindow.preferences['Selected multiple group feature']
	assert feature != ''
	assert mainWindow.multiGroupStatsTest.results.postHocResults.feature == feature

	# multiple comparison correction changes the filter label
	activate(ui.cboGroupMultCompMethod, 'Benjamini-Hochberg FDR')
	assert ui.lblGroupSignLevelFilter.text() == 'q-value filter (>):'

	assert messageBoxes.calls == []


def test_load_second_profile(mainWindow, monkeypatch, STAMP, messageBoxes):
	'''Upstream raised KeyError '' in MetadataTableDlg.setValues when a second profile was loaded.'''
	loadData(mainWindow, monkeypatch, STAMP)
	loadData(mainWindow, monkeypatch, STAMP)
	assert messageBoxes.calls == []
	assert mainWindow.metadataDlg.ui.cboMetadataField.currentIndex() == 0
	assert mainWindow.metadataDlg.ui.cboMetadataValue.count() > 0
	assert len(mainWindow.groupStatsTest.results.data) > 0


def test_save_plot_and_send_to_window(mainWindow, monkeypatch, STAMP, messageBoxes, tmp_path):
	loadData(mainWindow, monkeypatch, STAMP)
	ui = mainWindow.ui
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoGroups))

	outFile = str(tmp_path / 'plot.png')
	monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: (outFile, '')))
	monkeypatch.setattr(QtWidgets.QInputDialog, 'getInt', staticmethod(lambda *a, **k: (72, True)))
	ui.mnuFileSavePlot.trigger()
	assert os.path.getsize(outFile) > 0

	before = len(mainWindow.findChildren(STAMP.PlotDlg))
	ui.mnuViewSendPlotToWindow.trigger()
	plotDlgs = mainWindow.findChildren(STAMP.PlotDlg)
	assert len(plotDlgs) == before + 1
	newPlot = plotDlgs[-1].plot
	assert ('mirrorProperties', mainWindow.groupPlot.currentPlot) in newPlot.calls
	assert messageBoxes.calls == []


def test_group_legend_toggle(mainWindow, monkeypatch, STAMP, messageBoxes):
	loadData(mainWindow, monkeypatch, STAMP)
	legend = mainWindow.groupLegendDlg
	checkBoxes = {c.objectName(): c for c in legend.findChildren(QtWidgets.QCheckBox)}
	assert sorted(checkBoxes) == sorted(mainWindow.profileTree.groupDict)

	checkBoxes['Enterotype 3'].setChecked(False)
	assert mainWindow.profileTree.groupActive['Enterotype 3'] is False
	assert 'Enterotype 3' not in comboItems(mainWindow.ui.cboGroup1)
	assert 'Enterotype 3' not in mainWindow.multiGroupProfile.activeGroupNames

	checkBoxes['Enterotype 3'].setChecked(True)
	assert 'Enterotype 3' in comboItems(mainWindow.ui.cboGroup1)
	assert messageBoxes.calls == []


def test_metadata_table_active_samples(mainWindow, monkeypatch, STAMP, messageBoxes):
	loadData(mainWindow, monkeypatch, STAMP)
	dlg = mainWindow.metadataDlg
	activate(dlg.ui.cboMetadataField, 'Nationality')
	dlg.ui.cboMetadataAddRemove.setCurrentText('Remove')
	dlg.ui.cboMetadataRelationship.setCurrentText('=')
	dlg.ui.cboMetadataValue.setCurrentText('american')
	dlg.ui.tbMetadataFilter.click()
	american = [s for s in mainWindow.metadata.getSampleNames() if mainWindow.metadata.getValue(s, 'Nationality') == 'american']
	assert american
	assert not set(american) & set(mainWindow.metadata.activeSamples)
	assert not set(american) & set(comboItems(mainWindow.ui.cboSample1))

	dlg.ui.tbMetadataAddAll.click()
	assert sorted(mainWindow.metadata.activeSamples) == sorted(mainWindow.metadata.getSampleNames())
	assert messageBoxes.calls == []


def test_preferences_dialog_updates_preferences_and_settings(mainWindow, monkeypatch, STAMP, isolatedSettings):
	def fakeExec(dlg):
		dlg.ui.spinPseudoCount.setValue(0.25)
		dlg.ui.spinReplicates.setValue(2000)
		dlg.ui.chkTruncateFeatureNames.setChecked(False)
		dlg.ui.spinFeatureNameLength.setValue(30)
		dlg.setMinimumReportedPValue(-10)
		dlg.setAxesButtonColour(QtGui.QColor('#102030'))
		dlg.setAllOtherSamplesButtonColour(QtGui.QColor('#405060'))
		return QtWidgets.QDialog.DialogCode.Accepted

	monkeypatch.setattr(STAMP.PreferencesDlg, 'exec', fakeExec)
	mainWindow.ui.mnuSettingsPreferences.trigger()
	prefs = mainWindow.preferences
	assert (prefs['Pseudocount'], prefs['Replicates'], prefs['Truncate feature names'], prefs['Length of truncated feature names'], prefs['Minimum reported p-value exponent']) == (0.25, 2000, False, 30, -10)
	assert prefs['Axes colour'].name() == '#102030'
	assert prefs['All other samples colour'].name() == '#405060'

	# closing stores the preferences; main() reads them back with the same values and types
	mainWindow.close()
	settings = QtCore.QSettings('BeikoLab', 'STAMP')
	assert settings.value('Preferences/Pseudocount', 0.5, type=float) == 0.25
	assert settings.value('Preferences/Replicates', 1000, type=int) == 2000
	assert settings.value('Preferences/Truncate feature names', True, type=bool) is False
	assert settings.value('Preferences/Length of truncated feature names', 50, type=int) == 30
	assert settings.value('Preferences/Minimum reported p-value exponent', -15, type=float) == -10
	assert settings.value('Preferences/Axes colour', '#7f7f7f', type=str) == '#102030'
	assert not settings.value('MainWindow/Geometry', QtCore.QByteArray(), type=QtCore.QByteArray).isEmpty()


def test_about_dialog_matches_upstream(mainWindow, messageBoxes):
	mainWindow.ui.mnuHelpAbout.trigger()
	assert len(messageBoxes.calls) == 1
	kind, args = messageBoxes.calls[0]
	assert kind == 'about'
	assert args[1] == 'About...'
	assert args[2] == ('STAMP: statistical analysis of taxonomic and functional profiles\n\n'
						'Donovan Parks and Robert Beiko\n2.1.3\nJune 26, 2015\n\n'
						'Program icon by Caihua (http://commons.wikimedia.org/wiki/File:Fairytale_colors.png)')


def test_mult_comp_info_without_test(mainWindow, messageBoxes):
	mainWindow.ui.btnGroupMultCompCorrectionInfo.click()
	assert messageBoxes.calls[0][0] == 'information'
	assert messageBoxes.calls[0][1][1:3] == ('Run test', 'Run hypothesis test first.')


def test_except_hook_reports_error(STAMP, messageBoxes):
	try:
		{}['missing']
	except KeyError:
		STAMP.exceptHook(*sys.exc_info())
	kind, args = messageBoxes.calls[0]
	assert kind == 'critical'
	assert args[1] == 'Unknown error...'
	assert "KeyError: 'missing'" in args[2] and 'test_gui_mainwindow.py' in args[2]


class _FakeApp:
	styles = []
	instance = staticmethod(QtWidgets.QApplication.instance)	# pytest-qt keeps using the real application

	def __init__(self, argv):
		pass

	@staticmethod
	def setStyle(style):
		_FakeApp.styles.append(style)

	def exec(self):
		return 0


@pytest.mark.parametrize('frozen', [False, True])
def test_main_preferences_style_and_working_directory(STAMP, monkeypatch, isolatedSettings, qapp, tmp_path, frozen):
	settings = QtCore.QSettings('BeikoLab', 'STAMP')
	settings.setValue('Preferences/Pseudocount', 0.75)
	settings.setValue('Preferences/Replicates', 500)
	settings.setValue('Preferences/Truncate feature names', False)
	settings.setValue('Preferences/All other samples colour', '#123456')
	settings.sync()

	created = {}

	class FakeMainWindow:
		def __init__(self, preferences):
			created['preferences'] = preferences

		def show(self):
			created['shown'] = True

	chdirs = []
	_FakeApp.styles = []
	monkeypatch.setattr(QtWidgets, 'QApplication', _FakeApp)
	monkeypatch.setattr(STAMP, 'MainWindow', FakeMainWindow)
	monkeypatch.setattr(os, 'chdir', chdirs.append)
	monkeypatch.setattr(sys, 'path', list(sys.path))
	monkeypatch.setattr(sys, 'argv', ['STAMP'])
	monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
	if frozen:
		appDir = str(tmp_path / 'Applications')
		monkeypatch.setattr(sys, 'frozen', True, raising=False)
		monkeypatch.setattr(sys, '_MEIPASS', appDir + '/STAMP.app/Contents/Frameworks', raising=False)
		monkeypatch.setattr(sys, 'executable', appDir + '/STAMP.app/Contents/MacOS/STAMP')

	with pytest.raises(SystemExit):
		STAMP.main()

	prefs = created['preferences']
	assert created['shown']
	assert (prefs['Pseudocount'], prefs['Replicates'], prefs['Truncate feature names']) == (0.75, 500, False)
	assert isinstance(prefs['Replicates'], int) and isinstance(prefs['Pseudocount'], float)
	assert prefs['Length of truncated feature names'] == 50
	assert prefs['Minimum reported p-value exponent'] == -15
	assert prefs['All other samples colour'].name() == '#123456'
	assert prefs['Axes colour'].name() == '#7f7f7f'
	assert _FakeApp.styles == ['Windows']
	assert sys.excepthook is STAMP.exceptHook
	if frozen:
		assert sys.path[0] == appDir + '/STAMP.app/Contents/Frameworks'
		assert prefs['Last directory'] == appDir
		assert chdirs[-1] == appDir
	else:
		assert sys.path[0] == os.path.join(ROOT, 'stamp')
		assert prefs['Last directory'] == ''
		assert chdirs == [os.path.join(ROOT, 'stamp')]
