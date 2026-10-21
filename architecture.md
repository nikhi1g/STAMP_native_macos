# STAMP_native_macos

## Goal (user's specification)
Run STAMP (Statistical Analysis of Metagenomic Profiles) natively on macOS: no virtual
machine, Porting Kit/Wine, Windows, or Docker. Distributable: if it runs on this Mac, it
runs on any Apple Silicon Mac.

The user interface must preserve the original STAMP interface as seen on the lab-manual path
(Windows `STAMP.exe`): the Windows look, as close as possible to an exact match.

## Context
- The 109BL lab manual (printed pp. 48-49) has Mac users run the Windows `STAMP.exe` through
  Porting Kit (Wine engine WS11WineCX21.2.0) or the UCLA virtual desktop. That is the setup
  being replaced.
- `projLab/stamp_metagenomic_profiles` (Docker + noVNC) is a parallel attempt that does not
  meet the goal. It stays untouched and serves only as inspiration and as the read-only
  reference for correct results. Look nowhere outside projLab.

## Stack (agreed)

### Runtime (ships inside `STAMP.app`)
| Layer | Choice | Notes |
|---|---|---|
| Platform | macOS 12+ on Apple Silicon (arm64) only | Intel is out of scope |
| Language | Python 3.12 | |
| GUI toolkit | PyQt6 (Qt 6.x) | Closest API to STAMP's PyQt4; GPL matches STAMP's GPL-3 |
| Layout | STAMP's original `.ui` files and icons, unchanged | Same windows, panels, dialogs, menus |
| Widget style | Qt Fusion | Closest available match to the Windows look; Qt's Windows styles do not run on macOS |
| Menu bar | Inside the STAMP window (not the macOS top bar) | Matches Windows |
| Shortcuts | Original (Ctrl+O load data, Ctrl+W save plot) mapped to ⌘O / ⌘W | |
| Plotting | matplotlib 3.x, QtAgg backend | 300 DPI figure export (manual CI-5 step 8) |
| Numerics | numpy 2.x, scipy 1.x | Results must match the reference (see Correctness) |
| BIOM import | biom-format 2.1.x | Import dialog adapted to the current API |
| Dropped | pyqi, py2exe, h5py | Not used by the CI-5 workflow |

### Build and distribution
| Item | Choice |
|---|---|
| Dependencies | uv with a lockfile (`uv.lock`) |
| Packaging | PyInstaller -> `STAMP.app` -> `STAMP.dmg` |
| Signing | Developer ID Application certificate + notarization + stapling (pending confirmation of the paid program and certificate) |
| Fallback signing | Ad-hoc; users right-click -> Open on first launch |
| Size | ~150-250 MB |

### Correctness
- Reference: the Docker build in `stamp_metagenomic_profiles`, used read-only once to generate
  expected outputs, stored in `tests/golden/`.
- Tests (pytest): upstream `STAMP_test.py`; the manual's CI-5 workflow (load profile +
  metadata, two-sample, two-group with p-value filter, multi-group, 300 DPI export); the
  Skirball demo (only Bacteroidetes remains after the p-value filter); the class soil tables;
  a headless GUI smoke test.
- Pass criterion: p-values, effect sizes and confidence intervals match the reference to 1e-9
  relative tolerance; filtered feature lists match exactly.
- UI check: side-by-side screenshots against the Windows build for the main window and the
  dialogs used in CI-5.

### Repository layout
```
STAMP_native_macos/
├── AGENTS.md, architecture.md
├── stamp/                 upstream 088aacd, ported in place (first commit = untouched baseline)
├── tests/, tests/golden/  parity tests + expected outputs from the reference
├── packaging/             PyInstaller spec, DMG script, icon, signing/notarization script
└── pyproject.toml, uv.lock
```

## Plan
1. Repository created (done).
2. Import upstream STAMP at `088aacd` (GPL-3) unmodified as the baseline commit.
3. Port: Python 2 -> 3, PyQt4 -> PyQt6, matplotlib QtAgg, biom-format 2.1.x; Fusion style,
   in-window menu bar.
4. Generate golden outputs from the reference; parity tests pass.
5. Package `STAMP.app` -> `STAMP.dmg`, signed and notarized.
6. One-page install note replacing the manual's Porting Kit steps.

## Open items
- Apple Developer Program: confirm paid membership; create a Developer ID Application
  certificate; store notarization credentials.

## Findings (agent notes, not user specification)
- This Mac has two "Apple Development: <your Apple ID email> (DC2WXMK9MY)" certificates (testing
  only) and no Developer ID Application certificate. Xcode and `notarytool` are installed.
