#=======================================================================
# Author: Nikhil Gupta (macOS port)
#
# First-run "Move to Applications" for the macOS app bundle.
#
# When STAMP.app runs from anywhere other than an Applications folder (Downloads after
# unzipping, a mounted DMG, macOS's translocated copy of either), offer to move it:
#   Move to Applications -> copy to /Applications (or ~/Applications when the account cannot
#     write /Applications, so no password is needed), verify the signature, relaunch from
#     there, then put the original and the leftover download (.zip, or the ejected .dmg) in
#     the Trash. Never asked again.
#   Not Now -> asked again at the next launch, unless "Don't remind me about this again" is
#     ticked, in which case it is never asked again.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#=======================================================================

import os
import re
import sys
import time
import ctypes
import logging
import plistlib
import zipfile
import subprocess

SETTINGS_KEY = 'Install/Do not offer move to Applications'
ENV_CLEANUP = 'STAMP_MOVE_CLEANUP'	# set on the relaunched copy: what to trash once the old one exits
APP_NAME = 'STAMP.app'
DOWNLOAD_ZIP = re.compile(r'^STAMP[-_ ]?[0-9.]*( \(\d+\))?\.zip$')

def bundlePath(executable):
	"""Path of the .app bundle containing executable, or None when not running from a bundle."""
	index = executable.find('.app/Contents/')
	return executable[:index + len('.app')] if index != -1 else None

def isTranslocated(path):
	return '/AppTranslocation/' in path

def originalPath(path):
	"""Real location of a translocated bundle (macOS runs quarantined apps opened from Downloads
	or a DMG from a randomized read-only path). Returns path unchanged when not translocated."""
	if not isTranslocated(path):
		return path
	try:
		cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
		sec = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/Security.framework/Security')
		cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
		cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
		cf.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
		cf.CFURLGetFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_char_p, ctypes.c_long]
		cf.CFRelease.argtypes = [ctypes.c_void_p]
		sec.SecTranslocateCreateOriginalPathForURL.restype = ctypes.c_void_p
		sec.SecTranslocateCreateOriginalPathForURL.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
		encoded = path.encode('utf-8')
		url = cf.CFURLCreateFromFileSystemRepresentation(None, encoded, len(encoded), True)
		original = sec.SecTranslocateCreateOriginalPathForURL(url, None)
		cf.CFRelease(url)
		if not original:
			return path
		buf = ctypes.create_string_buffer(4096)
		ok = cf.CFURLGetFileSystemRepresentation(original, True, buf, len(buf))
		cf.CFRelease(original)
		return buf.value.decode('utf-8').rstrip('/') if ok else path
	except Exception:
		logging.exception('could not resolve translocated path %s', path)
		return path

def applicationsDirs(home):
	return ['/Applications', os.path.join(home, 'Applications')]

def isInApplications(path, home):
	parent = os.path.dirname(os.path.realpath(path))
	for apps in applicationsDirs(home):
		apps = os.path.realpath(apps)
		if parent == apps or parent.startswith(apps + os.sep):
			return True
	return False

def destinationDir(home, canWrite=os.access):
	"""/Applications when this account can write it (admins), else ~/Applications (no password)."""
	if canWrite('/Applications', os.W_OK):
		return '/Applications'
	return os.path.join(home, 'Applications')

def shouldOffer(path, home, doNotOffer):
	return path is not None and not doNotOffer and not isInApplications(path, home)

def bundleInfo(bundle):
	try:
		with open(os.path.join(bundle, 'Contents', 'Info.plist'), 'rb') as f:
			return plistlib.load(f)
	except (OSError, plistlib.InvalidFileException):
		return {}

def bundleVersion(bundle):
	return bundleInfo(bundle).get('CFBundleShortVersionString', '0')

def existingTargetAction(target, source):
	"""What to do about a STAMP.app already at the destination:
	'none' (nothing there), 'replace' (this app, same or older version), 'open-existing' (this app,
	newer version) or 'foreign' (a different app that happens to be named STAMP.app; never touched)."""
	if not os.path.exists(target):
		return 'none'
	ourId = bundleInfo(source).get('CFBundleIdentifier')
	if not ourId or bundleInfo(target).get('CFBundleIdentifier') != ourId:
		return 'foreign'
	if versionKey(bundleVersion(target)) > versionKey(bundleVersion(source)):
		return 'open-existing'
	return 'replace'

def versionKey(version):
	return tuple(int(part) if part.isdigit() else 0 for part in re.split(r'[.\-]', str(version)))

def diskImageFor(path, hdiutilInfo=None):
	"""(mount point, image file) when path is on a mounted disk image, else (None, None)."""
	if not path.startswith('/Volumes/'):
		return None, None
	try:
		if hdiutilInfo is None:
			hdiutilInfo = subprocess.run(['hdiutil', 'info', '-plist'], capture_output=True, check=True).stdout
		info = plistlib.loads(hdiutilInfo)
	except Exception:
		return None, None
	for image in info.get('images', []):
		for entity in image.get('system-entities', []):
			mount = entity.get('mount-point')
			if mount and (path == mount or path.startswith(mount + '/')):
				return mount, image.get('image-path')
	return None, None

def leftoverZips(folder):
	"""Downloaded STAMP zips in folder that contain STAMP.app (the archive the app came from)."""
	found = []
	try:
		names = os.listdir(folder)
	except OSError:
		return found
	for name in names:
		if not DOWNLOAD_ZIP.match(name):
			continue
		path = os.path.join(folder, name)
		try:
			with zipfile.ZipFile(path) as z:
				if any(n == APP_NAME + '/' or n.startswith(APP_NAME + '/') for n in z.namelist()[:50]):
					found.append(path)
		except (OSError, zipfile.BadZipFile):
			continue
	return sorted(found)

def moveToTrash(path):
	from PyQt6 import QtCore
	if path and os.path.exists(path):
		ok = QtCore.QFile.moveToTrash(path)
		ok = ok[0] if isinstance(ok, tuple) else ok
		logging.info('moved to Trash: %s (%s)', path, 'ok' if ok else 'FAILED')
		return bool(ok)
	return False

def copyBundle(source, target):
	subprocess.run(['ditto', source, target], check=True)
	subprocess.run(['codesign', '--verify', '--strict', target], check=True, capture_output=True)

def relaunch(target, cleanup):
	env = dict(os.environ)
	env[ENV_CLEANUP] = '\n'.join(cleanup)
	subprocess.Popen(['open', '-n', '-a', target, '--env', '%s=%s' % (ENV_CLEANUP, env[ENV_CLEANUP])])

def cleanupAfterMove():
	"""Run in the relaunched copy: trash what the previous copy left behind, once it has quit."""
	spec = os.environ.pop(ENV_CLEANUP, '')
	if not spec:
		return
	items = spec.split('\n')
	pid = int(items[0]) if items and items[0].isdigit() else None
	for _ in range(100):	# wait up to 10 s for the old copy to exit (its volume must be free to eject)
		if pid is None:
			break
		try:
			os.kill(pid, 0)
		except OSError:
			break
		time.sleep(0.1)
	for item in items[1:]:
		kind, _, path = item.partition(':')
		if kind == 'detach':
			subprocess.run(['hdiutil', 'detach', path, '-quiet'], capture_output=True)
			logging.info('ejected %s', path)
		elif kind == 'trash':
			moveToTrash(path)

def offerMove(settings, parent=None):
	"""Ask to move STAMP.app into Applications. Returns True when STAMP relaunched from the new
	location and this process should quit."""
	from PyQt6 import QtWidgets
	if sys.platform != 'darwin' or not getattr(sys, 'frozen', False) or os.environ.get('STAMP_NO_MOVE_PROMPT'):
		return False	# not a macOS app bundle, or suppressed (automated smoke tests, managed installs)
	running = bundlePath(sys.executable)
	if running is None:
		return False
	source = originalPath(running)
	home = os.path.expanduser('~')
	doNotOffer = settings.value(SETTINGS_KEY, False, type=bool)
	if not shouldOffer(source, home, doNotOffer):
		return False

	box = QtWidgets.QMessageBox(parent)
	box.setIcon(QtWidgets.QMessageBox.Icon.Question)
	box.setWindowTitle('STAMP')
	box.setText('Move STAMP to your Applications folder?')
	box.setInformativeText('STAMP will then open from Applications, and the downloaded copy will be moved to the Trash.')
	moveButton = box.addButton('Move to Applications', QtWidgets.QMessageBox.ButtonRole.AcceptRole)
	box.addButton('Not Now', QtWidgets.QMessageBox.ButtonRole.RejectRole)
	box.setDefaultButton(moveButton)
	dontRemind = QtWidgets.QCheckBox("Don't remind me about this again")
	box.setCheckBox(dontRemind)
	box.exec()

	if box.clickedButton() is not moveButton:
		if dontRemind.isChecked():
			settings.setValue(SETTINGS_KEY, True)
		logging.info('move to Applications declined (do not remind: %s)', dontRemind.isChecked())
		return False

	targetDir = destinationDir(home)
	target = os.path.join(targetDir, APP_NAME)
	try:
		os.makedirs(targetDir, exist_ok=True)
		action = existingTargetAction(target, source)
		if action == 'foreign':
			raise OSError('another app named STAMP.app is already in %s (left untouched); move STAMP manually if you want both' % targetDir)
		if action == 'open-existing':
			logging.info('newer STAMP already in %s; opening it', targetDir)
			settings.setValue(SETTINGS_KEY, True)
			relaunch(target, [str(os.getpid())])
			return True
		if action == 'replace' and not moveToTrash(target):
			raise OSError('could not move the existing %s to the Trash' % target)
		copyBundle(source, target)
	except Exception as e:
		logging.exception('move to Applications failed')
		QtWidgets.QMessageBox.warning(parent, 'STAMP', 'STAMP could not be moved to %s:\n%s\n\nIt will keep running from its current location.' % (targetDir, e))
		return False

	settings.setValue(SETTINGS_KEY, True)	# in Applications now; never ask again
	settings.sync()
	cleanup = [str(os.getpid())]
	mount, image = diskImageFor(source)
	if mount:
		cleanup.append('detach:' + mount)
		if image:
			cleanup.append('trash:' + image)
	else:
		cleanup.append('trash:' + source)
		cleanup.extend('trash:' + z for z in leftoverZips(os.path.dirname(source)))
	logging.info('moved STAMP to %s; relaunching (cleanup: %s)', target, cleanup[1:])
	relaunch(target, cleanup)
	return True
