"""D8/D18 acceptance check: a deployed dotfile may differ from its repo source
ONLY by the substitutions listed in CLAUDE.md D18.

check(kind, source, deployed, user) -> list of human-readable violations ([] = OK).
Kinds: "gno", "hyprland", "hyprlock", "verbatim".
"""

from __future__ import annotations

import re

WALLPAPER_SECTIONS = {"org/gnome/desktop/background", "org/gnome/desktop/screensaver"}
WALLPAPER_KEYS = {"picture-uri", "picture-uri-dark", "picture-options"}

MONITOR_BEGIN = "# >>> ArCoN monitors (generated) >>>"
MONITOR_END = "# <<< ArCoN monitors <<<"
_MONITOR_LINE = re.compile(r"^\s*#?\s*monitor\s*=")

AXSHELL_SOURCE = "source = ~/.config/Ax-Shell/config/hypr/colors.conf"
ARCON_SOURCE = "source = ~/.config/hypr/arcon-colors.conf"


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _compare(expected: list[str], got: list[str], label: str) -> list[str]:
    if len(expected) != len(got):
        return [f"{label}: line count {len(got)} != {len(expected)}"]
    return [
        f"{label}:{i}: expected {e!r}, got {g!r}"
        for i, (e, g) in enumerate(zip(expected, got), start=1) if e != g
    ]


def _check_gno(source: str, deployed: str, user: str) -> list[str]:
    src, dep = _lines(source), _lines(deployed)
    if len(src) != len(dep):
        return [f"gno: line count {len(dep)} != {len(src)}"]
    problems, section = [], None
    for i, (s, d) in enumerate(zip(src, dep), start=1):
        head = s.strip()
        if head.startswith("[") and head.endswith("]"):
            section = head[1:-1]
        key = head.split("=", 1)[0].strip() if "=" in head and not head.startswith("#") else None
        if section in WALLPAPER_SECTIONS and key in WALLPAPER_KEYS:
            if not d.strip().startswith(f"{key}="):
                problems.append(f"gno:{i}: wallpaper key {key} renamed or removed: {d!r}")
            continue
        if s.replace("USER_PLACEHOLDER", user) != d:
            problems.append(f"gno:{i}: expected {s.replace('USER_PLACEHOLDER', user)!r}, got {d!r}")
    return problems


def _strip_monitor_block(lines: list[str]) -> tuple[list[str], list[str]]:
    problems, out, inside, blocks = [], [], False, 0
    for line in lines:
        text = line.rstrip("\n")
        if text == MONITOR_BEGIN:
            inside, blocks = True, blocks + 1
            continue
        if text == MONITOR_END:
            inside = False
            continue
        if not inside:
            out.append(line)
    if blocks != 1:
        problems.append(f"hyprland: expected exactly one generated monitor block, found {blocks}")
    if inside:
        problems.append("hyprland: monitor block not closed")
    return out, problems


def _check_hyprland(source: str, deployed: str) -> list[str]:
    src = [l for l in _lines(source) if not _MONITOR_LINE.match(l)]
    dep, problems = _strip_monitor_block(_lines(deployed))
    stray = [l for l in dep if _MONITOR_LINE.match(l)]
    if stray:
        problems.append(f"hyprland: monitor lines outside the generated block: {stray}")
    return problems + _compare(src, dep, "hyprland")


def _check_hyprlock(source: str, deployed: str) -> list[str]:
    src, dep = _lines(source), _lines(deployed)
    if len(src) != len(dep):
        return [f"hyprlock: line count {len(dep)} != {len(src)}"]
    problems = []
    for i, (s, d) in enumerate(zip(src, dep), start=1):
        if s.strip() == AXSHELL_SOURCE and d.strip() in (AXSHELL_SOURCE, ARCON_SOURCE):
            continue
        if s != d:
            problems.append(f"hyprlock:{i}: expected {s!r}, got {d!r}")
    return problems


def check(kind: str, source: str, deployed: str, user: str = "") -> list[str]:
    if kind == "gno":
        return _check_gno(source, deployed, user)
    if kind == "hyprland":
        return _check_hyprland(source, deployed)
    if kind == "hyprlock":
        return _check_hyprlock(source, deployed)
    if kind == "verbatim":
        return [] if source == deployed else ["verbatim file differs"]
    raise ValueError(f"unknown dotfile kind {kind!r}")
