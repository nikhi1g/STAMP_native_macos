'''Headless tests of STAMP's dialogs (QT_QPA_PLATFORM=offscreen, see conftest.py): each dialog is
constructed and its main interaction driven, with file and colour pickers replaced by fixed answers.'''

import gzip
import os
import shutil
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, 'stamp', 'examples')
ENTEROTYPES = os.path.join(EXAMPLES, 'EnterotypesArumugam')
BIOM = os.path.join(EXAMPLES, 'BIOM-test')

Accepted = QtWidgets.QDialog.DialogCode.Accepted
Rejected = QtWidgets.QDialog.DialogCode.Rejected


def preferences(lastDirectory=''):
	return {'Pseudocount': 0.5, 'Replicates': 1000, 'Last directory': lastDirectory, 'Group colours': {},
			'Truncate feature names': True, 'Length of truncated feature names': 50}


@pytest.fixture
def messageBoxes(monkeypatch):
	calls = []

	def record(kind):
		def f(*args, **kwargs):
			calls.append((kind, args))
			return QtWidgets.QMessageBox.StandardButton.Ok
		return staticmethod(f)

	for kind in ('information', 'warning', 'critical', 'about'):
		monkeypatch.setattr(QtWidgets.QMessageBox, kind, record(kind))
	return calls


def answerOpen(monkeypatch, path):
	monkeypatch.setattr(QtWidgets.QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: (path, '')))


def answerOpenMany(monkeypatch, paths):
	monkeypatch.setattr(QtWidgets.QFileDialog, 'getOpenFileNames', staticmethod(lambda *a, **k: (list(paths), '')))


def answerSave(monkeypatch, path):
	monkeypatch.setattr(QtWidgets.QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: (path, '')))


def answerColour(monkeypatch, colour):
	monkeypatch.setattr(QtWidgets.QColorDialog, 'getColor', staticmethod(lambda *a, **k: QtGui.QColor(colour)))


@pytest.fixture(scope='module')
def enterotypes():
	from stamp.metagenomics.fileIO.StampIO import StampIO
	from stamp.metagenomics.fileIO.MetadataIO import MetadataIO
	prefs = preferences()
	tree, err = StampIO(prefs).read(os.path.join(ENTEROTYPES, 'Enterotypes.profile.spf'))
	assert err is None
	metadata, warning = MetadataIO(prefs).read(os.path.join(ENTEROTYPES, 'Enterotypes.metadata.tsv'), tree)
	return tree, metadata


@pytest.fixture
def groupStatsTest(enterotypes):
	from stamp.metagenomics.stats.GroupStatsTests import GroupStatsTests
	from stamp.plugins.groups.statisticalTests.Welch import Welch
	from stamp.plugins.common.multipleComparisonCorrections.NoCorrection import NoCorrection
	tree, metadata = enterotypes
	prefs = preferences()
	metadata.setActiveField('Enterotype', tree)
	profile = tree.createGroupProfile('Enterotype 1', 'Enterotype 2', 'Entire sample', 'Genera', metadata, 'Retain unclassified reads')
	test = GroupStatsTests(prefs)
	test.run(Welch(prefs), 'Two-sided', "DP: Welch's inverted", 0.95, profile)
	test.results.performMultCompCorrection(NoCorrection(prefs))
	test.results.selectAllFeautres()
	test.results.filterFeatures(0.05, None, None, None, None, None, None, None, None, 'OR', None, None)
	return test


def test_resources_registered(qapp):
	import stamp.STAMP_rc  # noqa: F401
	assert not QtGui.QIcon(':/icons/icons/refresh.png').isNull()
	assert QtGui.QPixmap(':/icons/icons/programIcon.png').width() == 64


def test_load_data_dialog_returns_chosen_paths(qtbot, monkeypatch):
	from stamp.GUI.loadDataDlg import LoadDataDlg
	prefs = preferences()
	dlg = LoadDataDlg(prefs)
	qtbot.addWidget(dlg)
	assert dlg.windowTitle() == 'Load data'

	profile = os.path.join(ENTEROTYPES, 'Enterotypes.profile.spf')
	metadata = os.path.join(ENTEROTYPES, 'Enterotypes.metadata.tsv')
	answerOpen(monkeypatch, profile)
	dlg.ui.tbProfileFile.click()
	answerOpen(monkeypatch, metadata)
	dlg.ui.tbMetadataFile.click()
	assert dlg.getProfileFile() == profile
	assert dlg.getMetadataFile() == metadata
	assert prefs['Last directory'] == ENTEROTYPES

	# cancelling the file chooser keeps the previous choice
	answerOpen(monkeypatch, '')
	dlg.ui.tbProfileFile.click()
	assert dlg.getProfileFile() == profile

	QtCore.QTimer.singleShot(0, dlg.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click)
	assert dlg.exec() == Accepted


def test_preferences_dialog_round_trip(qtbot, monkeypatch):
	from stamp.GUI.preferencesDlg import PreferencesDlg
	dlg = PreferencesDlg()
	qtbot.addWidget(dlg)

	dlg.setMinimumReportedPValue(-15.0)	# main() reads the exponent as a float
	assert dlg.ui.spinMinPvalue.value() == 15
	assert dlg.getMinimumReportedPValue() == -15

	dlg.setAxesButtonColour(QtGui.QColor('#7f7f7f'))
	dlg.setAllOtherSamplesButtonColour(QtGui.QColor('#7f7f7f'))
	answerColour(monkeypatch, '#ff0000')
	dlg.ui.btnAxesColour.click()
	answerColour(monkeypatch, '#00ff00')
	dlg.ui.btnAllOtherSamplesColour.click()
	assert dlg.getAxesColour().name() == '#ff0000'
	assert dlg.getAllOtherSamplesColour().name() == '#00ff00'
	assert 'rgb(255,0,0)' in dlg.ui.btnAxesColour.styleSheet()

	dlg.ui.chkTruncateFeatureNames.setChecked(False)
	assert not dlg.ui.spinFeatureNameLength.isEnabled()
	dlg.ui.chkTruncateFeatureNames.setChecked(True)
	assert dlg.ui.spinFeatureNameLength.isEnabled()

	QtCore.QTimer.singleShot(0, dlg.ui.btnOK.click)
	assert dlg.exec() == Accepted


def test_stats_table_fills_from_results(qtbot, monkeypatch, groupStatsTest, tmp_path):
	from stamp.GUI.statsTableDlg import StatsTableDlg
	prefs = preferences()
	dlg = StatsTableDlg(prefs)
	qtbot.addWidget(dlg)
	dlg.updateTable(groupStatsTest)

	results = groupStatsTest.results
	model = dlg.ui.tableStatisticalSummary.model()
	assert model.rowCount(None) == len(results.data)
	assert model.columnCount(None) == len(results.tableHeadings)
	assert [model.headerData(c, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.DisplayRole) for c in range(model.columnCount(None))] == results.tableHeadings
	firstColumn = [model.data(model.index(r, 0), QtCore.Qt.ItemDataRole.DisplayRole) for r in range(model.rowCount(None))]
	assert firstColumn == sorted(firstColumn, key=str.lower)	# starts sorted alphabetically on the first column
	assert all(dlg.ui.tableStatisticalSummary.columnWidth(c) > 10 for c in range(model.columnCount(None)))

	dlg.ui.chkShowActiveFeatures.setChecked(True)
	dlg.ui.chkShowActiveFeatures.clicked.emit(True)
	assert dlg.ui.tableStatisticalSummary.model().rowCount(None) == len(results.getActiveFeatures())

	outFile = str(tmp_path / 'table.tsv')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnSave.click()
	lines = open(outFile).read().splitlines()
	assert lines[0] == '\t'.join(results.tableHeadings) + '\t'
	assert len(lines) == 1 + len(results.getActiveFeatures())
	assert prefs['Last directory'] == str(tmp_path)


def test_metadata_table_set_values_and_filter(qtbot, enterotypes):
	from stamp.GUI.metadataTableDlg import MetadataTableDlg
	tree, metadata = enterotypes
	dlg = MetadataTableDlg(preferences())
	qtbot.addWidget(dlg)
	dlg.setTable(metadata)

	table, headers = metadata.getTableData()
	assert [dlg.ui.cboMetadataField.itemText(i) for i in range(dlg.ui.cboMetadataField.count())] == headers[1:]
	assert dlg.ui.tableMetadata.rowCount() == len(table)
	assert dlg.ui.tableMetadata.item(0, 0).checkState() == QtCore.Qt.CheckState.Checked

	dlg.ui.cboMetadataField.setCurrentText('Nationality')
	values = [dlg.ui.cboMetadataValue.itemText(i) for i in range(dlg.ui.cboMetadataValue.count())]
	assert values == sorted(set(metadata.getValue(s, 'Nationality') for s in metadata.getSampleNames()), key=str.lower)

	# a second table (second profile load) must not raise KeyError '' (upstream bug)
	dlg.setTable(metadata)
	assert dlg.ui.cboMetadataField.currentText() == headers[1]
	assert dlg.ui.cboMetadataValue.count() == len(metadata.getUniqueValues(headers[1]))

	with qtbot.waitSignal(dlg.activeSamplesChanged):
		dlg.ui.tbMetadataRemoveAll.click()
	assert metadata.activeSamples == []
	with qtbot.waitSignal(dlg.activeSamplesChanged):
		dlg.ui.tbMetadataAddAll.click()
	assert sorted(metadata.activeSamples) == sorted(metadata.getSampleNames())

	dlg.ui.cboMetadataField.setCurrentText('Gender')
	dlg.ui.cboMetadataAddRemove.setCurrentText('Remove')
	dlg.ui.cboMetadataRelationship.setCurrentText('=')
	dlg.ui.cboMetadataValue.setCurrentText('F')
	with qtbot.waitSignal(dlg.activeSamplesChanged):
		dlg.ui.tbMetadataFilter.click()
	assert all(metadata.getValue(s, 'Gender') != 'F' for s in metadata.activeSamples)
	dlg.checkAll()


def test_metadata_table_numeric_values_sorted_numerically(qtbot):
	from stamp.GUI.metadataTableDlg import MetadataTableDlg
	metadata = types.SimpleNamespace(getUniqueValues=lambda field: ['10', '9', '100', '2.5'], isNumericalData=lambda field: True)
	dlg = MetadataTableDlg(preferences())
	qtbot.addWidget(dlg)
	dlg.metadata = metadata
	dlg.setFields(['pH'])
	assert [dlg.ui.cboMetadataValue.itemText(i) for i in range(dlg.ui.cboMetadataValue.count())] == ['2.5', '9', '10', '100']


def test_group_legend_toggles_and_colours(qtbot, monkeypatch, enterotypes, messageBoxes):
	from stamp.GUI.groupLegendDlg import GroupLegendDlg
	tree, metadata = enterotypes
	metadata.activeSamples = list(metadata.getSampleNames())
	prefs = preferences()
	dlg = GroupLegendDlg(prefs)
	qtbot.addWidget(dlg)
	dlg.initLegend(tree, metadata, 'Enterotype')
	assert sorted(dlg.groupColourDict) == sorted(tree.groupDict)
	assert dlg.groupColourDict['Enterotype 1'] == dlg.groupColours[sorted(tree.groupDict).index('Enterotype 1')]

	checkBoxes = {c.objectName(): c for c in dlg.findChildren(QtWidgets.QCheckBox)}
	with qtbot.waitSignal(dlg.legendActiveGroupsChanged):
		checkBoxes['Enterotype 2'].setChecked(False)
	assert tree.groupActive['Enterotype 2'] is False
	with qtbot.waitSignal(dlg.legendActiveGroupsChanged):
		checkBoxes['Enterotype 2'].setChecked(True)
	assert tree.groupActive['Enterotype 2'] is True

	buttons = {b.objectName(): b for b in dlg.findChildren(QtWidgets.QToolButton)}
	answerColour(monkeypatch, '#010203')
	with qtbot.waitSignal(dlg.legendItemChanged):
		buttons['Enterotype 1'].click()
	assert dlg.groupColourDict['Enterotype 1'].name() == '#010203'
	assert prefs['Group colours'] is dlg.groupColourDict

	cboField = dlg.findChildren(QtWidgets.QComboBox)[0]
	with qtbot.waitSignal(dlg.legendFieldChanged):
		cboField.setCurrentText('Gender')
	assert metadata.activeField == 'Gender'
	assert sorted(dlg.groupColourDict) == sorted(tree.groupDict)

	# a group without active samples cannot be activated
	metadata.activeSamples = [s for s in metadata.getSampleNames() if metadata.getValue(s, 'Gender') != 'F']
	dlg.initLegend(tree, metadata, 'Gender')
	checkBoxF = [c for c in dlg.findChildren(QtWidgets.QCheckBox) if c.objectName() == 'F'][-1]
	assert not checkBoxF.isChecked()
	checkBoxF.setChecked(True)
	assert not checkBoxF.isChecked()
	assert messageBoxes[-1][1][1:3] == ('Empty group', 'Groups with no active samples cannot be made active.')
	metadata.activeSamples = list(metadata.getSampleNames())
	metadata.setActiveField('Enterotype', tree)


def test_select_features_dialog(qtbot, groupStatsTest):
	from stamp.GUI.selectFeaturesDlg import SelectFeaturesDlg
	results = groupStatsTest.results
	dlg = SelectFeaturesDlg(results)
	qtbot.addWidget(dlg)
	allFeatures = results.getColumn('Features', False)
	assert dlg.ui.lstSelectedFeatures.count() == len(allFeatures)
	assert dlg.ui.lstFilteredFeatures.count() == 0
	assert dlg.ui.cboHierarchicalLevel.currentText() == 'Genera'

	dlg.ui.lstSelectedFeatures.item(0).setSelected(True)
	removed = dlg.ui.lstSelectedFeatures.item(0).text()
	dlg.ui.btnFilterFeature.click()
	assert removed not in dlg.getSelectedFeatures()
	assert len(dlg.getSelectedFeatures()) == len(allFeatures) - 1
	assert dlg.ui.txtNumSelectedFeatures.text() == str(len(allFeatures) - 1)

	# group by the parent level: '<phylum> [n]' entries
	dlg.ui.cboHierarchicalLevel.setCurrentIndex(0)
	dlg.ui.cboHierarchicalLevel.activated.emit(0)
	assert all(' [' in dlg.ui.lstSelectedFeatures.item(i).text() for i in range(dlg.ui.lstSelectedFeatures.count()))

	dlg.ui.cboHierarchicalLevel.setCurrentIndex(1)
	dlg.ui.cboHierarchicalLevel.activated.emit(1)
	dlg.ui.lstFilteredFeatures.item(0).setSelected(True)
	dlg.ui.btnAddFeature.click()
	assert sorted(dlg.getSelectedFeatures()) == sorted(allFeatures)

	QtCore.QTimer.singleShot(0, dlg.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click)
	assert dlg.exec() == Accepted


def test_customize_headings_dialog(qtbot):
	from stamp.GUI.customizeHeadingsDlg import CustomizeHeadingsDlg
	dlg = CustomizeHeadingsDlg()
	qtbot.addWidget(dlg)
	dlg.ui.txtLevel1.setText('Kingdom')
	QtCore.QTimer.singleShot(0, dlg.ui.btnOK.click)
	assert dlg.exec() == Accepted
	assert dlg.ui.txtLevel1.text() == 'Kingdom'
	QtCore.QTimer.singleShot(0, dlg.ui.btnCancel.click)
	assert dlg.exec() == Rejected


@pytest.mark.parametrize('info', [[('Number of significant features', 3), ('FDR', 0.05)], []])
def test_mult_comp_correction_info_dialog(qtbot, info):
	from stamp.GUI.multCompCorrectionInfoDlg import MultCompCorrectionInfoDlg
	dlg = MultCompCorrectionInfoDlg(None, info)
	qtbot.addWidget(dlg)
	labels = [w.text() for w in dlg.findChildren(QtWidgets.QLabel)]
	if info:
		assert 'Number of significant features:' in labels and 'FDR:' in labels
		assert [w.text() for w in dlg.findChildren(QtWidgets.QLineEdit)] == ['3', '0.05']
	else:
		assert 'No additional information.' in labels
	QtCore.QTimer.singleShot(0, dlg.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click)
	assert dlg.exec() == Accepted


def test_plot_dialog_sizes_to_plot(qtbot):
	from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
	from matplotlib.figure import Figure
	from stamp.GUI.plotDlg import PlotDlg
	window = QtWidgets.QMainWindow()
	qtbot.addWidget(window)
	dlg = PlotDlg(window)
	window.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dlg)
	canvas = FigureCanvasQTAgg(Figure(figsize=(4, 3), dpi=50))
	dlg.addPlot(canvas)
	assert dlg.ui.scrollArea.widget() is canvas
	# PlotDlg's slots shadow the QDockWidget signals of the same name; emit the real signals (as Qt does
	# when the user floats or docks the window) to check they reach the slots
	QtWidgets.QDockWidget.topLevelChanged.__get__(dlg).emit(True)
	w, h = canvas.get_width_height()
	assert dlg.maximumSize() == QtCore.QSize(w, h)
	QtWidgets.QDockWidget.dockLocationChanged.__get__(dlg).emit(QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
	assert dlg.maximumSize() == QtCore.QSize(10000, 10000)


def test_create_profile_mgrast_matches_example(qtbot, monkeypatch, tmp_path, messageBoxes):
	from stamp.GUI.createProfileMgRastDlg import CreateProfileMgRastDlg
	from stamp.GUI.customizeHeadingsDlg import CustomizeHeadingsDlg
	example = os.path.join(EXAMPLES, 'CowRumen-MG-RAST')
	prefs = preferences()
	dlg = CreateProfileMgRastDlg(prefs)
	qtbot.addWidget(dlg)
	answerOpen(monkeypatch, os.path.join(example, 'CowRumen-MG-RAST.tsv'))
	dlg.ui.btnLoadProfiles.click()
	assert dlg.ui.btnCreateProfile.isEnabled() and dlg.ui.btnCustomizeHeadings.isEnabled()
	assert prefs['Last directory'] == example

	# the customize-headings dialog shows and returns the headings
	def fakeExec(headingsDlg):
		assert headingsDlg.ui.txtInfo.toPlainText() == 'This MG-RAST profiles consists of 4 hierarchical levels.'
		assert headingsDlg.ui.txtLevel4.text() == 'function'
		return Accepted
	monkeypatch.setattr(CustomizeHeadingsDlg, 'exec', fakeExec)
	dlg.ui.btnCustomizeHeadings.click()
	assert dlg.headings[0:4] == ['level 1', 'level 2', 'level 3', 'function']

	outFile = str(tmp_path / 'CowRumen.spf')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnCreateProfile.click()
	produced = open(outFile).read().splitlines()
	expected = open(os.path.join(example, 'CowRumen.spf')).read().splitlines()
	assert produced[0] == expected[0]
	assert sorted(produced[1:]) == sorted(expected[1:])	# rows follow dict order
	assert messageBoxes == []


def test_create_profile_comet(qtbot, monkeypatch, tmp_path, messageBoxes):
	from stamp.GUI.createProfileCoMetDlg import CreateProfileCoMetDlg
	# upstream takes the sample name between the last '/' and the first '.' of the whole path, so the
	# inputs are copied to a folder without dots in its path (this checkout lives under .worktrees/)
	folder = os.path.join(EXAMPLES, 'NineBiomes-GO-Profiles-CoMet')
	files = [shutil.copy(os.path.join(folder, f), tmp_path) for f in ('profileGO_Coral.fa.txt', 'profileGO_Fish.fa.txt')]
	assert '.' not in str(tmp_path)
	dlg = CreateProfileCoMetDlg(preferences())
	qtbot.addWidget(dlg)
	answerOpenMany(monkeypatch, files)
	dlg.ui.btnLoadProfiles.click()
	assert dlg.ui.lstSelectedProfiles.count() == 2

	outFile = str(tmp_path / 'comet.spf')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnCreateProfile.click()
	lines = open(outFile).read().splitlines()
	assert lines[0] == 'Category\tCoral\tFish'
	rows = {line.split('\t')[0]: line.split('\t')[1:] for line in lines[1:]}
	assert rows['molecular_function'][0] == '40652.0'
	assert messageBoxes == []


def test_create_profile_rita(qtbot, monkeypatch, tmp_path, messageBoxes):
	from stamp.GUI.createProfileRITADlg import CreateProfileRITADlg
	sample = tmp_path / 'RITA_SampleA.txt'
	sample.write_text('read\tscore\tgroup\trank\ttaxonomy\n'
					'r1\t1\tNB and D-BLASTN\tGENUS\tBacteroides\tBacteroidaceae\tBacteroidales\tBacteroidia\tBacteroidetes\tBacteria\n'
					'r2\t1\tNB and D-BLASTN\tGENUS\tBacteroides\tBacteroidaceae\tBacteroidales\tBacteroidia\tBacteroidetes\tBacteria\n'
					'r3\t1\tBLASTX ratio\tPHYLUM\tFirmicutes\tBacteria\n')
	dlg = CreateProfileRITADlg(preferences())
	qtbot.addWidget(dlg)
	answerOpenMany(monkeypatch, [str(sample)])
	dlg.ui.btnLoadProfiles.click()
	outFile = str(tmp_path / 'rita.spf')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnCreateProfile.click()
	lines = open(outFile).read().splitlines()
	assert lines[0] == 'Domain\tPhylum\tClass\tOrder\tFamily\tGenus\tSampleA'
	rows = sorted(lines[1:])
	assert 'Bacteria\tBacteroidetes\tBacteroidia\tBacteroidales\tBacteroidaceae\tBacteroides\t2' in rows
	assert messageBoxes == []


def test_create_profile_mothur(qtbot, monkeypatch, tmp_path, messageBoxes):
	from stamp.GUI.createProfileMothurDlg import CreateProfileMothurDlg
	taxonomy = tmp_path / 'seqs.taxonomy'
	taxonomy.write_text('s1\tBacteria(100);Firmicutes(99);Clostridia(90);\n'
						's3\tBacteria(100);Bacteroidetes(98);\n')
	groups = tmp_path / 'seqs.groups'
	groups.write_text('s1\tA\ns2\tB\ns3\tB\ns4\tA\n')
	names = tmp_path / 'seqs.names'
	names.write_text('s1\ts1,s2\ns3\ts3,s4\n')
	prefs = preferences()
	dlg = CreateProfileMothurDlg(prefs)
	qtbot.addWidget(dlg)

	dlg.ui.btnCreateProfile.click()
	assert messageBoxes[-1][1][1:3] == ('Missing data', 'A Group file must be specified.')

	for button, path in ((dlg.ui.btnTaxonomyFile, taxonomy), (dlg.ui.btnGroupsFile, groups), (dlg.ui.btnNamesFile, names)):
		answerOpen(monkeypatch, str(path))
		button.click()
	assert dlg.ui.txtTaxonomyFile.text() == str(taxonomy)
	outFile = str(tmp_path / 'mothur.spf')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnCreateProfile.click()
	lines = open(outFile).read().splitlines()
	assert lines[0] == 'Level 1\tLevel 2\tLevel 3\tA\tB'
	assert sorted(lines[1:]) == ['Bacteria\tBacteroidetes\tunclassified\t1\t1', 'Bacteria\tFirmicutes\tClostridia\t1\t1']


def readProfile(path):
	lines = open(path).read().splitlines()
	return lines[0], sorted(lines[1:])


@pytest.mark.parametrize('biomFile, groundTruth', [
	('predicted_metagenomes.L3.biom', 'predicted_metagenomes.L3.ground_truth.spf'),
	('predicted_metagenomes.biom', 'predicted_metagenomes_gt.spf'),
])
def test_create_profile_biom_matches_ground_truth(qtbot, monkeypatch, tmp_path, messageBoxes, biomFile, groundTruth):
	from stamp.GUI.createProfileBiomDlg import CreateProfileBiomDlg
	prefs = preferences()
	dlg = CreateProfileBiomDlg(prefs)
	qtbot.addWidget(dlg)
	answerOpen(monkeypatch, os.path.join(BIOM, biomFile))
	dlg.ui.btnBiomFile.click()
	assert prefs['Last directory'] == BIOM
	assert dlg.ui.cboMetadataField.currentText() == '<observation ids>'

	outFile = str(tmp_path / 'out.spf')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnCreateProfile.click()
	assert readProfile(outFile) == readProfile(os.path.join(BIOM, groundTruth))
	assert messageBoxes == []


def test_create_profile_biom_metadata_levels_and_gzip(qtbot, monkeypatch, tmp_path, messageBoxes):
	from stamp.GUI.createProfileBiomDlg import CreateProfileBiomDlg
	gzFile = str(tmp_path / 'kegg.biom.gz')
	with open(os.path.join(BIOM, 'kegg_predictions_L3.biom'), 'rb') as fin, gzip.open(gzFile, 'wb') as fout:
		shutil.copyfileobj(fin, fout)

	dlg = CreateProfileBiomDlg(preferences())
	qtbot.addWidget(dlg)
	outFile = str(tmp_path / 'kegg.spf')
	dlg.convertBiomFileToStampProfile(gzFile, outFile, 'KEGG_Pathways (PICRUSt KEGG analysis)')
	lines = open(outFile).read().splitlines()
	header = lines[0].split('\t')
	assert header[0:4] == ['Level_1', 'Level_2', 'Level_3', 'Observation Ids']
	assert len(header) == 4 + 29
	assert len(lines) == 1 + 328
	first = lines[1].split('\t')
	assert first[0:3] == ['Metabolism', 'Xenobiotics Biodegradation and Metabolism', '1,1,1-Trichloro-2,2-bis(4-chlorophenyl)ethane (DDT) degradation']
	assert first[3] == first[2]
	assert messageBoxes == []

	dlg.convertBiomFileToStampProfile(gzFile, str(tmp_path / 'none.spf'), 'taxonomy (QIIME OTU table)')
	assert messageBoxes[-1][1][1:3] == ('Unrecognized metadata file', "'taxonomy' was not found in the BIOM table.")


def _cogIOPorted():
	import inspect
	from stamp.metagenomics.fileIO import COG_IO
	return "'U'" not in inspect.getsource(COG_IO)


def test_assign_cogs_dialog(qtbot, monkeypatch, tmp_path, messageBoxes):
	from stamp.GUI.assignCOGsDlg import AssignCOGsDlg
	import stamp.metagenomics.fileIO.COG_IO as COG_IO
	prefs = preferences()
	dlg = AssignCOGsDlg(prefs)
	qtbot.addWidget(dlg)
	assert not dlg.ui.btnCreateProfile.isEnabled()
	inputFile = os.path.join(EXAMPLES, 'Assign_COGs_Example.tsv')
	answerOpen(monkeypatch, inputFile)
	dlg.ui.btnLoadProfiles.click()
	assert dlg.ui.txtInputProfile.text() == inputFile
	assert dlg.ui.btnCreateProfile.isEnabled()
	assert prefs['Last directory'] == EXAMPLES

	if not _cogIOPorted():
		pytest.skip("COG_IO still opens files with the removed 'U' mode on this base (fixed on port/core)")
	monkeypatch.setattr(COG_IO, 'getMainDir', lambda: os.path.join(ROOT, 'stamp'))
	outFile = str(tmp_path / 'cogs.spf')
	answerSave(monkeypatch, outFile)
	dlg.ui.btnCreateProfile.click()
	lines = open(outFile).read().splitlines()
	assert len(lines) > 1
	assert messageBoxes == []


def test_plot_event_handlers_show_nearest_tooltip(qapp, monkeypatch):
	from stamp.plugins.PlotEventHandler import PlotEventHandler, MultiPlotEventHandler
	shown = []
	# (Qt on macOS ignores QMessageBox window titles and icons, so only the text is checked)
	monkeypatch.setattr(QtWidgets.QMessageBox, 'exec', lambda box: shown.append(box.text()) or 0)

	handler = PlotEventHandler([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], ['a', 'b', 'c'])
	handler(types.SimpleNamespace(xdata=1.01, ydata=0.99))
	handler(types.SimpleNamespace(xdata=0.5, ydata=0.5))	# nothing within tolerance
	handler(types.SimpleNamespace(xdata=None, ydata=None))
	assert shown == ['b']

	axes = ['ax1', 'ax2']
	multi = MultiPlotEventHandler([[0.0, 1.0], [0.0, 10.0]], [[0.0, 1.0], [0.0, 10.0]], axes, ['x', 'y'])
	multi(types.SimpleNamespace(xdata=10.0, ydata=10.0, inaxes='ax2'))
	assert shown == ['b', 'y']
