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
- **Deviations:** none. Hyprland group installs nautilus' role via GNOME (the v2.5 config uses nautilus; v2.5 installed dolphin, N-06) — dolphin is no longer installed.
