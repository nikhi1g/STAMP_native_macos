# Lab-manual STAMP pathway (reference install)

Reproduces the 109BL lab manual's Mac setup (printed pp. 48-49, "STAMP Download Instructions
for Mac Users (Updated 5/6/24)") as the visual/behavioral reference for the native port.
Downloads live in `downloads/` (gitignored).

| Item | Source | Version | SHA-256 |
|---|---|---|---|
| STAMP Windows installer | github.com/dparks1134/STAMP/releases/download/v2.1.3/STAMP_2_1_3.exe (the manual's "executable binary" link on beikolab.cs.dal.ca) | 2.1.3 | `152745174051d2b0b6ed7b9c75eb7305ce08f5ad27b41e078b48d05ff70f2e13` |
| Porting Kit | github.com/vitor251093/porting-kit-releases (official), `Porting.Kit-6.7.0-arm64.dmg` | 6.7.0, arm64 | `7e33b70e326c7e5a99c531b65b678b605c44aaa107f51688777ad5dd9e5fbf5a` |

Notes
- 2026-10-20: PK 5.14.9 (last PK5, as the manual says) failed on macOS 26.5.2: with engine WS12WineStaging11.12_DXMT, "Registry not found" after engine extraction; on retry, "Downloaded file does not contain Master Wrapper named Wineskin-3.0.6-2.app" (the wrapper server no longer serves PK5's wrapper). PK5 is unusable today; replaced with PK 6.7.0 arm64 (5.14.9 app moved to Trash, its dmg kept in downloads/).
- portingkit.com/download now offers PK7 only; PK5 comes from the official releases repo.
- Porting Kit 6.7.0 arm64, notarized Developer ID (Vitor Marques de Miranda, 45WEPZ3433), installed to `/Applications/Porting Kit.app`.

Manual steps (GUI, done by hand)
1. Porting Kit -> All Apps -> Custom Port, name "STAMP".
2. Engine `WS11WineCX21.2.0`, OS Windows 10, window driver: Mac driver.
3. Install -> select `downloads/STAMP_2_1_3.exe`; click through the STAMP setup wizard.
4. Grant Porting Kit access to Desktop/Downloads when asked.
