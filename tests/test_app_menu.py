"""macOS application menu (stamp/appMenu.py): About STAMP and Check for Updates... with the right roles."""
import sys
import pytest
from stamp import appMenu


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS application menu')
def test_app_menu_items_and_roles(qapp, monkeypatch):
	from PyQt6 import QtGui
	monkeypatch.setattr(appMenu, '_menuBar', None)
	bar = appMenu.install(lambda: None)
	items = {a.text(): a.menuRole() for a in bar.actions()[0].menu().actions()}
	assert items == {'About STAMP': QtGui.QAction.MenuRole.AboutRole,
		'Check for Updates...': QtGui.QAction.MenuRole.ApplicationSpecificRole}


def test_credits_text():
	assert 'Donovan Parks and Robert Beiko' in appMenu.CREDITS_HTML
	assert '<i><a href="https://github.com/nikhi1g/STAMP_native_macos">' in appMenu.CREDITS_HTML
	assert 'Source:' not in appMenu.CREDITS_HTML
