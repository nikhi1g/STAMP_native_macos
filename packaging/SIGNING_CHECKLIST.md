# STAMP signing checklist (Developer ID, team G7955Z5DNB)

## You (manual)
- [x] 1. Xcode -> Settings -> Apple Accounts -> click "Nikhil Gupta" row (>) -> team G7955Z5DNB -> Manage Certificates... -> + -> Developer ID Application -> Done
- [x] 2. account.apple.com -> Sign-In and Security -> App-Specific Passwords -> + "STAMP notarization" -> copy it
- [x] 3. In the Claude chat:  ! xcrun notarytool store-credentials "STAMP" --apple-id <your Apple ID email> --team-id G7955Z5DNB   (paste password)

## Claude (automatic)
- [x] 4. Confirm certificate + notarization profile
- [x] 5. Write packaging/sign_notarize.sh
- [x] 6. Rebuild + sign STAMP.app (hardened runtime, timestamp)
- [x] 7. Notarize + staple app
- [x] 8. Build, sign, notarize, staple DMG
- [x] 9. Verify: codesign / spctl / stapler / smoke test
- [x] 10. Hand-off: dist/STAMP-2.1.3.dmg + SHA-256, INSTALL.md, architecture.md

Status: DONE. dist/STAMP-2.1.3.dmg signed, notarized, stapled. SHA-256 e5a7a16c...188c. Next: clean-environment verification, then publish; rotate the app-specific password.

## .pkg installer (2026-10-21)
- [x] P1. You: Xcode -> Settings -> Apple Accounts -> NIKHIL GUPTA -> Manage Certificates -> + -> Developer ID Installer
- [x] P2. Claude: script ready (packaging/make_pkg.sh); build STAMP-2.1.3.pkg (installs STAMP.app to /Applications), sign with Developer ID Installer
- [x] P3. Claude: notarize + staple pkg; verify (pkgutil --check-signature, spctl -t install, stapler)
- [~] P4. You: click through the installer (opened) -> then Claude checks /Applications/STAMP.app; ; hand file + SHA-256 to release
