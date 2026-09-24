"""Dotfile manager (D10): deploy / diff / capture. Files stay in their native
format; only the D18 substitutions are applied (checked by rules.check)."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from arcon.core.action import Change, Context, Reversible, Risk, register
from arcon.core.common import WriteFile, read_text
from arcon.dotfiles import rules


@dataclass(frozen=True)
class Dotfile:
    name: str
    source: str               # relative to the repo root
    target: str               # relative to $HOME
    kind: str                 # rules.check kind
    module: str               # which profile module deploys it
    render: Callable[[Context, str], str] = lambda ctx, text: text


def _render_hyprland(ctx: Context, text: str) -> str:
    from arcon.display.actions import hyprland_block
    from arcon.display.hyprland import replace_monitor_lines
    return replace_monitor_lines(text, hyprland_block(ctx))


def _render_hyprlock(ctx: Context, text: str) -> str:
    if (ctx.home / ".config" / "Ax-Shell").exists():
        return text
    return text.replace(rules.AXSHELL_SOURCE, rules.ARCON_SOURCE, 1)


DOTFILES = (
    Dotfile("terminator", "configs/terminator/config", ".config/terminator/config", "verbatim", "dotfiles"),
    Dotfile("hyprland", "configs/hypr/hyprland.conf", ".config/hypr/hyprland.conf", "hyprland", "hyprland",
            _render_hyprland),
    Dotfile("hypridle", "configs/hypr/hypridle.conf", ".config/hypr/hypridle.conf", "verbatim", "hyprland"),
    Dotfile("hyprlock", "configs/hypr/hyprlock.conf", ".config/hypr/hyprlock.conf", "hyprlock", "hyprland",
            _render_hyprlock),
    Dotfile("arcon-colors", "configs/hypr/arcon-colors.conf", ".config/hypr/arcon-colors.conf", "verbatim", "hyprland"),
)


def rendered(ctx: Context, d: Dotfile) -> str:
    return d.render(ctx, (ctx.repo_root / d.source).read_text())


class DeployDotfile(WriteFile):
    reversible = Reversible.YES

    def __init__(self, d: Dotfile):
        self.dotfile = d
        super().__init__(f"dotfiles.{d.name}", f"Deploy {d.target}", Path("~") / d.target,
                         lambda ctx: rendered(ctx, d), risk=Risk.LOW)

    def plan(self, ctx):
        self.path = ctx.home / self.dotfile.target
        source = (ctx.repo_root / self.dotfile.source).read_text()
        problems = rules.check(self.dotfile.kind, source, self.content(ctx), ctx.profile.get("profile", "name"))
        if problems:  # never deploy something that breaks D8/D18
            raise RuntimeError(f"{self.dotfile.name}: rendered file violates D18: {problems[:3]}")
        return super().plan(ctx)


def diff(ctx: Context, d: Dotfile) -> str:
    live = read_text(ctx.home / d.target)
    if live is None:
        return f"{d.target}: not deployed\n"
    want = rendered(ctx, d)
    return "".join(difflib.unified_diff(want.splitlines(True), live.splitlines(True),
                                        f"repo:{d.source} (rendered)", f"live:~/{d.target}"))


def capture(ctx: Context, d: Dotfile) -> bool:
    """Copy the live file back into the repo (D11: the owner refreshes the source).
    Generated parts are not captured: hyprland's monitor block is replaced by the
    repo's own monitor lines, hyprlock keeps the Ax-Shell source line."""
    live = read_text(ctx.home / d.target)
    if live is None:
        return False
    source_path = ctx.repo_root / d.source
    source = source_path.read_text()
    if d.kind == "hyprland":
        original_monitors = "".join(l for l in source.splitlines(True) if rules._MONITOR_LINE.match(l))
        live = live.replace(_block_of(live), original_monitors) if _block_of(live) else live
    elif d.kind == "hyprlock":
        live = live.replace(rules.ARCON_SOURCE, rules.AXSHELL_SOURCE, 1)
    if live == source:
        return False
    source_path.write_text(live)
    return True


def _block_of(text: str) -> str:
    start = text.find(rules.MONITOR_BEGIN)
    end = text.find(rules.MONITOR_END)
    return text[start:end + len(rules.MONITOR_END) + 1] if start != -1 and end != -1 else ""


@register("dotfiles", "Dotfiles", order=60)
def build(ctx: Context):
    return [DeployDotfile(d) for d in DOTFILES if d.module == "dotfiles"]
