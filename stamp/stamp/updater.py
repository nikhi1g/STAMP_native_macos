#=======================================================================
# Author: Nikhil Gupta (macOS port)
#
# In-app updates via Sparkle 2 (bundled as Contents/Frameworks/Sparkle.framework).
# Feed, public EdDSA key and defaults (automatic checks on, automatic install off, every 24 h)
# are in the app's Info.plist (SUFeedURL, SUPublicEDKey, SUEnableAutomaticChecks,
# SUAutomaticallyUpdate, SUScheduledCheckInterval). Sparkle shows its own native macOS UI:
# "Install and Relaunch / Later / Skip This Version".
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#=======================================================================

import os
import sys
import ctypes
import logging

_controller = None

def frameworkPath(executable=None):
	executable = executable or sys.executable
	index = executable.find('.app/Contents/')
	if index == -1:
		return None
	return os.path.join(executable[:index + len('.app')], 'Contents', 'Frameworks', 'Sparkle.framework')

def start():
	"""Start Sparkle's standard updater (scheduled checks per Info.plist). No-op outside the macOS
	app bundle or when Sparkle is not bundled. Returns True when the updater is running."""
	global _controller
	if _controller is not None:
		return True
	if sys.platform != 'darwin' or not getattr(sys, 'frozen', False) or os.environ.get('STAMP_NO_UPDATER'):
		return False
	path = frameworkPath()
	if not path or not os.path.isdir(path):
		logging.info('updater: Sparkle.framework not bundled; updates disabled')
		return False
	try:
		from stamp import macNative as objc
		bundle = objc.send(objc.cls('NSBundle'), 'bundleWithPath:', objc.nsstring(path))
		if not bundle or not objc.send(bundle, 'load', restype=ctypes.c_bool):
			raise RuntimeError('could not load ' + path)
		controllerClass = objc.cls('SPUStandardUpdaterController')
		controller = objc.send(objc.send(controllerClass, 'alloc'), 'initWithStartingUpdater:updaterDelegate:userDriverDelegate:',
			True, None, None, argtypes=[ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p])
		if not controller:
			raise RuntimeError('SPUStandardUpdaterController init failed')
		_controller = controller
		logging.info('updater: Sparkle started (%s)', path)
		return True
	except Exception:
		logging.exception('updater: could not start Sparkle; updates disabled')
		return False

def checkForUpdates():
	"""User-initiated check (Help > Check for Updates...): Sparkle shows the result either way."""
	if _controller is None and not start():
		from PyQt6 import QtWidgets
		QtWidgets.QMessageBox.information(None, 'STAMP', 'Updates are available only in the installed STAMP app.')
		return
	from stamp import macNative as objc
	objc.send(_controller, 'checkForUpdates:', None, restype=None)

def addMenuAction(mainWindow):
	"""Add Help > Check for Updates... to the (in-window) menu bar."""
	from PyQt6 import QtGui
	menu = getattr(mainWindow.ui, 'menu_Help', None) if hasattr(mainWindow, 'ui') else None
	if menu is None:
		return None
	action = QtGui.QAction('Check for Updates...', mainWindow)
	action.setMenuRole(QtGui.QAction.MenuRole.NoRole)
	action.triggered.connect(checkForUpdates)
	actions = menu.actions()
	menu.insertAction(actions[0] if actions else None, action)
	if actions:
		menu.insertSeparator(actions[0])
	return action
