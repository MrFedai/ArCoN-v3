# Testing

Run everything: `uv run pytest` (Python ≥ 3.11). Labels follow CLAUDE.md rule 3.

| Suite | What it proves | Needs | Label |
|---|---|---|---|
| `tests/test_dotfiles_golden.py` | owner dotfiles unchanged (sha256 manifest), owner settings present, v3 golden files obey D18, D18 checker rejects forbidden edits | Python | UNIT TESTED |
| same, `@pytest.mark.dconf` | v2.5 and v3 `gno.conf` load into a real, throw-away dconf database and read back the owner settings + black wallpaper | `dconf`, `dbus-run-session` | INTEGRATION TESTED (container) |
| `tests/characterization/` | what ArCoN **v2.5** does: package lists, commands issued, files written, exact dconf input — bugs included | bash, git; Arch scenarios need root + `unshare` | INTEGRATION TESTED (container, mocked tools) |
| `tests/unit/` | v3 core, detection, packages, display (fake Mutter), every feature module with `FakeRunner` | Python | UNIT TESTED |
| `tests/integration/test_real_run.py` | REAL `arcon apply` (packages, dconf, dotfiles, Oh-My-Zsh, chsh) → idempotent 2nd run → `arcon rollback` | `ARCON_REAL_RUN=1`, disposable container/VM, dbus, dconf, sudo | INTEGRATION TESTED (Ubuntu 24.04 container, run by hand) |

Nothing here validates a real GNOME session, real package installs, GPU, monitors or Hyprland: those are NOT TESTED until VM/native runs.

## Characterization harness

`tests/characterization/run_v25.sh <scenario> <outdir>` runs `setup.sh` **from tag `v2.5.0`** with:

- every side-effecting tool replaced by `mocks/_mock` (records `tool args`, never runs the real tool; stdin of `dconf load` / `sudo tee` is captured)
- `HOME`/`USER` inside `<outdir>`; answers from `scenarios/<name>.answers`
- `*-arch` scenarios: private mount namespace with `/etc/os-release` bind-mounted to `ID=arch`

Scenarios: `dotfiles-debian`, `dotfiles-arch` (GNOME + Hyprland default configs + terminal), `packages-arch` (all groups + pacs.txt).

Golden files: `tests/golden/v25/*.json`. Regenerate only deliberately: `python tests/characterization/snapshot.py --update`, then review the diff.

## Golden files for v3

| File | Rule |
|---|---|
| `tests/golden/sources.sha256` | repo dotfiles; change only with owner approval (later: `arcon capture`) |
| `tests/golden/owner_settings.json` | settings that must survive every version |
| `tests/golden/v3/gno.conf` | expected deploy for user `arcontest`, default black wallpaper |
| `tests/golden/v3/hyprlock.conf` | expected deploy without Ax-Shell |
| `arcon/dotfiles/rules.py` | D18 checker, used by the deploy/verify step and the tests |

`hyprland.conf` v3 golden is deferred to Phase 4 (depends on detected monitors).

## CI (`.github/workflows/ci.yml`)

| Job | Runs | Status |
|---|---|---|
| lint | ShellCheck, `compileall` | PASS (runs 35993001306, 36054621202) |
| unit | full pytest as user, characterization as root (Arch scenarios) | PASS in run 35993001306; run 36054621202 did not start: `astral-sh/setup-uv@v10` does not exist (setup-uv has no major tags since v8) — now pinned to `v10.2.0` |
| distro × {archlinux, debian:stable, ubuntu:24.04, fedora} | catalog verification per distro, dry run of `profiles/mrfedai.toml`, real apply + rollback | run 36054621202: **debian:stable and ubuntu:24.04 PASS** (incl. real apply + rollback); archlinux and fedora: catalog + dry run PASS, **real apply + rollback FAIL** — see below |

Expected on Arch in a root container: the AUR actions fail (makepkg refuses root) — the test allows exactly those two, also on the idempotency re-run (judged by the journal, not by console text).

**First CI run (35993001306) — real apply + rollback:**
- debian:stable, ubuntu:24.04 — cause found: the images have no `dconf-service` (`dconf-cli` does not pull it in), so every dconf write failed with `ServiceUnknown: ca.desrt.dconf`. A desktop always has it; the workflow now installs it — confirmed green in CI run 36054621202. Reproduced and fix verified in a fresh Ubuntu 24.04 minbase rootfs (debootstrap + chroot, the workflow's exact commands) — not in Docker (Docker Hub blocked here).
- archlinux, fedora — cause found from the `arcon-runs-0` / `arcon-runs-3` artifacts of run 36055367756: `shell.chsh` failed with `/usr/sbin/zsh is not listed in /etc/shells`. Both distros merged /usr/sbin into /usr/bin, so `which zsh` (root's PATH has sbin first) returns /usr/sbin/zsh — the same file as the listed /usr/bin/zsh. `ChangeShell` now picks the /etc/shells entry that points to the same file. Reproduced (same error) and fix verified on Ubuntu 24.04 with a merged-sbin symlink; unit test added. Run 36056633594 (with that fix): **archlinux PASS**; fedora got further and failed at `arcon rollback`: `dconf dump /` shows the merged view incl. Fedora's system database (authselect's locked `/org/gnome/login-screen/enable-*-authentication` keys), and loading that backup back failed with "non-writable keys". Backups/restores now use the user database only (`DCONF_PROFILE` = `user-db:user`). Reproduced (same error) and fix verified on Ubuntu 24.04 with a Fedora-like locked system dconf database plus merged sbin; unit test added. Real Fedora container: NOT TESTED until the next CI run. Also fixed earlier: the Arch-as-root idempotency check (console shows titles, not ids).

**One-line install** (`git clone … ~/ArCoN-v3 && ~/ArCoN-v3/setup.sh`): run as a normal sudo user on a fresh Ubuntu 24.04 minbase rootfs (debootstrap + chroot, no python3): `setup.sh` installed python3 + python3-venv, uv, and started `arcon` (`--version`, `doctor`, `plan` OK). Arch/Fedora path (uv from pacman/dnf): NOT TESTED.

## Test status by level (2026-09-24)

| Level | What actually ran |
|---|---|
| UNIT | 132 tests pass (`uv run pytest`; 1 opt-in real-run test skipped) |
| INTEGRATION (container) | characterization of v2.5 (Ubuntu + Arch via mount namespace, mocked tools); real apply/rollback on Ubuntu 24.04; real dconf load; catalog check on Ubuntu 24.04 |
| VM | none |
| NATIVE | none — first native run: the owner's Arch machine (see docs/FINAL_AUDIT.md, "native checklist") |
