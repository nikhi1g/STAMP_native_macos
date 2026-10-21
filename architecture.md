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
| Signing | Developer ID Application: NIKHIL GUPTA (G7955Z5DNB); hardened runtime, secure timestamp, no entitlements; app and DMG notarized and stapled (`packaging/sign_notarize.sh`, notary keychain profile `STAMP`) |
| Size | ~150-250 MB |

### Correctness
- Reference: the Docker build in `stamp_metagenomic_profiles`, used read-only once to generate
  expected outputs, stored in `tests/golden/`.
- Tests (pytest): upstream `STAMP_test.py`; the manual's CI-5 workflow (load profile +
  metadata, two-sample, two-group with p-value filter, multi-group, 300 DPI export); the
  Skirball demo (only Bacteroidetes remains after the p-value filter); the class soil tables;
  a headless GUI smoke test.
- Pass criterion (relaxed 2026-10-20 from 1e-9 relative, user decision relayed by the
  organizer session): every numeric output (p-values, corrected p-values, effect sizes, CI
  endpoints) passes if the absolute or the relative difference is <= 1e-6; every significance
  decision (the set of features passing each p-value or effect-size filter, per test and
  dataset) matches exactly; rows are matched by feature name, not order; tied-rank
  Benjamini-Hochberg values are verified against an independent implementation of upstream's
  formula. Cause of the 8th-9th digit noise: scipy 0.19 (reference) and 1.18 differ in the
  Student-t quantile `t.isf` that forms t-test and Welch CI endpoints, and upstream's
  hypergeometric right tail `(1 - cdf) + pdf` is floating-point noise below ~1e-11 in both.
- Accuracy criterion (independent of the reference): `tests/accuracy/` recomputes every exposed
  test, CI method, effect size, post-hoc test and correction with exact rationals or mpmath at 50
  digits (`oracle.py`, self-checked against closed forms). Pass: abs or rel diff <= 1e-12, except
  where the comment next to the assertion justifies a looser bound with its measured error
  (double-precision log-gamma in Fisher/hypergeometric, cancellation in G-tests, upstream's
  grid search in Newcombe-Wilson, the tabulated and interpolated studentized range in
  Tukey-Kramer/Games-Howell, Monte Carlo tests within binomial bounds). 13 upstream defects are
  pinned as strict xfails in `test_acc_defects.py` (see Findings).
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

## Distribution and updates (agreed 2026-10-21)
- Main download: a zip of the notarized app (`STAMP-<version>-<build>.zip`); `.pkg` and `.dmg` as
  secondary downloads. No dragging, finding files or passwords for the user.
- First launch outside an Applications folder: a native macOS alert in front of the STAMP window,
  "Move STAMP to your Applications folder?" with Move to Applications / Not Now. Move: copy to
  /Applications (or ~/Applications when the account cannot write /Applications), relaunch from there,
  move the downloaded app and zip (or ejected dmg) to the Trash. Not Now: a second alert, "Remind you
  next time STAMP opens?" with Remind Me / Don't Remind Me.
- Updates: Sparkle 2 inside the app, so users never return to the download page. Checks at launch and
  every 24 h; popup "Install and Relaunch / Later / Skip This Version" with release notes. Defaults:
  automatic checks on, automatic download and install off. "Check for Updates..." menu item and an
  update section in Preferences.
- Feed: `https://www.mimg.io/download/stamp/appcast.xml` (the only mutable file). Each release adds a
  zip at `https://www.mimg.io/download/stamp/<version>-<build>/STAMP-<version>-<build>.zip` (immutable), signed with
  Developer ID (notarized) and Sparkle's EdDSA key (user's keychain). Build numbers (CFBundleVersion)
  only increase; Sparkle compares them. `packaging/make_appcast.sh` adds each release to
  `packaging/appcast/appcast.xml`.
- Future, not yet scheduled: update popup and Preferences styled like STAMP's own (Windows-look) UI.

## Plan
1. Repository created (done).
2. Import upstream STAMP at `088aacd` (GPL-3) unmodified as the baseline commit (done,
   commit 2f96d76; `stamp/` tree hash equals the upstream commit's root tree).
3. Port: Python 2 -> 3, PyQt4 -> PyQt6, matplotlib QtAgg, biom-format 2.1.x; Windows style
   (Fusion fallback), in-window menu bar (done; see Verification below).
4. Generate golden outputs from the reference; parity tests pass (done; `tests/golden/`).
5. Package `STAMP.app` -> `STAMP-2.1.3.dmg`, Developer ID signed, notarized and stapled (done 2026-10-21).
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
- Verification in a clean environment (new user account / second Mac) before publishing.
- Hosting for the DMG + SHA-256 + source link (GPL-3).

## Findings (agent notes, not user specification)
- 2026-10-21 release build: bundle id `com.nikhilgupta.stamp` (was the upstream authors' domain);
  notarization accepted with no issues for the app (eecc54cd) and the DMG (a74f889d); `spctl`:
  Notarized Developer ID; stapler validate OK; signed app smoke test ready in 2-3 s.
  `dist/STAMP-2.1.3.dmg` SHA-256 e5a7a16c899f1d60a77131f95020d5b91c2425fda683edfce7d51d610701188c.
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
- Upstream statistical defects found by the mpmath accuracy suite (all present in the Windows
  build; kept for parity, each a strict xfail in `tests/accuracy/test_acc_defects.py`; fixing any
  of them changes results relative to the Windows build and is the user's call): Fisher's exact
  two-sided drops exactly tied tables (78 of 20214 small tables; e.g. (1,2,2,8) gives 0.533 for an
  exact 1.0); Fisher's one-sided mis-tails non-integer counts; Newcombe-Wilson misses a root in the
  last grid step (upper bound above 100%); the two-sample difference-between-proportions test and
  White's test crash on a zero parent count; the group ratio-of-proportions filter crashes on an
  all-zero feature; Bootstrap and White's permutation classify ties by float rounding; the t-test's
  zero-variance handler is unreachable; eta-squared cancels catastrophically on large offsets (1%
  error); the studentized-range table row for df = 2 is wrong; QTable crashes at 30 or more groups;
  Sidak's significant-feature count never resets.
- Verification of the final revision (2026-10-20): `uv run pytest -q` → 624 passed, 13 xfailed
  (parity 2558 scenarios, accuracy, core oracles, every plot in every mode, all dialogs, main
  window, end-to-end with real plugins, Skirball demo); `packaging/smoke_app.sh` on
  `dist/STAMP.app` → main window shown in 2 s with 15 tests and 18 plots loaded, no exception;
  `tests/walkthrough_ci5.py` → load Skirball phylum profile + metadata, two samples, two groups
  by Burn status with the p-value filter (only Bacteroidetes remains, p = 2.2e-4, enriched in
  unburned soil), 300 DPI export (2100x255 px), multiple groups + post-hoc; screenshots in
  `build/walkthrough_final/`. Side-by-side pixel comparison with the Windows build is not done
  (no Windows build available here); the extended error bar clips its right-hand
  "p-value (corrected)" label for 7-character p-values, which follows upstream's fixed 0.75 in
  label margin.
- Comparison with the user's Windows build (2026-10-20): the STAMP.exe installed under Porting
  Kit (`~/Applications/STAMP.app`, launched by `~/Desktop/STAMP.command`) ships its Python
  modules; all 167 are bytecode-identical to upstream's `v2.1.3` tag (checked with Python 2.7 in
  the reference image), and its 114 plugin `.py` files match the tag. Upstream changed only four
  files between that tag and the imported commit 088aacd: `STAMP.py` (+`svg.fonttype = 'none'`:
  SVG text stays text), both `HeatmapPlot.py` (minimum cell size guard; column labels rotated
  'vertical' instead of 270) and `White.py` (a 2016 "initial attempt" at a progress dialog that
  calls `setMaximum(list)` and crashes in the GUI whenever a group has fewer than 8 samples).
  The port keeps 088aacd's three author fixes and uses the v2.1.3 `White.py` (statistics
  identical; only progress handling differs), so White's test works on small groups exactly as in
  the user's exe (`test_whites_test_with_small_groups_in_the_gui`, 7 vs 7 Skirball samples).
  The 13 statistical defects in Findings are therefore all present in the user's exe as well.
