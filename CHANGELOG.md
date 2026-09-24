# Changelog

## 3.0.0 — unreleased (branch `v3-dev`)

Complete rewrite of the 1885-line v2.5 Bash script in Python 3.11+ (`arcon`). v2.5 stays in `legacy/v2.5/` and at tag `v2.5.0`.

### New
- One profile (TOML) instead of ~40 prompts during the install; wizard asks everything first, then **one** confirmation.
- `arcon plan` (dry run), `resume`, `rollback`, `runs`, `doctor`, `display show|capture`, `dotfiles diff|capture`, `profile init|show|validate`, `reset`.
- JSON-lines journal for every run; verified per-file backups; GNOME settings backed up with `dconf dump`; Snapper/Timeshift snapshot when configured.
- Monitors: best mode per monitor detected, owner's layout kept, fallback when a mode does not work (GNOME via Mutter, Hyprland generated block).
- GPU detection (NVIDIA open modules / DKMS + headers / PRIME, AMD, Intel) — no more GPU menu.
- Debian, Ubuntu and Fedora support through a per-distro package catalog with Flatpak fallback.
- Package groups reorganised: base, essentials, media, cyber, remote, privacy, power.
- One-line install: `git clone https://github.com/MrFedai/ArCoN-v3.git ~/ArCoN-v3 && ~/ArCoN-v3/setup.sh`; on Debian/Ubuntu `setup.sh` installs `python3-venv` itself when it is missing.

### Fixed (v2.5 bugs)
- Resume never worked (log was never written).
- "Internet OK" printed without a check; live-USB check commented out; stray `END` command.
- Firejail step never ran; UFW and ZRAM configured without being installed.
- Alacritty/Kitty theme downloads saved 404 pages as config and overwrote `alacritty.toml`.
- Gaming only offered after GNOME settings; GameMode config written where GameMode never reads it.
- Every run deleted the pacman keyring and sync DB; `pacman -Scc` removed the downgrade path.
- Unknown package names were sent to yay; one `pacman -S` per package.
- Factory reset deleted `~/.config/<package>` for every package (incl. browser/editor data) and ignored the protected list.
- `curl | sh` installers, BlackArch without checksum and with `--overwrite '*'`, SSH edited with `sed` and no validation, UFW enabled before allowing SSH, `/etc/os-release` sourced.
- Final summary printed success unconditionally.

### Removed
- Third-party Hyprland theme installers (Ax-Shell, Hyprdots/HyDE, ML4W, JaKooLit) — deferred to v3.1.
- `wallp/` (licensing) — optional private wallpaper repository; default background is solid black.
- Packages: x11vnc, stacer, stirling-pdf, pinokio, flameshot, switcheroo.

### Unchanged on purpose
- Your dotfiles (`configs/`) — deployed byte-identical except the documented D18 substitutions.
