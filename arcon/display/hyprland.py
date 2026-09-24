"""Hyprland backend (D13/D18): the `monitor=` lines of hyprland.conf become one
generated block. With Hyprland running, modes come from `hyprctl monitors all -j`;
otherwise Hyprland's own `highres` / `highrr` keywords pick the best mode at start."""

from __future__ import annotations

import json
import re

from arcon.core.runner import Runner
from arcon.display.model import Mode, Monitor, Target

BEGIN = "# >>> ArCoN monitors (generated) >>>"
END = "# <<< ArCoN monitors <<<"
_MONITOR_LINE = re.compile(r"^\s*#?\s*monitor\s*=")
_MODE = re.compile(r"(\d+)x(\d+)@([\d.]+)Hz")


def read(runner: Runner) -> list[Monitor] | None:
    """None when Hyprland is not running."""
    res = runner.run(["hyprctl", "monitors", "all", "-j"], mutating=False, check=False, timeout=10)
    if not res.ok or not res.stdout.strip().startswith("["):
        return None
    monitors = []
    for m in json.loads(res.stdout):
        modes = tuple(Mode(int(a), int(b), float(c)) for a, b, c in
                      (_MODE.match(s).groups() for s in m.get("availableModes", []) if _MODE.match(s)))
        current = Mode(int(m["width"]), int(m["height"]), float(m["refreshRate"]))
        monitors.append(Monitor(m["name"], m.get("make", ""), m.get("model", ""), m.get("serial", ""),
                                modes, current, m["name"].startswith("eDP"), m.get("description", "")))
    return monitors


def monitor_lines(targets: list[Target], prefer: str) -> list[str]:
    lines = []
    for t in targets:
        p = t.placement
        ident = f"desc:{t.monitor.display_name}" if t.monitor.display_name else t.monitor.connector
        mode = t.mode.label() if t.mode.id != "auto" else ("highrr" if prefer == "refresh" else "highres")
        extra = f",transform,{p.transform}" if p.transform else ""
        lines.append(f"monitor={ident},{mode},{p.x}x{p.y},{p.scale:g}{extra}")
    lines.append("# any other monitor: preferred mode, placed automatically")
    lines.append("monitor=,preferred,auto,1")
    return lines


def render_block(lines: list[str]) -> str:
    return "\n".join([BEGIN, *lines, END]) + "\n"


def replace_monitor_lines(config: str, block: str) -> str:
    """Put `block` where the first monitor line was; drop every other monitor line
    (active or commented). Everything else is left byte-identical (D18)."""
    out, inserted, inside = [], False, False
    for line in config.splitlines(keepends=True):
        text = line.rstrip("\n")
        if text == BEGIN:
            inside = True
            if not inserted:
                out.append(block)
                inserted = True
            continue
        if text == END:
            inside = False
            continue
        if inside:
            continue
        if _MONITOR_LINE.match(line):
            if not inserted:
                out.append(block)
                inserted = True
            continue
        out.append(line)
    if not inserted:
        out.append(block)
    return "".join(out)
