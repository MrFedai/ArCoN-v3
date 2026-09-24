# v2.5 package group review (owner request, 2026-09-24)

Source: `tests/golden/v25/packages.json` (76 packages in 5 groups, no exact duplicates).
The problems are **overlaps** (several tools for one job), **misplaced** packages, and
packages that **do not fit the owner's setup** (GNOME on Wayland, Arch, NVIDIA).

## Findings

| # | Finding | Packages |
|---|---|---|
| 1 | ArCoN's own prerequisites mixed into "Essentials" | `git`, `curl`, `wget` (also in PROTECTED), `unzip`, `zip`, `man-db`, `man-pages`, `ntfs-3g`, `dosfstools` |
| 2 | Two editors of the same family | `vim` + `neovim` (both also PROTECTED) |
| 3 | Three browsers in three groups | `google-chrome` (Essentials), `firefox` (Media), `torbrowser-launcher` (Remote) |
| 4 | VPN / privacy spread over three groups | `riseup-vpn` (Essentials); `openvpn`, `networkmanager-openvpn`, `wireguard-tools`, `proton-vpn-gtk-app`, `torbrowser-launcher` (Remote); `onionshare`, `metadata-cleaner` (Power) |
| 5 | Remote-desktop clients in the Cyber group | `remmina`, `freerdp` (Cyber) vs `anydesk-bin`, `rustdesk-bin` (Remote) |
| 6 | X11-only tool on a Wayland desktop | `x11vnc` — does not share a GNOME Wayland session (GNOME has built-in Remote Desktop/RDP) |
| 7 | Screenshot tool duplicated by GNOME | `flameshot` — gno.conf already binds `<Alt>t` to GNOME's screenshot UI; Flameshot on Wayland needs extra portal setup |
| 8 | System cleaners/optimizers overlapping with ArCoN's optimization module | `stacer`, `bleachbit`, `ananicy-cpp` (ArCoN enables ananicy itself) |
| 9 | Two batch image converters | `switcheroo` + `converseen` |
| 10 | Server / heavyweight apps, not desktop utilities | `stirling-pdf` (self-hosted web service), `pinokio` (AI app launcher, large downloads) |
| 11 | Cyber group overlaps the BlackArch module | all 16 cyber tools exist in BlackArch groups; selecting both installs them twice-resolved but slows planning |
| 12 | `timeshift` in Essentials but it is ArCoN's rollback dependency (D6) | move to recovery |

Maintenance status of `stacer` (upstream activity) is NOT verified here — check before release.

## Proposed structure (superseded by the Decision below — vim and bleachbit were kept)

| Group | Content | Default for owner |
|---|---|---|
| `base` (always, not a choice) | git curl wget unzip zip man-db man-pages ntfs-3g dosfstools | always |
| `essentials` | neovim, code, google-chrome **or** firefox, telegram-desktop, localsend, vlc, btop, fastfetch, planify | on |
| `media` | libreoffice-fresh, gimp, inkscape, blender, kdenlive, losslesscut, obs-studio, audacity, easyeffects, spotify, shortwave, discord, obsidian, upscayl | on |
| `cyber` | nmap, masscan, wireshark-qt, aircrack-ng, metasploit, exploitdb, burpsuite, gobuster, sqlmap, nikto, hydra, john, hashcat, ghidra, radare2, bettercap — skipped automatically when BlackArch full is selected | on |
| `remote` | anydesk, rustdesk, remmina, freerdp | off |
| `privacy` (new, from Remote + Power + Essentials) | wireguard-tools, openvpn, networkmanager-openvpn, proton-vpn-gtk-app, riseup-vpn, torbrowser-launcher, onionshare, metadata-cleaner | off |
| `power` | virt-manager, qemu-desktop, devtoys, clapgrep, converseen, bleachbit | off |
| recovery module | timeshift | with rollback |
| removed | x11vnc, stacer, stirling-pdf, pinokio, flameshot, vim (kept only as PROTECTED, not installed), switcheroo | — |

## Decision (owner, 2026-09-24) — CLAUDE.md D28

Structure approved. Removal list left to ArCoN for the first four; owner chose flameshot and switcheroo.

| Group | Packages | Count |
|---|---|---|
| `base` (always) | git curl wget unzip zip man-db man-pages ntfs-3g dosfstools | 9 |
| `essentials` | vim neovim code google-chrome firefox telegram-desktop localsend vlc btop fastfetch planify | 11 |
| `media` | libreoffice-fresh gimp inkscape blender kdenlive losslesscut obs-studio audacity easyeffects spotify shortwave discord obsidian upscayl | 14 |
| `cyber` | nmap masscan wireshark-qt aircrack-ng metasploit exploitdb burpsuite gobuster sqlmap nikto hydra john hashcat ghidra radare2 bettercap | 16 |
| `remote` | anydesk rustdesk remmina freerdp | 4 |
| `privacy` | wireguard-tools openvpn networkmanager-openvpn proton-vpn-gtk-app riseup-vpn torbrowser-launcher onionshare metadata-cleaner | 8 |
| `power` | virt-manager qemu-desktop devtoys clapgrep converseen bleachbit | 6 |
| recovery module | timeshift | 1 |
| optimization module | ananicy-cpp | 1 |
| **removed** | x11vnc (X11-only, owner runs Wayland), stacer (overlaps btop/bleachbit/optimization), stirling-pdf (web service, not a desktop app), pinokio (niche, heavy), flameshot (owner), switcheroo (owner) | 6 |

70 kept + 6 removed = 76 v2.5 packages; nothing dropped silently. Names above are logical ids; per-distro names are mapped in Phase 4 (AUR `-bin` variants on Arch).

