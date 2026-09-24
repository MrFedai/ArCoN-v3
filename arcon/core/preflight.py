"""Checks before anything changes (F01–F05, F14). Read-only except the
pacman-lock removal, which is asked for explicitly."""

from __future__ import annotations

import os
import shutil
import socket
import time
from pathlib import Path

from arcon.core.runner import Runner
from arcon.core.ui import UI
from arcon.platform.detect import Family, OSInfo

MIN_FREE_GB = 10
NET_HOSTS = ("archlinux.org", "deb.debian.org", "github.com")


def online(hosts=NET_HOSTS, timeout: float = 5.0) -> bool:
    for host in hosts:
        try:
            with socket.create_connection((host, 443), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def live_environment(root: Path = Path("/")) -> bool:
    """Running from a live ISO (v2.5 had this check commented out)."""
    if (root / "run" / "archiso").exists() or (root / "run" / "live").exists():
        return True
    for line in (root / "proc" / "mounts").read_text().splitlines() if (root / "proc" / "mounts").exists() else []:
        parts = line.split()
        if len(parts) > 2 and parts[1] == "/" and parts[2] in ("overlay", "tmpfs", "squashfs", "aufs"):
            return True
    return False


def pacman_running(runner: Runner) -> bool:
    return runner.run(["pgrep", "-x", "pacman"], mutating=False, check=False).ok


def run(os_info: OSInfo, runner: Runner, ui: UI, needs_network: bool, dry_run: bool,
        root: Path = Path("/"), speedtest: bool = False) -> bool:
    ok = True
    free_gb = shutil.disk_usage(root).free / 1024 ** 3
    if free_gb < MIN_FREE_GB:
        ui.error(f"only {free_gb:.1f} GiB free on / (need {MIN_FREE_GB})")
        ok = False
    if needs_network and not online():
        ui.error("no network connection (checked " + ", ".join(NET_HOSTS) + ")")
        ok = False
    if live_environment(root):
        ui.warn("this looks like a live/ISO system: changes are lost at reboot")
        if not dry_run and not ui.confirm("Continue anyway?", default=False):
            ok = False
    if os_info.family is Family.ARCH:
        lock = root / "var" / "lib" / "pacman" / "db.lck"
        if lock.exists():
            if pacman_running(runner):
                ui.error("pacman is running in another process — finish it first")
                ok = False
            elif not dry_run and ui.confirm(f"Stale pacman lock {lock} (no pacman running). Remove it?", default=False):
                runner.run(["rm", "-f", str(lock)], sudo=True)
            elif not dry_run:
                ok = False
    if not dry_run and os.environ.get("ARCON_SKIP_SUDO_CHECK") != "1":
        if not runner.run(["sudo", "-v"], check=False, interactive=True).ok:
            ui.error("sudo is required for system changes")
            ok = False
    if speedtest:
        ui.info(f"download speed: {measure_speed(runner)}")
    return ok


def measure_speed(runner: Runner) -> str:
    start = time.monotonic()
    res = runner.run(["curl", "-s", "-o", "/dev/null", "-w", "%{speed_download}", "--max-time", "8",
                      "https://speed.cloudflare.com/__down?bytes=10000000"], mutating=False, check=False)
    try:
        return f"{float(res.stdout) / 1024:.0f} KiB/s"
    except ValueError:
        return f"unknown ({time.monotonic() - start:.0f}s, no result)"
