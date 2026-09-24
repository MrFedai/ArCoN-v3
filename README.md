# ArCoN v3

**Set up a Linux machine from one profile — packages, GNOME, monitors, shell, gaming, security — with a plan you see first, a journal of every change and a rollback.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Status](https://img.shields.io/badge/v3-development-orange)

ArCoN v3 is a rewrite of [ArCoN v2.5](legacy/v2.5/README.md) (a 1885-line Bash script) in Python.
Every v2.5 feature is kept, fixed or explicitly marked — see [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md).
Your dotfiles in `configs/` are deployed **unchanged** (only documented substitutions, CLAUDE.md D18).

## Quick start

```bash
git clone https://github.com/MrFedai/ArCoN.git && cd ArCoN
./setup.sh plan        # dry run: what would change — nothing is modified
./setup.sh             # wizard -> plan -> one confirmation -> apply
```

Run it as your normal user (not with `sudo`); ArCoN asks for sudo only for the commands that need it.
`setup.sh` only makes sure [uv](https://docs.astral.sh/uv/) exists (distro package or a private venv — never `curl | sh`) and starts `arcon`.

## How a run works

```
wizard (all questions up front) -> plan (every package, file, setting, service; risk; reversibility)
  -> one confirmation -> preflight (disk, network, live ISO, pacman lock, sudo) -> snapshot if Snapper/Timeshift
  -> apply + verify each action -> report from real results -> reboot prompt only if needed
```

- **Dry run** (`arcon plan`): read-only probes run, every change is only recorded. GNOME monitor changes are checked by Mutter itself ("verify" mode).
- **Journal**: `~/.local/state/arcon/runs/<run>/journal.jsonl` — drives `arcon resume` and `arcon rollback`.
- **Rollback**: files and GNOME settings are restored exactly; installed packages are listed, never "rolled back" silently.
- **Idempotent**: a second `arcon apply` prints "Nothing to do".

## Commands

| Command | What it does |
|---|---|
| `arcon` | wizard → plan → confirm → apply |
| `arcon plan` / `arcon apply` | dry run / apply the saved profile |
| `arcon wizard` | answer the questions, save the profile |
| `arcon resume` | continue an interrupted or failed run |
| `arcon rollback [RUN]` | restore files + dconf changed by a run |
| `arcon runs` | list runs |
| `arcon profile init\|show\|validate\|path` | documented profile template, effective values, checks |
| `arcon display show\|capture` | monitors, best modes; save the current layout into the profile |
| `arcon dotfiles diff\|capture` | compare deployed dotfiles with the repo; copy them back |
| `arcon reset [--uninstall] [--gnome]` | Smart Factory Reset (backup first, typed `CLEAN`) |
| `arcon doctor` | detected OS, GPU, disk, kernels, snapshot tool |

Global options work before or after the command: `--profile FILE`, `-n/--dry-run`, `-y/--yes` (never answers typed confirmations), `--keep-going`, `-v`.

## Profile

`arcon profile init` writes a template with every key documented ([arcon/data/profile.template.toml](arcon/data/profile.template.toml)).
Unknown keys and invalid values are errors. The owner's profile: [profiles/mrfedai.toml](profiles/mrfedai.toml).

## Platform status (honest)

| Platform | Status |
|---|---|
| Arch Linux | full scope; UNIT TESTED; container CI in `.github/workflows/ci.yml`; native test pending |
| Debian / Ubuntu | full scope (one provider); Ubuntu 24.04: real `apply` + `rollback` run in a container (packages, dconf, dotfiles, shell) |
| Fedora | full scope; UNIT TESTED; container CI |
| Derivatives (EndeavourOS, CachyOS, Mint, Nobara, …) | run as their parent family, marked *experimental* |
| Windows, macOS | interfaces only — ArCoN v3.0 changes nothing there |

Nothing has been run on real hardware yet (GPU drivers, monitors, Hyprland). See [docs/TESTING.md](docs/TESTING.md) and [docs/PROGRESS.md](docs/PROGRESS.md).

## Coming from v2.5

Read [docs/MIGRATION.md](docs/MIGRATION.md). The v2.5 script is kept unchanged in `legacy/v2.5/` and at tag `v2.5.0`.

## Development

```bash
uv run pytest                         # unit + characterization + golden tests
ARCON_REAL_RUN=1 uv run pytest tests/integration   # REAL installs — disposable container/VM only
python3 scripts/verify_catalog.py     # check the package catalog on the current distro
```

Project rules and decisions: [CLAUDE.md](CLAUDE.md). Audit of v2.5: [docs/AUDIT.md](docs/AUDIT.md).

## License

MIT — see [LICENSE](LICENSE). Hyprland/Oh-My-Zsh/Starship and the other tools ArCoN installs keep their own licences.
