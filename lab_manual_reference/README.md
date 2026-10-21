# Lab-manual STAMP pathway (reference install)

Reproduces the 109BL lab manual's Mac setup (printed pp. 48-49, "STAMP Download Instructions
for Mac Users (Updated 5/6/24)") as the visual/behavioral reference for the native port.
Downloads live in `downloads/` (gitignored).

| Item | Source | Version | SHA-256 |
|---|---|---|---|
| STAMP Windows installer | github.com/dparks1134/STAMP/releases/download/v2.1.3/STAMP_2_1_3.exe (the manual's "executable binary" link on beikolab.cs.dal.ca) | 2.1.3 | `152745174051d2b0b6ed7b9c75eb7305ce08f5ad27b41e078b48d05ff70f2e13` |
| Porting Kit | github.com/vitor251093/porting-kit-releases (official), `Porting-Kit-5.14.9.dmg` | 5.14.9 (last PK5; manual says "PK5") | `5f9524b755276dc4537df961be0a74d6aaaea2f28d82c1a519ae06b22a12aa48` |

Notes
- portingkit.com/download now offers PK7 only; PK5 comes from the official releases repo.
- Porting Kit 5.14.9 is x86_64 only; runs under Rosetta. Signed and notarized (Developer ID
  Application: Vitor Marques de Miranda, 45WEPZ3433). Installed to `/Applications/Porting Kit.app`.

Manual steps (GUI, done by hand)
1. Porting Kit -> All Apps -> Custom Port, name "STAMP".
2. Engine `WS11WineCX21.2.0`, OS Windows 10, window driver: Mac driver.
3. Install -> select `downloads/STAMP_2_1_3.exe`; click through the STAMP setup wizard.
4. Grant Porting Kit access to Desktop/Downloads when asked.
