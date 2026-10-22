# STAMP 2.1.9: edit error during the release (2026-10-22)

## What happened
While adding the download icon next to Check for Updates (STAMP menu and Dock menu), a scripted
edit of `stamp/stamp/appMenu.py` matched an empty span (its end marker, `return _menuBar`, first
occurs earlier in `install()`), so Python's `str.replace` inserted the new block between every
character of the file. `git diff --stat` showed `appMenu.py | 61796 ++++`, and
`uv run pytest -q tests/test_app_menu.py` failed with `1 error during collection`.

## What was done
- The file was restored with `git checkout -- stamp/stamp/appMenu.py` and the edit redone with
  bounded indexes; the committed diff (`e62f749`) touches only the icon code in `appMenu.py` and
  the new helpers in `macNative.py` (36 insertions, 15 deletions).
- The full gate then passed: `uv run pytest -q`: 639 passed, 13 xfailed.
- A source run logged all three menu icons set on the first attempt
  (`~/Library/Logs/STAMP/STAMP.log`).
- The corrupted file was never committed, built or released.

## Required follow-up (not done here, by instruction)
Analyze 2.1.9 against the original port (2.1.4/2.1.8 and upstream STAMP v2.1.3) and confirm parity:
the only intended change is the menu icon. Parity with the original port is paramount and must not
change. Check at least `git diff v2.1.8 v2.1.9`, the full test suite, and the CI-5 walkthrough
(`tests/walkthrough_ci5.py`).
