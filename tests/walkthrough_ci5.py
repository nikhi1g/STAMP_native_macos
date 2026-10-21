# Lab-manual CI-5 walkthrough driven through the real application entry point
# (stamp.STAMP.main) on the native macOS platform, with a screenshot of the main
# window after each step and the 300 DPI export, as evidence.
#
#   uv run python tests/walkthrough_ci5.py <output dir> [profile] [metadata]
#
# Defaults to the Skirball demo (tests/data/skirball). QSettings are redirected to
# an ini file in the output dir, so the user's preferences are untouched. The Load
# Data dialog is replaced by a stub returning the two paths; everything else is the
# real code path the user clicks through.
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'stamp'))

OUT = os.path.abspath(sys.argv[1])
PROFILE = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'data', 'skirball', 'skirball_phylum.spf')
METADATA = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, 'data', 'skirball', 'skirball_metadata.tsv')
os.makedirs(OUT, exist_ok=True)

from PyQt6 import QtCore, QtWidgets

_RealQSettings = QtCore.QSettings


class IsolatedSettings(_RealQSettings):
	def __init__(self, *args):
		if len(args) == 2 and all(isinstance(a, str) for a in args):
			_RealQSettings.__init__(self, os.path.join(OUT, 'STAMP.ini'), _RealQSettings.Format.IniFormat)
		else:
			_RealQSettings.__init__(self, *args)


QtCore.QSettings = IsolatedSettings

import stamp.STAMP as STAMP


class FakeLoadDataDlg:
	def __init__(self, *a, **k):
		pass

	def exec(self):
		return QtWidgets.QDialog.DialogCode.Accepted

	def getProfileFile(self):
		return PROFILE

	def getMetadataFile(self):
		return METADATA


STAMP.LoadDataDlg = FakeLoadDataDlg
log = []


def window():
	return [w for w in QtWidgets.QApplication.instance().topLevelWidgets() if isinstance(w, STAMP.MainWindow)][0]


def shot(name):
	w = window()
	QtWidgets.QApplication.processEvents()
	path = os.path.join(OUT, name + '.png')
	w.grab().save(path)
	log.append('%s: %s' % (name, path))


def activate(combo, text):
	index = combo.findText(text)
	assert index != -1, (text, [combo.itemText(i) for i in range(combo.count())])
	combo.setCurrentIndex(index)
	combo.activated.emit(index)


def steps():
	w = window()
	ui = w.ui
	w.resize(1400, 900)
	yield 'step1_opened'
	# 2-3: File > Load data (Ctrl+O), profile + metadata
	ui.mnuFileOpenProfile.trigger()
	log.append('loaded %s + %s' % (PROFILE, METADATA))
	yield 'step3_loaded'
	# two samples: first two samples, extended error bar
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoSamples))
	activate(ui.cboSamplePlots, 'Extended error bar')
	r = w.sampleStatsTest.results
	log.append('two samples %s vs %s: %s, %d features, %d active' % (ui.cboSample1.currentText(), ui.cboSample2.currentText(), r.test, len(r.data), len(r.getActiveFeatures())))
	yield 'step4_two_samples_extended_error_bar'
	# two groups by Burn status, extended error bar, p-value filter 0.05
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabTwoGroups))
	legend = w.groupLegendDlg
	field = legend.findChildren(QtWidgets.QComboBox)[0]
	if field.findText('Burn status') != -1:
		field.setCurrentText('Burn status')
	activate(ui.cboGroupPlots, 'Extended error bar')
	ui.chkGroupEnableSignLevelFilter.setChecked(True)
	ui.spinGroupSignLevelFilter.setValue(0.05)
	ui.spinGroupSignLevelFilter.editingFinished.emit()
	r = w.groupStatsTest.results
	log.append('two groups %s vs %s (%s): %s, %d features, active after p<=0.05: %s' % (ui.cboGroup1.currentText(), ui.cboGroup2.currentText(), w.metadata.activeField, r.test, len(r.data), r.getActiveFeatures()))
	yield 'step6_two_groups_p_filter'
	# 8: save the figure at 300 DPI (File > Save plot...)
	out = os.path.join(OUT, 'step8_two_groups_extended_error_bar_300dpi.png')
	QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, 'PNG (*.png)'))
	QtWidgets.QInputDialog.getInt = staticmethod(lambda *a, **k: (300, True))
	ui.mnuFileSavePlot.trigger()
	with open(out, 'rb') as f:
		header = f.read(24)
	log.append('saved %s at 300 DPI: %dx%d px' % ((out,) + struct.unpack('>II', header[16:24])))
	# multiple groups
	ui.tabWidgetProperties.setCurrentIndex(ui.tabWidgetProperties.indexOf(ui.tabMultipleGroups))
	r = w.multiGroupStatsTest.results
	log.append('multiple groups: %s, %d features, %d active' % (r.test, len(r.data), len(r.getActiveFeatures())))
	yield 'step7_multiple_groups'
	activate(ui.cboMultiGroupPlots, 'Post-hoc plot')
	yield 'step7_multiple_groups_post_hoc'


def run_steps(app):
	it = steps()

	def advance():
		try:
			name = next(it)
		except StopIteration:
			with open(os.path.join(OUT, 'walkthrough.log'), 'w') as f:
				f.write('\n'.join(log) + '\n')
			print('\n'.join(log))
			app.quit()
			return
		QtCore.QTimer.singleShot(800, lambda: (shot(name), QtCore.QTimer.singleShot(200, advance)))

	QtCore.QTimer.singleShot(1000, advance)


_origExec = QtWidgets.QApplication.exec


def fakeExec(*a):
	app = QtWidgets.QApplication.instance()
	run_steps(app)
	return _origExec()


QtWidgets.QApplication.exec = fakeExec
sys.argv = [sys.argv[0]]
STAMP.main()
