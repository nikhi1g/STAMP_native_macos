# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for STAMP 2.1.3 on Apple Silicon macOS.
#   uv run pyinstaller packaging/STAMP.spec --noconfirm
# Output: dist/STAMP.app (ad-hoc signed by PyInstaller; Developer ID signing and
# notarization are a separate step, see packaging/sign.sh once a certificate exists).
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
UPSTREAM = os.path.join(ROOT, 'stamp')          # upstream root: contains the `stamp` package
PACKAGE = os.path.join(UPSTREAM, 'stamp')

# collect_submodules imports the package in this process: it must be importable here,
# not only through pathex (otherwise it silently returns nothing and the app starts
# without any plugin).
sys.path.insert(0, UPSTREAM)
STAMP_MODULES = collect_submodules('stamp')
assert any(m.endswith('.plots.ExtendedErrorBar') for m in STAMP_MODULES), STAMP_MODULES

a = Analysis(
    [os.path.join(SPECPATH, 'stamp_entry.py')],
    pathex=[UPSTREAM],
    binaries=[],
    datas=[
        # critical-value tables (QTable) and COG category files (COG_IO): both are
        # located relative to the package / main dir as `stamp/data/...`
        (os.path.join(PACKAGE, 'data'), os.path.join('stamp', 'data')),
    ],
    # plugins are discovered with pkgutil at run time; nothing imports them by name
    hiddenimports=STAMP_MODULES + ['matplotlib.backends.backend_qtagg'],
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['QtAgg']}},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtWebEngineCore', 'PyQt6.QtMultimedia',
              'PyQt6.QtBluetooth', 'PyQt6.QtNfc', 'PyQt6.QtPositioning', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
              'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtXml', 'PyQt6.QtNetwork', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
              'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.QtSvgWidgets', 'PyQt6.QtDesigner', 'PyQt6.QtHelp',
              'PyQt6.QtRemoteObjects', 'PyQt6.QtSpatialAudio', 'PyQt6.QtTextToSpeech', 'PyQt6.QtWebChannel',
              'PyQt6.QtWebSockets', 'PyQt6.QtDBus', 'PyQt6.QtMultimediaWidgets', 'PyQt6.QtQuick3D', 'PyQt6.QtQuickWidgets',
              'PyQt6.QtStateMachine', 'PyQt6.QtHttpServer', 'PyQt6.QtGraphs', 'PyQt6.QtGraphsWidgets'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='STAMP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PACKAGE, 'icons', 'STAMP.icns'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='STAMP')
app = BUNDLE(
    coll,
    name='STAMP.app',
    icon=os.path.join(PACKAGE, 'icons', 'STAMP.icns'),
    bundle_identifier='com.nikhilgupta.stamp',
    info_plist={
        'CFBundleName': 'STAMP',
        'CFBundleDisplayName': 'STAMP',
        'CFBundleShortVersionString': '2.1.3',
        'CFBundleVersion': '2',
        'LSMinimumSystemVersion': '12.0',
        'NSHighResolutionCapable': True,
        # light window chrome: the content uses Qt's Windows style with its light palette, so
        # a dark-mode title bar would clash with the Windows build's look
        'NSRequiresAquaSystemAppearance': True,
        'NSHumanReadableCopyright': 'Copyright 2011-2015 Donovan Parks. GPL-3.0.',
        'LSApplicationCategoryType': 'public.app-category.education',
    },
)
