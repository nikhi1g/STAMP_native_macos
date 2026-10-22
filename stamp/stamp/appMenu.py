#=======================================================================
# Author: Nikhil Gupta (macOS port)
#
# The macOS application menu (the bold "STAMP" menu next to the Apple logo): About STAMP and
# Check for Updates... STAMP's own Windows-style menu bar stays inside its window.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#=======================================================================

import sys

# stable mimg.io routes (302 redirects managed on the site): the repo can move without an app update
SOURCE_URL = 'https://www.mimg.io/stamp/source'	# + '/<version>' = that version's exact source (GPL)

CREDITS_HTML = '''<div style="text-align:center; font-family:-apple-system; font-size:11px">
Statistical Analysis of Metagenomic Profiles<br><br>
Original STAMP &copy; 2011&ndash;2015 Donovan Parks and Robert Beiko.<br>
macOS port &copy; 2026 Nikhil Gupta.<br>
Free software under the GNU General Public License v3.<br>
<i><a href="{url}">mimg.io/stamp/source</a></i>
</div>'''

def creditsHtml(version):
	return CREDITS_HTML.replace('{url}', '%s/%s' % (SOURCE_URL, version))

_menuBar = None

def showAbout():
	from stamp.STAMP import appVersion
	if sys.platform == 'darwin':
		from stamp import macNative
		macNative.showAboutPanel('STAMP', appVersion(), creditsHtml(appVersion()))

def install(checkForUpdates):
	"""Add About STAMP and Check for Updates... to the application menu (macOS only)."""
	global _menuBar
	if sys.platform != 'darwin' or _menuBar is not None:
		return _menuBar
	from PyQt6 import QtWidgets, QtGui
	_menuBar = QtWidgets.QMenuBar()	# parentless: Qt's global native menu bar, merged into the app menu
	menu = _menuBar.addMenu('STAMP')
	about = QtGui.QAction('About STAMP', _menuBar)
	about.setMenuRole(QtGui.QAction.MenuRole.AboutRole)
	about.triggered.connect(showAbout)
	updates = QtGui.QAction('Check for Updates...', _menuBar)
	updates.setMenuRole(QtGui.QAction.MenuRole.ApplicationSpecificRole)
	updates.triggered.connect(checkForUpdates)
	menu.addAction(about)
	menu.addAction(updates)
	# macOS 26 style icons: info next to About, download next to Check for Updates (here and in the
	# Dock menu). Qt builds the native menus lazily, so set them once they exist.
	from PyQt6 import QtCore
	from stamp import macNative
	icons = [
		('app menu', 'About STAMP', 'info.circle', macNative.setAppMenuItemSymbol),
		('app menu', 'Check for Updates...', 'arrow.down.circle', macNative.setAppMenuItemSymbol),
		('Dock menu', 'Check for Updates...', 'arrow.down.circle', macNative.setDockMenuItemSymbol),
	]
	def addIcons(pending=icons, attempt=0):
		import logging
		left = []
		for icon in pending:
			if icon[3](icon[1], icon[2]):
				logging.info('%s: %s icon set (attempt %d)', icon[0], icon[1], attempt)
			else:
				left.append(icon)
		if left and attempt < 20:
			QtCore.QTimer.singleShot(250, lambda: addIcons(left, attempt + 1))
		elif left:
			logging.warning('menu icons not set: %s', ', '.join('%s %s' % icon[:2] for icon in left))
	QtCore.QTimer.singleShot(0, addIcons)
	return _menuBar
