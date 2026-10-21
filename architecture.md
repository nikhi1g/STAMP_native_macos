# STAMP_native_macos

## Goal (user's specification)
Run STAMP (Statistical Analysis of Metagenomic Profiles) natively on macOS: no virtual
machine, Porting Kit/Wine, Windows, or Docker. Distributable: if it runs on this Mac, it
runs on any Mac.

## Context
- The 109BL lab manual (printed pp. 48-49) has Mac users run the Windows `STAMP.exe`
  through Porting Kit (Wine engine WS11WineCX21.2.0) or the UCLA virtual desktop. That is
  the setup being replaced.
- User interface: match the STAMP interface seen on the lab-manual path (Windows build),
  not the one in `projLab/stamp_metagenomic_profiles`.
- `projLab/stamp_metagenomic_profiles` (Docker + noVNC) is a parallel attempt that does not
  meet the goal. It stays untouched and serves only as inspiration and a reference for
  correct results. Look nowhere outside projLab.

## Plan (agreed)
1. This repository (git, own history).
2. Import upstream STAMP source at the verified commit (`088aacd`, GPL-3) unmodified as baseline.
3. Port Python 2 -> 3, PyQt4 -> Qt 6, matplotlib Qt backend, current biom-format API.
4. Parity against the Docker reference: upstream `STAMP_test.py`; the manual's CI-5 workflow
   (load profile + metadata, two-sample, two-group with p-value filter, multi-group,
   300 DPI figure export); the class soil tables.
5. Package `STAMP.app` -> `STAMP.dmg` (Apple Silicon + Intel), signed.
6. One-page install note replacing the manual's Porting Kit steps.

## Open decisions
- PyQt6 (recommended) vs PySide6.
- Apple Developer ID for notarization, or unsigned with right-click -> Open on first launch.
