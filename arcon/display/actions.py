"""`display` module (D13): best mode per monitor, the owner's layout kept.

The layout comes from `[[display.monitor]]` in the profile; when the profile
has none, the CURRENT layout is kept (only modes change). `arcon display capture`
writes the current layout into the profile."""

from __future__ import annotations

import os
from dataclasses import replace

from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.display import hyprland
from arcon.display.gnome import DisplayConfigError, GnomeDisplay, JeepneyBus
from arcon.display.model import (Mode, Monitor, Target, placements_from_profile, placements_from_state,
                                 plan_layout)


def gnome_session(env=os.environ) -> bool:
    return "GNOME" in env.get("XDG_CURRENT_DESKTOP", "").upper() and bool(env.get("DBUS_SESSION_BUS_ADDRESS"))


def gnome_backend(ctx: Context) -> GnomeDisplay | None:
    if "gnome_display" not in ctx.facts:
        backend = None
        if gnome_session():
            try:
                backend = GnomeDisplay(JeepneyBus())
            except DisplayConfigError as exc:
                ctx.ui.warn(f"display: {exc}")
        ctx.facts["gnome_display"] = backend
    return ctx.facts["gnome_display"]


def targets_for(ctx: Context, monitors: list[Monitor], logical: list[dict]) -> list[Target]:
    entries = ctx.profile.get("display", "monitor")
    placements = placements_from_profile(entries) if entries else placements_from_state(monitors, logical)
    return plan_layout(monitors, placements, ctx.profile.get("display", "prefer"),
                       keep_positions=bool(entries))


def _changes(targets: list[Target], monitors: list[Monitor], logical: list[dict]) -> list[Change]:
    changes = []
    current_pos = {}
    by_conn = {m.connector: m for m in monitors}
    for lm in logical:
        for c in lm["connectors"]:
            if c in by_conn:
                current_pos[by_conn[c].identity] = (lm["x"], lm["y"], lm["scale"], lm["primary"])
    for t in targets:
        cur = t.monitor.current
        if cur is None or (cur.width, cur.height, round(cur.refresh, 1)) != (t.mode.width, t.mode.height, round(t.mode.refresh, 1)):
            changes.append(Change("setting", t.monitor.identity,
                                  f"mode {cur.label() if cur else 'off'} -> {t.mode.label()}"))
        p = t.placement
        if current_pos.get(t.monitor.identity) != (p.x, p.y, p.scale, p.primary):
            changes.append(Change("setting", t.monitor.identity,
                                  f"position {p.x},{p.y} scale {p.scale:g}{' primary' if p.primary else ''}"))
    return changes


class GnomeMonitors(Action):
    id, title = "display.gnome", "Monitors: best mode, keep layout (GNOME)"
    risk, reversible = Risk.MEDIUM, Reversible.YES

    def plan(self, ctx):
        backend = gnome_backend(ctx)
        if backend is None:
            return []
        _, monitors, logical = backend.read()
        self._targets = targets_for(ctx, monitors, logical)
        return _changes(self._targets, monitors, logical)

    def apply(self, ctx):
        backend = gnome_backend(ctx)
        _, _, logical_before = backend.read()
        ctx.journal.write("display_before", logical=logical_before)
        applied = backend.apply(self._targets, dry_run=ctx.dry_run)
        for t in self._targets:
            if applied[t.monitor.identity] != t.mode:
                ctx.ui.warn(f"{t.monitor.identity}: {t.mode.label()} did not work, using {applied[t.monitor.identity].label()}")
        ctx.journal.write("display_applied", modes={k: v.label() for k, v in applied.items()})


def hyprland_block(ctx: Context) -> str:
    """Monitor block for hyprland.conf (D18). Uses live Hyprland data when running,
    otherwise connector names + Hyprland's own best-mode keyword."""
    prefer = ctx.profile.get("display", "prefer")
    monitors = hyprland.read(ctx.runner)
    if monitors:
        entries = ctx.profile.get("display", "monitor")
        placements = placements_from_profile(entries) if entries else []
        targets = plan_layout(monitors, placements, prefer, keep_positions=bool(entries))
        return hyprland.render_block(hyprland.monitor_lines(targets, prefer))
    backend = gnome_backend(ctx)
    lines = []
    if backend is not None:
        _, gmons, logical = backend.read()
        auto = [replace(m, display_name="", modes=(Mode(0, 0, 0.0, "auto"),)) for m in gmons]
        entries = ctx.profile.get("display", "monitor")
        placements = placements_from_profile(entries) if entries else placements_from_state(gmons, logical)
        lines = hyprland.monitor_lines(plan_layout(auto, placements, prefer, keep_positions=True), prefer)
    else:
        lines = ["# monitors could not be detected; Hyprland picks the preferred mode",
                 "monitor=,preferred,auto,1"]
    return hyprland.render_block(lines)


@register("display", "Monitors", order=30)
def build(ctx: Context) -> list[Action]:
    if gnome_backend(ctx) is None:
        ctx.ui.info("display: no GNOME session detected — monitor modes are left unchanged")
        return []
    return [GnomeMonitors()]
