# ArCoN v3 — progress log

One entry per phase (CLAUDE.md, continuous mode). Format: done · evidence · NOT tested · risks · deviations · questions.

## Phase 1 — audit (2026-09-24) · commit `a361fa7`

- **Done:** `docs/AUDIT.md`, `docs/FEATURE_MATRIX.md`, CLAUDE.md, prior audit verified (16/17 confirmed).
- **Evidence:** `bash -n` OK; ShellCheck 0.9.0 52 findings; theme/installer URLs checked (HTTP codes in AUDIT §7); `v3.0` bats unit suite 68/68.
- **NOT tested:** BlackArch key fingerprint (site unreachable).
- **Deviations:** tag `v2.5-final` not created (`v2.5.0` already on the same commit).

## Phase 2 — characterization & golden files · commit `6a98f18`

- **Done:** recording mocks + harness running `setup.sh` from tag `v2.5.0` (Debian, Arch via mount namespace); golden snapshots; owner settings + source hash manifest; v3 golden `gno.conf` (solid black) / `hyprlock.conf`; D18 checker.
- **Evidence:** 47 tests passed; mutation check (`prefer-dark` → `default`) fails 5 tests; v3 `gno.conf` loaded into a real dconf DB and read back.
- **NOT tested:** real GNOME session, real installs.

## Decisions — commit `bea45ca`

D20–D28 recorded (Arch dual-boot + NVIDIA, English + rich CLI, Flatpak fallback, security all opt-in, Hyprland = own config only, wallpapers → private repo, owner profile, release plan, package groups).

## Phase 3 — core skeleton

- **Done:**
  - `arcon/core/runner.py` — single command gate: `SystemRunner`, `DryRunRunner` (probes run, mutations recorded), `FakeRunner`; sudo prefix, timeouts, 127 for missing commands.
  - `arcon/platform/detect.py` — os-release parsed (never sourced), family + tier (supported / experimental derivative / stub / unsupported).
  - `arcon/core/profile.py` — TOML profile, strict schema (unknown keys and bad values are errors), `tomlkit` keeps comments; `profiles/mrfedai.toml` (D26).
  - `arcon/recovery/` — JSONL journal (fsync per event, torn last line tolerated), verified per-file backup + atomic write + rollback, Snapper/Timeshift detection.
  - `arcon/core/engine.py` — plan → show (risk, reversibility, ONE-WAY/HIGH warnings) → execute → verify → report from real statuses; resume skips done actions; `requires`; `--keep-going`.
  - `arcon/core/wizard.py` — all questions up front, conditional follow-ups, "reuse previous answers".
  - `arcon/cli.py` — `arcon`, `plan`, `apply`, `wizard`, `resume`, `rollback`, `runs`, `profile`, `doctor`; refuses root for mutating commands (D15); refuses Windows/macOS (stub, exit 3) and unknown distros.
  - `setup.sh` is now the thin bootstrap (uv from distro package or a private venv — no `curl | sh`); v2.5 moved unchanged to `legacy/v2.5/`. `setup.ps1` = Windows stub.
- **Evidence:** `uv run pytest` → 82 passed (35 new unit tests); `arcon doctor`, `arcon --profile profiles/mrfedai.toml plan` run in the Ubuntu container; ShellCheck clean on `setup.sh`.
- **Bug found by tests and fixed:** run ids collided within one second → now microseconds + random suffix.
- **NOT tested:** snapshot creation (no Snapper/Timeshift here); root-owned file writes only with FakeRunner; `setup.sh` uv installation path (uv already present).
- **Risks:** no feature modules yet — `arcon plan` reports "nothing to do" until Phase 4/5.
- **Deviations:** none.

## Phase 4 — hardware, display, packages

- **Done:**
  - `arcon/hardware/linux.py` — GPUs from sysfs (vendor, PCI device id, boot VGA, hybrid), NVIDIA open-module capability (device id ≥ 0x1E00 = Turing+), RAM, root disk SSD/HDD, battery, installed kernel flavours (`/usr/lib/modules/*/pkgbase`), virtualization.
  - `arcon/display/` — monitor model, D13 mode ranking (resolution-first / refresh-first), layout that keeps order/y/scale and recomputes x so neighbours touch; GNOME backend over Mutter `org.gnome.Mutter.DisplayConfig` (jeepney): dry run = Mutter **verify** method, real run = persistent, per-monitor fallback to the next mode when a mode does not become active; Hyprland backend (`hyprctl monitors all -j`, `highres`/`highrr` when Hyprland is not running) and the D18 generated monitor block. `arcon display show|capture` (capture writes the current layout into the profile).
  - `arcon/data/packages.toml` — 126 logical packages (D28 groups + internal groups), explicit `aur:` markers; `scripts/verify_catalog.py`; `docs/PACKAGE_CATALOG.md`.
  - `arcon/package/` — pacman, AUR helper (yay/paru, as user), apt (Debian+Ubuntu), dnf, Flatpak; one transaction per source; resolution native → AUR (Arch) → Flatpak (D22) → reported as unavailable. User extras that exist nowhere are reported, never sent to yay (v2.5 bug #15). `packages` module: native, AUR helper bootstrap (yay-bin via makepkg in a temp dir), AUR, Flathub, Flatpak actions.
  - `tests/golden/v3/hyprland.conf` (deferred from Phase 2) — obeys D18.
- **Evidence:** `uv run pytest` → 105 passed (23 new). Ubuntu 24.04 container: `verify_catalog.py` 81 ok / 7 missing (handled at runtime); `arcon --profile profiles/mrfedai.toml plan` resolved against the real apt index (28 repo packages, Flatpak fallback for 11, 5 reported unavailable).
- **NOT tested:** real Mutter D-Bus (no GNOME session here) — the GNOME backend is UNIT TESTED against a fake Mutter only; Hyprland `desc:` matching on real Hyprland; Arch/Debian/Fedora package queries (CI, Phase 7); Flathub ids (flathub.org unreachable); AUR helper build.
- **Risks:** Mutter's API details (`ApplyMonitorsConfig` signature, variant layout) are implemented from the documented interface, not exercised against a live session — first native run must use `arcon plan` (verify method) before `apply`. NVIDIA "open capable" threshold is a PCI id heuristic.
- **Deviations:** none.
- **Intentional fix (N-06):** the Hyprland group no longer installs dolphin — the v2.5 config uses nautilus, which GNOME already provides.

## Phase 5 — feature migration

- **Done (one module per v2.5 sector, all registered explicitly in `arcon/modules.py`):**
  - `system` — full upgrade (Arch: keyring first, then `-Su`; never `-Sy` alone), opt-in reflector with mirrorlist backup, opt-in keyring reset (v2.5 behaviour, HIGH), multilib enabled only for gaming, followed by `-Syu`.
  - `gnome` — gno.conf rendered with D18 (user + wallpaper; default solid black), plan lists only the dconf keys that differ, full `dconf dump /` backup, verification of the owner keys, rollback via the dump; exact-name debloat.
  - `gaming` — GPU packages from detection: NVIDIA open modules (`nvidia-open` on the stock kernel, `-dkms` + headers for every other kernel, `nvidia-prime` on hybrid), pre-Turing NVIDIA reported (not automated), Ubuntu `ubuntu-drivers`, Debian/Fedora reported (no repo changes); GameMode config at the path GameMode reads (D-08), gamemode group.
  - `dotfiles` — deploy (D18-checked before writing), `arcon dotfiles diff|capture`; capture never brings generated parts (monitor block, arcon-colors source) into the repo.
  - `hyprland` — packages + ArCoN's config only (D24), monitor block from detection.
  - `terminal` / `shell` — Kitty themes via kitty's own kitten (config backed up), Alacritty themes imported (config never overwritten, `curl -f`), Oh-My-Zsh + plugins from pinned commits (no `curl | sh`), `.zshrc` edits only ZSH_THEME/plugins, Starship presets, chsh checked against /etc/shells with the real login shell (getent).
  - `security` (all opt-in, D23) — tools, sysctl drop-in, ufw/firewalld (SSH allowed before enabling; "inactive" ≠ active), SSH drop-in validated with `sshd -t` and removed again if invalid, USBGuard + SSH key-only behind typed confirmations, scans with reports in the run dir, OpenSnitch. BlackArch: strap.sh SHA-256 shown + typed confirmation (ONE-WAY), no `--overwrite`, removal restores pacman.conf.
  - `optimization` / `cleanup` — TRIM only on SSD, Bluetooth only with an adapter, ZRAM only when none exists, ananicy-cpp; orphans listed, `paccache -rk2` by default (purge = v2.5 `-Scc`, opt-in).
  - `arcon reset` (D19) — explicit paths, protected packages' configs kept, user data (browser/editor/chat profiles) never touched, directory backups + dconf dump, typed `CLEAN`.
  - Preflight — disk, network, live ISO, stale pacman lock (asked, never silent), sudo, optional speed test; reboot prompt only when an action needs it.
  - `wallp/` removed from the repo (D25; still in `v2.5.0`).
- **Evidence:**
  - `uv run pytest` → 130 passed, 1 skipped (the real-run test, opt-in).
  - **Real run** (`ARCON_REAL_RUN=1`, Ubuntu 24.04 container, `dbus-run-session`): `arcon apply` installed packages via apt, loaded gno.conf into a real dconf database (read back `'prefer-dark'`, picture-options `'none'`), deployed the Terminator config byte-identical, cloned Oh-My-Zsh at the pinned commit, changed the login shell; a second `apply` printed "Nothing to do"; `arcon rollback` removed the deployed files and restored dconf.
  - Dry run with `profiles/mrfedai.toml` leaves `$HOME` untouched (checked).
- **Bugs found and fixed while testing:** `$USER` unset crashed chsh/gamemode (now getent/getpass); dry run created `~/.oh-my-zsh/custom/plugins`; a broken third-party apt source aborted every install (now a warning); chsh was re-planned every run because `$SHELL` is not the login shell.
- **NOT tested:** Arch/Debian/Fedora real runs (CI Phase 7 = containers only), NVIDIA driver install, multilib, reflector, BlackArch, USBGuard, OpenSnitch, scans, firewall on a real host, Mutter display changes, Hyprland — all UNIT at most.
- **Deviations:** none.

## Phase 6 — CLI polish and migration guide

- **Done:** global options accepted before or after the command; help epilog with examples; `arcon profile init` (documented template, never overwrites); README rewritten for v3 with an honest platform table; `docs/MIGRATION.md` (every v2.5 prompt → profile key/command, every intentional behaviour change with its reason); v2.5 README kept in `legacy/v2.5/`.
- **Evidence:** 132 passed; template test checks every schema key/default; `arcon profile init` + `validate` run.
- **NOT tested:** —
- **Deviations:** none.

## Phase 7 — CI and test-status report

- **Done:** `.github/workflows/ci.yml` — lint (ShellCheck, compileall), unit (pytest as user + characterization as root for the Arch scenarios), distro matrix (archlinux, debian:stable, ubuntu:24.04, fedora): catalog verification per distro (artifact), dry run of the owner profile, real apply + rollback. The real-run test is distro-neutral now (package check through the provider; on Arch as root only the two AUR actions may fail — makepkg refuses root). `docs/TESTING.md`: level-by-level status.
- **Evidence:** workflow parses (PyYAML), ShellCheck/compileall clean locally, 132 passed; real-run test passes again on Ubuntu 24.04 after the generalisation.
- **NOT tested:** the workflow itself has **not run** — it needs the branch on GitHub. Docker Hub is blocked in this environment, so no local container matrix either.
- **Deviations:** none.

## Phase 8 — documentation and final audit

- **Done:** `CHANGELOG.md`, `docs/FINAL_AUDIT.md` (verdict per area, known risks, native checklist), CLAUDE.md status.
- **Evidence:** see FINAL_AUDIT — no FAIL; PASS areas are backed by integration runs in the Ubuntu container.
- **NOT tested:** everything marked NOT TESTED / PARTIAL in FINAL_AUDIT; no VM or native run.
- **Deviations:** none. Release (D27: merge to main, tag v3.0.0, archive the Bash branch) is **not** done — it waits for push access, a green CI run and the native checklist.
