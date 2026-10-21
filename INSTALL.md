# STAMP 2.1.3 for Apple Silicon Macs — install note

This replaces the "STAMP Download Instructions for Mac Users" (Porting Kit / Wine, or the
UCLA virtual desktop) in the 109BL lab manual, Experiment CI-5. STAMP now runs natively on
macOS 12 or later on Apple Silicon (M1 and later). No Windows, Wine, Porting Kit, virtual
machine or Docker is needed. Everything else in CI-5 (loading data, the Properties panel,
two samples / two groups / multiple groups, plots, saving figures) works exactly as the
manual describes for the Windows version, with the same windows, menus and shortcuts.

## Install (about one minute)
1. Open `STAMP-2.1.3.dmg`.
2. Drag `STAMP.app` into the `Applications` folder shown next to it. The DMG also contains
   the `examples` folder from STAMP and the `STAMP_Users_Guide.pdf`; copy them wherever you
   keep your course files if you want them.
3. Open STAMP from Applications. The first time, macOS asks whether to open an app downloaded
   from the internet; click **Open**. STAMP is signed with an Apple Developer ID and notarized
   by Apple, so no other steps are needed.
   Optional integrity check: `shasum -a 256 STAMP-2.1.3.dmg` should match the published
   `STAMP-2.1.3.dmg.sha256`.

## Use
- **File > Load data...** (⌘O): choose your ASV profile `.txt`/`.tsv` and your metadata file,
  exactly as in CI-5 steps 2–3.
- Shortcuts are the manual's Windows shortcuts with ⌘ instead of Ctrl: ⌘O load data,
  ⌘S save plot, ⌘W send the plot to its own window ("Ctrl + W and Save"), ⌘P properties
  panel, ⌘L group legend.
- Saved figures: choose PNG, PDF or SVG and enter the resolution when asked (300 DPI as the
  manual suggests).

## If something goes wrong
- Error dialogs look like the Windows version. The full details are written to
  `~/Library/Logs/STAMP/STAMP.log` (in Finder: Go > Go to Folder..., paste the path).
  Send that file along with a description of what you clicked.
- Preferences live in `~/Library/Preferences/com.beikolab.STAMP.plist`; delete it to reset.
