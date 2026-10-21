"""Sparkle wiring (stamp/updater.py): framework location and safe no-op outside the app bundle."""
from stamp import updater


def test_framework_path_inside_bundle():
	assert updater.frameworkPath('/Applications/STAMP.app/Contents/MacOS/STAMP') == \
		'/Applications/STAMP.app/Contents/Frameworks/Sparkle.framework'
	assert updater.frameworkPath('/usr/bin/python3') is None


def test_start_is_noop_when_not_frozen(monkeypatch):
	monkeypatch.setattr(updater, '_controller', None)
	assert updater.start() is False    # tests run unfrozen: no Sparkle, no network


def test_menu_action_added_to_help_menu(qapp):
	from PyQt6 import QtWidgets

	class Ui:
		menu_Help = QtWidgets.QMenu('Help')
	class Window(QtWidgets.QMainWindow):
		pass
	w = Window(); w.ui = Ui()
	Ui.menu_Help.addAction('About')
	action = updater.addMenuAction(w)
	assert Ui.menu_Help.actions()[0] is action and action.text() == 'Check for Updates...'
