import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM = os.path.join(ROOT, 'stamp')
if UPSTREAM not in sys.path:
	sys.path.insert(0, UPSTREAM)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
