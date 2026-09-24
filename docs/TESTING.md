# Testing

Run everything: `uv run pytest` (Python ≥ 3.11). Labels follow CLAUDE.md rule 3.

| Suite | What it proves | Needs | Label |
|---|---|---|---|
| `tests/test_dotfiles_golden.py` | owner dotfiles unchanged (sha256 manifest), owner settings present, v3 golden files obey D18, D18 checker rejects forbidden edits | Python | UNIT TESTED |
| same, `@pytest.mark.dconf` | v2.5 and v3 `gno.conf` load into a real, throw-away dconf database and read back the owner settings + black wallpaper | `dconf`, `dbus-run-session` | INTEGRATION TESTED (container) |
| `tests/characterization/` | what ArCoN **v2.5** does: package lists, commands issued, files written, exact dconf input — bugs included | bash, git; Arch scenarios need root + `unshare` | INTEGRATION TESTED (container, mocked tools) |

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
