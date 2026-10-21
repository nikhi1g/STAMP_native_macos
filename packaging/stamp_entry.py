# PyInstaller entry point for STAMP.app. The upstream launcher (stamp/STAMP.py)
# does the same two lines; this copy exists so the frozen app has a fixed script
# path independent of the checkout layout.
import os

# PyInstaller's matplotlib runtime hook points MPLCONFIGDIR at a throw-away temp
# directory, so the font cache was rebuilt on every launch (about 5 s). Keep it in
# the user's cache folder instead; this must run before matplotlib is imported.
if True:
	cacheDir = os.path.join(os.path.expanduser('~'), 'Library', 'Caches', 'STAMP', 'matplotlib')
	try:
		os.makedirs(cacheDir, exist_ok=True)
		os.environ['MPLCONFIGDIR'] = cacheDir
	except OSError:
		pass

from stamp import STAMP

STAMP.main()
