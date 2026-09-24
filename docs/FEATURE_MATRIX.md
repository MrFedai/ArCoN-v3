# ArCoN v2.5 → v3.0 Feature Parity Matrix

Source of feature IDs: `docs/AUDIT.md` §2. Update this file in every phase.

**Action:** keep (same intent/behaviour) · replace (same intent, different mechanism) · fix (v2.5 behaviour is a bug/unsafe; not ported as-is without owner approval) · N-A (with reason) · new
**Reversible:** yes · partial · no · ONE-WAY (third-party code, D16)
**Status values:** NOT MIGRATED · MIGRATED (label) where label = UNIT / INTEGRATION / VM / NATIVE — the highest level actually run. Core items are distro-independent, so all Linux columns carry the same label.

| ID | Feature | Target module | Action | Reversible | Arch | Debian | Ubuntu | Fedora | Windows | macOS |
|---|---|---|---|---|---|---|---|---|---|---|
| F01 | stale pacman lock removal | core/preflight.py | fix (ask, never silent) | n/a | MIGRATED (UNIT) | N-A | N-A | N-A | stub | stub |
| F02 | internet check | core/preflight.py | fix | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F03 | disk ≥ 10 GB | core/preflight.py | keep | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F04 | sudo check | core/preflight.py | keep | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F05 | Live-USB detection | core/preflight.py | fix (was commented out) | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F06 | OS detection | platform/detect.py | fix (parse, don't source) | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F07 | package-manager selection | package/providers.py | replace | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT; dry-run against real apt in Ubuntu 24.04 container) | MIGRATED (UNIT) | stub | stub |
| F08 | package groups (76 → 7 groups, 70 kept, 6 removed: D28) | arcon/data/packages.toml | replace (per-distro names) | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT; dry-run against real apt in Ubuntu 24.04 container) | MIGRATED (UNIT) | stub | stub |
| F09 | main menu | cli.py / core/wizard.py | replace (D14) | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F10 | Smart Factory Reset | recovery/reset.py + `arcon reset` | fix (D19: explicit paths, protected list, verified backup) | partial | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F11 | resume | recovery/journal.py | fix (never worked) | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F12 | GPG / keyring reset | system/actions.py | fix (opt-in reset) | no | MIGRATED (UNIT) | N-A | N-A | N-A | N-A | N-A |
| F13 | reflector mirror benchmark | system/actions.py | keep + backup | yes | MIGRATED (UNIT) | N-A | N-A | N-A | N-A | N-A |
| F14 | speed test | core/preflight.py | keep | n/a | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | stub | stub |
| F15 | yay-bin build | package/actions.py (InstallAurHelper) | keep (temp dir) | yes | MIGRATED (UNIT) | N-A | N-A | N-A | N-A | N-A |
| F16 | deps + system upgrade | system/actions.py | fix (no partial upgrade) | no | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F17 | GNOME settings (gno.conf) | desktop/gnome.py | keep (D8; D18 default wallpaper = solid black) | yes (dconf dump) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (INTEGRATION: real run, Ubuntu 24.04 container) | MIGRATED (UNIT) | N-A | N-A |
| F18 | GNOME debloat | desktop/gnome.py | keep | partial | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | N-A | N-A |
| F19 | Gaming Mode + GPU drivers | gaming/actions.py (+ system multilib) | fix (decouple from GNOME, detect GPU) | partial | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F20 | package engine (preview, pacs.txt, AUR split) | package/resolve.py + package/actions.py | keep (batch install) | partial | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (INTEGRATION: real run, Ubuntu 24.04 container) | MIGRATED (UNIT) | stub | stub |
| F21 | BlackArch manager | security/actions.py (BlackArch*) | fix (checksum, key, no --overwrite default) | partial | MIGRATED (NOT TESTED) | N-A | N-A | N-A | N-A | N-A |
| F22 | Hyprland + theme installers | desktop/hyprland.py + dotfiles/manager.py | keep optional (D12), installers ONE-WAY (D16) | ONE-WAY | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | N-A | N-A |
| F23 | Terminator config + wallpapers | dotfiles/manager.py | keep + backup/diff (D10) | yes | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (INTEGRATION: real run, Ubuntu 24.04 container) | MIGRATED (UNIT) | N-A | stub |
| F24 | terminal emulator + theme | terminal/actions.py | fix (URLs, no overwrite) | yes | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F25 | shell + prompt themes | terminal/actions.py | fix (no curl-pipe-sh: pinned git clones) | partial | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (INTEGRATION: real run, Ubuntu 24.04 container) | MIGRATED (UNIT) | stub | stub |
| F26 | security tools + dashboard | security/actions.py | keep | partial | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F27 | optimization steps | optimization/actions.py | fix (install deps, labels) | yes | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F28 | security scans | security/actions.py (Scans) | keep (scope C-6) | n/a | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | stub | stub |
| F29 | hardening sysctl + SSH | security/actions.py | fix (drop-in + sshd -t) | yes | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F30 | Hardened Mode (OpenSnitch, USBGuard) | security/actions.py | fix (decouple from F29) | yes | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | stub | stub |
| F31 | final summary | core/engine.py (report) | fix (from journal) | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F32 | cleanup (orphans, cache) | optimization/actions.py (cleanup) | fix (no -Scc default) | no | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| F33 | reboot prompt | cli.py (reboot prompt) | keep | n/a | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | MIGRATED (NOT TESTED) | stub | stub |
| N1 | monitor mode detection + layout (D13) | display/* | new | yes | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| N2 | dotfile capture / diff (D10) | dotfiles/capture.py, dotfiles/diff.py | new | yes | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| N3 | wizard → summary → single confirm, saved answers (D14) | core/wizard.py, core/profile.py | new | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| N4 | dry-run for every action | core/runner.py | new | n/a | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (UNIT) | stub | stub |
| N5 | rollback (snapshot / file backup) | recovery/* | new (D6) | — | MIGRATED (UNIT) | MIGRATED (UNIT) | MIGRATED (INTEGRATION: real run, Ubuntu 24.04 container) | MIGRATED (UNIT) | stub | stub |
