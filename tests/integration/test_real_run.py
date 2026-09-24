"""REAL run of `arcon apply` + `arcon rollback` in a disposable container.

Installs packages and changes files for real — it only runs when
ARCON_REAL_RUN=1 (CI containers / throw-away VMs). GNOME settings go into a
private dconf database inside `dbus-run-session`.
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get("ARCON_REAL_RUN") != "1",
                                reason="set ARCON_REAL_RUN=1 in a disposable container to run")

PROFILE = """
[profile]
name = "realrun"
[modules]
system = false
packages = true
gnome = true
display = false
hyprland = false
dotfiles = true
terminal = false
shell = true
gaming = false
blackarch = false
security = false
optimization = false
cleanup = false
[packages]
groups = []
extra = ["tree"]
flatpak_fallback = false
[shell]
name = "zsh"
"""


def run(home: Path, *args: str, check=True) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_STATE_HOME=str(home / ".local" / "state"), ARCON_ALLOW_ROOT="1",
               ARCON_SKIP_SUDO_CHECK="1", USER="arcontest", SHELL="/bin/bash")
    script = " ".join(f"'{a}'" for a in args)
    proc = subprocess.run(["dbus-run-session", "--", "sh", "-c", script], env=env, cwd=REPO,
                          capture_output=True, text=True, timeout=3600)
    if check:
        assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    return proc


def test_apply_then_rollback(tmp_path):
    if subprocess.run(["id", "arcontest"], capture_output=True).returncode != 0:
        subprocess.run(["useradd", "-M", "-s", "/bin/bash", "arcontest"], check=True)
    home = tmp_path / "home"
    home.mkdir()
    profile = tmp_path / "profile.toml"
    profile.write_text(PROFILE)
    arcon = [shutil.which("uv"), "run", "--quiet", "--project", str(REPO), "arcon", "--profile", str(profile), "-y",
             "--keep-going"]

    apply = run(home, *arcon, "apply", check=False)
    # dconf values must be read inside the same kind of session: they persist in ~/.config/dconf/user
    got = run(home, "sh", "-c", "dconf read /org/gnome/desktop/interface/color-scheme; "
                                "dconf read /org/gnome/desktop/background/picture-options").stdout.split()
    assert got == ["'prefer-dark'", "'none'"], apply.stdout[-3000:]

    term = home / ".config" / "terminator" / "config"
    assert term.read_bytes() == (REPO / "configs" / "terminator" / "config").read_bytes()
    head = subprocess.run(["git", "-C", str(home / ".oh-my-zsh"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == "74965c96098134b192f00084f966b4b02438a739"
    assert 'ZSH_THEME="agnoster"' in (home / ".zshrc").read_text()
    from arcon.core.runner import SystemRunner
    from arcon.package.providers import native_for
    from arcon.platform.detect import Family, detect
    os_info = detect()
    assert native_for(os_info, SystemRunner()).installed(["tree"]) == {"tree"}
    assert subprocess.run(["getent", "passwd", "arcontest"], capture_output=True, text=True).stdout.strip().endswith("/zsh")

    runs = sorted(p for p in (home / ".local" / "state" / "arcon" / "runs").iterdir() if p.is_dir())
    events = [json.loads(l) for l in (runs[-1] / "journal.jsonl").read_text().splitlines()]
    # makepkg refuses to run as root: in a root container the AUR part cannot work (expected)
    allowed = {"packages.aur-helper", "packages.aur"} if os.geteuid() == 0 else set()
    failed = [e for e in events if e.get("status") == "failed" and e["id"] not in allowed]
    assert not failed, failed

    # second run: idempotent — nothing left to do. The console shows action
    # titles, not ids, so an Arch-as-root run (AUR actions stay pending, see
    # above) is judged by its journal: only the allowed actions may run again.
    again = run(home, *arcon, "apply", check=False)
    if "Nothing to do" not in again.stdout:
        newest = max(p for p in (home / ".local" / "state" / "arcon" / "runs").iterdir() if p.is_dir())
        rerun = {e["id"] for e in map(json.loads, (newest / "journal.jsonl").read_text().splitlines())
                 if e.get("event") == "action" and e.get("status") in ("started", "done", "failed")}
        assert newest != runs[-1] and rerun and rerun <= allowed, (sorted(rerun), again.stdout[-3000:])

    run(home, *arcon, "rollback", runs[-1].name)
    assert not term.exists() and not (home / ".zshrc").exists()
    reset = run(home, "sh", "-c", "dconf read /org/gnome/desktop/interface/color-scheme").stdout.strip()
    assert reset == ""       # back to the default (the key was unset before)
