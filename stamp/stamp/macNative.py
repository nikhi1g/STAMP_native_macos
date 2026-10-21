#=======================================================================
# Author: Nikhil Gupta (macOS port)
#
# Minimal Objective-C runtime bridge (ctypes, no extra dependency) for the few native macOS
# pieces STAMP uses: NSAlert for system-level questions, and loading Sparkle for updates.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#=======================================================================

import ctypes
import ctypes.util

_objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
ctypes.cdll.LoadLibrary('/System/Library/Frameworks/AppKit.framework/AppKit')
_objc.objc_getClass.restype = ctypes.c_void_p
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = ctypes.c_void_p
_objc.sel_registerName.argtypes = [ctypes.c_char_p]

def _msg(restype, *argtypes):
	f = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)
	return f(ctypes.cast(_objc.objc_msgSend, ctypes.c_void_p).value)

def cls(name):
	return _objc.objc_getClass(name.encode())

def sel(name):
	return _objc.sel_registerName(name.encode())

def send(obj, selector, *args, restype=ctypes.c_void_p, argtypes=None):
	if argtypes is None:
		argtypes = [ctypes.c_void_p] * len(args)
	return _msg(restype, *argtypes)(obj, sel(selector), *args)

def nsstring(text):
	return send(cls('NSString'), 'stringWithUTF8String:', text.encode('utf-8'), argtypes=[ctypes.c_char_p])

NSAlertFirstButtonReturn = 1000

def alert(message, buttons, suppressionTitle=None, informative=None):
	"""Native modal NSAlert in front of all windows. Returns (index of the clicked button,
	whether the suppression checkbox was ticked)."""
	app = send(cls('NSApplication'), 'sharedApplication')
	send(app, 'activateIgnoringOtherApps:', True, restype=None, argtypes=[ctypes.c_bool])
	a = send(send(cls('NSAlert'), 'alloc'), 'init')
	send(a, 'setMessageText:', nsstring(message), restype=None)
	if informative:
		send(a, 'setInformativeText:', nsstring(informative), restype=None)
	for title in buttons:
		send(a, 'addButtonWithTitle:', nsstring(title))
	if suppressionTitle:
		send(a, 'setShowsSuppressionButton:', True, restype=None, argtypes=[ctypes.c_bool])
		send(send(a, 'suppressionButton'), 'setTitle:', nsstring(suppressionTitle), restype=None)
	result = send(a, 'runModal', restype=ctypes.c_long)
	suppressed = False
	if suppressionTitle:
		suppressed = send(send(a, 'suppressionButton'), 'state', restype=ctypes.c_long) == 1
	send(a, 'release', restype=None)
	return result - NSAlertFirstButtonReturn, suppressed
