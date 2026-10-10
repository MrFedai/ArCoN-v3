# ArCoN v3.0 — final audit (2026-09-24, CI results updated 2026-10-10)

Verdicts: **PASS** (tested at the stated level) · **PARTIAL** (some paths tested) · **NOT TESTED** (implemented, never executed for real) · **FAIL**.
"Container" never validates GPU, monitors, a real desktop session or hardware.

## Summary

| Area | Verdict | Highest level | Evidence |
|---|---|---|---|
| Owner dotfiles protected (D8/D18) | PASS | INTEGRATION | sha256 manifest, owner settings, D18 checker (mutation test), golden v3 files, real dconf load in container |
| Core: runner, profile, journal, backup, rollback, engine, wizard, CLI | PASS | INTEGRATION (4 distro containers) | 60+ unit tests; real apply → idempotent re-run → rollback on archlinux, debian:stable, ubuntu:24.04, fedora (CI run 36058864740) |
| Resume (F11) | PASS | UNIT | failure → resume skips done actions |
| Preflight (F01–F05) | PARTIAL | UNIT | live ISO, stale lock asked; sudo/network only exercised in the real run |
| Speed test (F14) | NOT TESTED | — | implemented, never executed |
| Packages: native (pacman / apt / dnf) | PASS | INTEGRATION | CI run 36058864740: real install of one package (`tree`) on all four distros; catalog verified per distro — Arch 105 official + 11 AUR / 7 missing, Debian 83 / 5, Ubuntu 81 / 7, Fedora 71 / 8 (missing → runtime fallback) |
| AUR helper + AUR packages | NOT TESTED | UNIT (plan only) | makepkg never executed |
| Flatpak fallback | PARTIAL | UNIT + dry run | Flathub ids not verified (flathub.org unreachable) |
| System upgrade / multilib / mirrors / keyring reset | PARTIAL | UNIT | text transforms tested; commands never executed |
| GNOME settings (F17) | PASS | INTEGRATION | real dconf database via dbus-run-session; rollback restores |
| GNOME debloat (F18) | PARTIAL | UNIT | |
| Display D13 — GNOME | PARTIAL | UNIT (fake Mutter) | **no live Mutter session** — first native run must be `arcon plan` (Mutter verify mode) |
| Display D13 — Hyprland | PARTIAL | UNIT | `desc:` matching not checked on real Hyprland |
| Gaming / GPU drivers (F19) | PARTIAL | UNIT | package selection per GPU tested; no driver installed anywhere |
| Dotfiles deploy/diff/capture (F23, N2) | PASS | INTEGRATION | Terminator config deployed byte-identical in the real run |
| Hyprland module (F22) | PARTIAL | UNIT | rendered files D18-valid |
| Terminal themes (F24) | PARTIAL | UNIT | kitty kitten / alacritty import never executed |
| Shell: zsh + Oh-My-Zsh (F25) | PASS | INTEGRATION | pinned clone + `.zshrc` + chsh in the real run |
| Shell: fish/bash + Starship | PARTIAL | UNIT | |
| Security: sysctl, firewall, SSH (F29) | PARTIAL | UNIT | ssh drop-in + `sshd -t` path never executed |
| Security: scans, OpenSnitch, USBGuard (F28, F30) | NOT TESTED | — | |
| BlackArch (F21) | NOT TESTED | — | |
| Optimization / cleanup (F27, F32) | PARTIAL | UNIT | |
| Factory reset (F10) | PARTIAL | UNIT | configs backup/restore tested; package removal and dconf reset only with FakeRunner |
| Reboot prompt (F33) | NOT TESTED | — | |
| Windows / macOS (D3) | PASS | UNIT | stubs refuse with exit 3 |
| CI workflow | PASS | INTEGRATION | run 36058864740 on `fc6ed43`: lint, unit, 4 distro jobs — all green |

No FAIL verdicts. Every v2.5 feature is in `docs/FEATURE_MATRIX.md` (keep / replace / fix / N-A); nothing was dropped silently.

## Known risks before the first native run

1. **Mutter D-Bus API** is implemented from the interface description and tested only against a fake. `arcon plan` uses Mutter's *verify* method — it cannot change the screens — so run `plan` first and check the Display rows.
2. **NVIDIA:** the open-module decision uses the PCI device id (≥ 0x1E00 = Turing+). Check `arcon doctor` shows "open modules ok" for your card before enabling gaming.
3. **AUR as root** fails by design (makepkg); run ArCoN as your user.
4. **Catalog on Arch** is verified only in the `archlinux:latest` container (CI run 36058864740). Its 7 MISSING are `lib32-*` + `steam`: the image has multilib disabled (the gaming module enables it). Run `python3 scripts/verify_catalog.py` once on your machine (your mirrors and multilib state).
5. **`setup.sh` on Arch** (uv from pacman) has never run — the first `./setup.sh doctor` is its first test.

## Native checklist (owner's Arch machine, NVIDIA, GNOME)

Run from the GNOME session, as your user (not root, not `sudo`), in the repo. About 15 min for the read-only part; 30–60 min for `apply` (downloads + AUR builds).

```bash
# A. read-only — nothing changes
dconf dump / > ~/dconf-before-arcon.ini              # extra insurance, independent of ArCoN
./setup.sh doctor                                    # installs uv via pacman on first run (sudo); GPU nvidia …(open modules ok)? kernels? snapshot tool?
python3 scripts/verify_catalog.py > /tmp/catalog.md  # MISSING lib32-* / steam = multilib off (expected); anything else: report
./setup.sh display show                              # 2–3 monitors, current vs best mode
./setup.sh display capture --profile profiles/mrfedai.toml   # saves your layout; check with: git diff profiles/mrfedai.toml
./setup.sh --profile profiles/mrfedai.toml plan      # read the whole plan; nothing changes

# B. apply
./setup.sh --profile profiles/mrfedai.toml apply     # one confirmation; sudo password; AUR PKGBUILD review prompts
./setup.sh --profile profiles/mrfedai.toml apply     # must say "Nothing to do"
./setup.sh runs                                      # and, if needed: ./setup.sh rollback (files only, not packages — D6)
```

In the plan, check:
- **Display rows** — they come from Mutter's *verify* method (risk 1); identity, best mode and your layout must match `display show`.
- **`cleanup.orphans`** — the list of packages to remove. Keep one with `sudo pacman -D --asexplicit <pkg>`, or set `orphans = false` in the profile.
- **Files to change** — only the dconf load from `gno.conf`, the Terminator config and `.zshrc`.
- **Recovery** — with Snapper/Timeshift (shown by `doctor`) ArCoN takes a snapshot first; without one there are per-file backups only, packages are not covered.

After `apply`, log out and back in: dark theme, Terminator colours/fonts, keybindings, black wallpaper, zsh + agnoster.

Not covered by this run: `gaming = false` in `profiles/mrfedai.toml`, so the NVIDIA driver path is only exercised by `doctor` (detection), not installed.

Report back: `arcon runs`, both runs' `~/.local/state/arcon/runs/<run_id>/journal.jsonl`, `/tmp/catalog.md`, the `doctor` output, and anything that looked wrong. Each passing item moves from UNIT/INTEGRATION to NATIVE TESTED in `docs/FEATURE_MATRIX.md`.
