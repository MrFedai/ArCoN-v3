"""Small reusable actions: services, root-owned files, user files."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from arcon.core.action import Action, Change, Context, Reversible, Risk


class EnableService(Action):
    reversible = Reversible.YES

    def __init__(self, id: str, unit: str, title: str = "", user: bool = False, when: Callable[[Context], bool] | None = None):
        self.id, self.unit, self.user, self.when = id, unit, user, when
        self.title = title or f"Enable {unit}"

    def _cmd(self, *args: str) -> list[str]:
        return ["systemctl", *(["--user"] if self.user else []), *args]

    def plan(self, ctx):
        if self.when and not self.when(ctx):
            return []
        enabled = ctx.runner.run(self._cmd("is-enabled", self.unit), mutating=False, check=False).stdout.strip()
        active = ctx.runner.run(self._cmd("is-active", self.unit), mutating=False, check=False).stdout.strip()
        if enabled == "enabled" and active == "active":
            return []
        return [Change("service", self.unit, "enable --now")]

    def apply(self, ctx):
        ctx.runner.run(self._cmd("enable", "--now", self.unit), sudo=not self.user)
        ctx.journal.write("service_enabled", unit=self.unit, user=self.user)

    def verify(self, ctx):
        return ctx.runner.run(self._cmd("is-enabled", self.unit), mutating=False, check=False).stdout.strip() == "enabled"


def read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


class WriteFile(Action):
    """Write one file with backup (FileChanger). `content` is computed lazily."""

    def __init__(self, id: str, title: str, path: Path, content: Callable[[Context], str], root: bool = False,
                 mode: int | None = None, risk: Risk = Risk.LOW, after: Callable[[Context], None] | None = None,
                 verify_fn: Callable[[Context], bool] | None = None, reboot: bool = False):
        self.id, self.title, self.path, self._content, self.root, self.mode = id, title, Path(path), content, root, mode
        self.risk, self._after, self._verify, self.reboot = risk, after, verify_fn, reboot
        self._rendered: str | None = None

    def content(self, ctx) -> str:
        if self._rendered is None:
            self._rendered = self._content(ctx)
        return self._rendered

    def plan(self, ctx):
        new = self.content(ctx)
        old = read_text(self.path)
        if old == new:
            return []
        return [Change("file", str(self.path), "create" if old is None else "update (backup kept)")]

    def apply(self, ctx):
        ctx.files.write(self.path, self.content(ctx).encode(), root=self.root, mode=self.mode)
        if self._after and not ctx.dry_run:
            self._after(ctx)

    def verify(self, ctx):
        if self._verify:
            return self._verify(ctx)
        return self.root or read_text(self.path) == self.content(ctx)
