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
| Widget style | Qt "Windows" style, Fusion as fallback | Qt 6.11 ships the classic Windows style on macOS (verified: `QStyleFactory.keys()` = macOS, Windows, Fusion). Under Wine/Porting Kit, PyQt4's Vista style falls back to this same classic style, so it is the closest match. See Findings. |
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
2. Import upstream STAMP at `088aacd` (GPL-3) unmodified as the baseline commit (done,
   commit 2f96d76; `stamp/` tree hash equals the upstream commit's root tree).
3. Port: Python 2 -> 3, PyQt4 -> PyQt6, matplotlib QtAgg, biom-format 2.1.x; Windows style
   (Fusion fallback), in-window menu bar (done; see Verification below).
4. Generate golden outputs from the reference; parity tests pass (done; `tests/golden/`).
5. Package `STAMP.app` -> `STAMP.dmg` (done, ad-hoc signed); Developer ID signing and
   notarization pending the certificate.
6. One-page install note replacing the manual's Porting Kit steps.

## Running and debugging
- Dev run: `uv run python stamp/STAMP.py` (checkout) or `open dist/STAMP.app` (bundle).
- Build: `packaging/build_app.sh` (PyInstaller, ~40 s) then `packaging/make_dmg.sh`.
- Smoke the bundle and see its output in one go: `packaging/smoke_app.sh [seconds]`.
- Logs: the app writes `~/Library/Logs/STAMP/STAMP.log` (startup info: versions, paths,
  frozen or not; and the full traceback of every error that upstream's "An error has
  occured" dialog shows, which itself only names a line). The same text goes to stderr, so
  launching from a terminal (`dist/STAMP.app/Contents/MacOS/STAMP`) prints it live.
- Tests: `uv run pytest -q` (all, ~2 min; GUI tests run offscreen). Parity against the
  Python 2 reference: `uv run pytest tests/test_golden_parity.py`.
- Regenerate the reference output (needs Docker/colima; only a `$HOME` path can be mounted):
  `docker run --rm --platform linux/amd64 --user 0 --entrypoint python -v $PWD/tests/golden:/gold
  -v $PWD/tests/data/soil:/soil:ro stamp-ref:py2-088aacd /gold/generate.py /opt/STAMP /soil
  /gold/golden_py2.json`.
- Shortcuts as upstream defines them: Ctrl+O load, Ctrl+S save plot, Ctrl+W send plot to
  its own window (the manual's "Ctrl + W and Save"), Ctrl+P properties, Ctrl+L legend.

## Open items
- Apple Developer Program: confirm paid membership; create a Developer ID Application
  certificate; store notarization credentials.

## Findings (agent notes, not user specification)
- This Mac has two "Apple Development: <your Apple ID email> (DC2WXMK9MY)" certificates (testing
  only) and no Developer ID Application certificate. Xcode and `notarytool` are installed.
- The spec's premise that Qt's Windows styles do not run on macOS was wrong: Qt 6.11 on this
  Mac offers `Windows` (classic look) in `QStyleFactory`. The port uses it, with Fusion as the
  fallback. Pending the user's side-by-side check against the Windows build.
- Six upstream files (`QTable.py`, `KruskalWallis.py`, `GamesHowell.py`, `Scheffe.py`,
  `TukeyKramer.py`, `WelchUncorrected.py`) use classic-Mac CR line endings; they were
  normalized to LF so Python 3 can parse them.
- Reference for golden outputs: the Python 2 image is built from the Dockerfile embedded in
  `../stamp_metagenomic_profiles/run.sh` (extracted into the scratchpad, tagged
  `stamp-ref:py2-088aacd`, never run from the reference folder). `tests/golden/generate.py`
  runs unchanged under both interpreters and produces `tests/golden/*.json`.
- Class data used for parity tests: `tests/data/soil/` (109BL soil tables + metadata, copied
  from the reference project's `src/`).
- `biom-format` 2.1.x: the BIOM import dialog is adapted to the current API (the reference
  Docker build pinned 2.0.1 instead).
- Upstream behaviour kept unchanged for parity (identical in the Python 2 build; listed so
  nobody mistakes it for a port bug): White's test crashes in the GUI when a group has fewer
  than 8 samples; Kruskal-Wallis needs 5 samples per group; post-hoc tests crash on a group
  with a single sample; Benjamini-Hochberg and Bonferroni corrected p-values are not capped
  at 1; the effect-size filter's AND/OR labels are swapped in `filterFeatures`; Welch
  (uncorrected) post-hoc effect sizes are scaled by 1e4; the extended error bar title always
  says "(corrected)"; two settings keys are written under one name and read under another
  (box plot width, scatter bins); loading a second profile raised `KeyError ''` upstream and
  is fixed in the port (local cause: an empty field name after the combo box is cleared).
- Behaviour that differs from the Python 2 build by necessity: Monte Carlo tests (White's,
  Bootstrap, Permutation) draw a different random stream under Python 3 even with the same
  seed, so their p-values and bootstrap CIs agree only within Monte Carlo error; rows with
  tied p-values may list in a different order; text files are decoded as UTF-8.
- Matplotlib 1.4 look: each plot family restores the classic style (ticks in, black patch
  edges, cap size 3, round-number limits, edge-aligned bars) around its own `plot()`; the
  three base classes do this with slightly different code, which could be unified later.
- Qt on macOS ignores QMessageBox window titles (Apple guideline), so the About and error
  boxes show no title bar text, unlike Windows.
