# Migrating from ArCoN v2.5 to v3

v2.5 CLI compatibility is not provided (D7). This guide maps every v2.5 prompt to v3.

## What stays exactly the same

- **Your dotfiles.** `configs/gno.conf`, `configs/terminator/config`, `configs/hypr/*.conf` are deployed unchanged. The only substitutions (D18): your user name, the wallpaper keys (default: solid black), the generated monitor block in `hyprland.conf`, and the colour-file line in `hyprlock.conf` when Ax-Shell is absent. A test fails if anything else would change.
- Your dark theme, fonts, keybindings, app folders, Terminator colours.

## Running it

| v2.5 | v3 |
|---|---|
| `chmod +x setup.sh && ./setup.sh` | `./setup.sh` (same file name, now a bootstrap for `arcon`) |
| prompts during the whole install | all questions first (`arcon wizard`), then one confirmation |
| — | `arcon plan` (dry run), `arcon resume`, `arcon rollback`, `arcon runs` |
| `sudo ./setup.sh` | refused — run as your user |

## Prompt → profile key

| v2.5 prompt / menu | v3 profile |
|---|---|
| Main menu 1) install | `arcon` / `arcon apply` |
| Main menu 2) Smart Factory Reset | `arcon reset [--uninstall] [--gnome]` |
| Resume from last checkpoint | `arcon resume` (it works now) |
| Update Base System (Mirrors/Keyrings) | `[modules] system`, `[system] upgrade / mirrors / keyring_reset / speedtest` |
| Apply GNOME Settings | `[modules] gnome` |
| Remove GNOME Bloatware | `[gnome] debloat` |
| Enable Gaming Mode + GPU menu | `[modules] gaming`, `[gaming] gpu = "auto"` (detected) |
| Package module, 4 groups, pacs.txt | `[packages] groups`, `extra`, `custom_file` |
| BlackArch menu 1/2/3 | `[modules] blackarch`, `[blackarch] install = core / full / remove` |
| Install Hyprland Environment | `[modules] hyprland` |
| Hyprland theme menu (Ax-Shell, Hyprdots, ML4W, JaKooLit) | not in v3.0 (D24) — deferred to v3.1; "Skip Theme" = v3 behaviour |
| Restore Configs (Terminator, Wallpapers) | `[modules] dotfiles`; wallpapers: `[wallpaper]` |
| Terminal emulator + theme | `[terminal] emulator`, `theme` |
| Shell + theme | `[shell] name`, `zsh_theme`, `starship_preset` |
| Security & Optimizations | `[modules] security` + `[security] …` (all opt-in), `[modules] optimization` + `[optimization] items` |
| Start Security Scans | `[security] scans` |
| Apply All Hardening Fixes | `[security] sysctl`, `firewall`, `ssh_root_login`, `ssh_disable_password` |
| Activate Hardened Mode | `[security] opensnitch`, `usbguard` (no longer tied to the hardening prompt) |
| Remove leftovers | `[modules] cleanup`, `[cleanup] orphans`, `cache` |
| Reboot system now | asked at the end only when a change needs it |

## Behaviour that changed on purpose

| v2.5 | v3 | Why |
|---|---|---|
| deleted `/etc/pacman.d/gnupg` and the sync DB on every run | normal keyring update; reset only with `keyring_reset = true` | destructive without need (AUDIT #10) |
| `pacman -Scc` | `paccache -rk2`; `cache = "purge"` restores the old behaviour | keeps a downgrade path for rollback |
| gaming only after GNOME settings | independent | D12 |
| GPU chosen from a menu | detected (NVIDIA open modules on Turing+, DKMS for extra kernels, PRIME on hybrids) | F19 |
| one `pacman -S` per package | one transaction | speed, consistent dependency resolution |
| unknown package → yay | reported as unavailable | typos were built from the AUR |
| `curl \| sh` (Oh-My-Zsh, Starship) | pinned `git` commits / distro packages | S-03 |
| BlackArch `--overwrite '*'`, wrong key | no overwrite; strap.sh SHA-256 shown + typed confirmation | S-01, S-02, S-05 |
| SSH: `sed` on sshd_config | drop-in in `sshd_config.d`, validated with `sshd -t` | S-06 |
| UFW enabled before allowing SSH | SSH allowed first | remote lock-out |
| factory reset deleted `~/.config/<every package>` incl. browser/editor data | explicit list; configs of protected packages and user data kept | D19 |
| Alacritty theme overwrote `alacritty.toml`; 404 pages saved as config | theme imported; `curl -f` | AUDIT #8 |
| GameMode config in `~/.config/gamemode/gamemode.ini` | `~/.config/gamemode.ini` (where GameMode reads it) | D-08 |
| "Internet OK" without checking; live-USB check commented out | both checked | F02, F05 |

## Packages

Groups were reorganised (D28): `base` (always), `essentials`, `media`, `cyber`, `remote`, `privacy`, `power`. Removed: x11vnc, stacer, stirling-pdf, pinokio, flameshot, switcheroo. Full table: [PACKAGE_REVIEW.md](PACKAGE_REVIEW.md).
On Debian/Ubuntu/Fedora, packages the distro does not ship fall back to Flathub (D22) or are listed as unavailable.

## Wallpapers

`wallp/` is no longer in the repository (D25). The default is a solid black background. To use an image: `[wallpaper] mode = "file"`, `file = "/path/to/image.jpg"`.
