"""Filesystem snapshots (D6): used when available, never installed or configured
silently. Detection is read-only; creating a snapshot is a mutating command."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from arcon.core.runner import Runner


@dataclass(frozen=True)
class SnapshotProvider:
    name: str
    create_argv: tuple[str, ...]

    def create(self, runner: Runner, description: str) -> bool:
        argv = [a.replace("{desc}", description) for a in self.create_argv]
        return runner.run(argv, sudo=True, check=False).ok


SNAPPER = SnapshotProvider("snapper", ("snapper", "-c", "root", "create", "--type", "single",
                                        "--cleanup-algorithm", "number", "--description", "{desc}"))
TIMESHIFT = SnapshotProvider("timeshift", ("timeshift", "--create", "--comments", "{desc}", "--scripted"))


def detect(runner: Runner, which=shutil.which) -> SnapshotProvider | None:
    """Snapper with a `root` config first (Btrfs), then Timeshift with an existing setup."""
    if which("snapper"):
        res = runner.run(["snapper", "-c", "root", "list", "--columns", "number"],
                         sudo=True, mutating=False, check=False, timeout=30)
        if res.ok:
            return SNAPPER
    if which("timeshift"):
        res = runner.run(["timeshift", "--list"], sudo=True, mutating=False, check=False, timeout=60)
        if res.ok and "not configured" not in (res.stdout + res.stderr).lower():
            return TIMESHIFT
    return None
