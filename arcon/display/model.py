"""Monitor model and the D13 rules: best mode per monitor, owner's layout kept.

Identity = vendor + product + serial (never the connector name, which changes
with the driver: eDP-1 vs eDP-2).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Mode:
    width: int
    height: int
    refresh: float
    id: str = ""              # backend-specific mode id (Mutter), or "" for Hyprland
    preferred: bool = False

    @property
    def pixels(self) -> int:
        return self.width * self.height

    def label(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh:.2f}"


@dataclass(frozen=True)
class Monitor:
    connector: str
    vendor: str
    product: str
    serial: str
    modes: tuple[Mode, ...]
    current: Mode | None = None
    builtin: bool = False
    display_name: str = ""

    @property
    def identity(self) -> str:
        return " ".join(p for p in (self.vendor, self.product, self.serial) if p) or self.connector


@dataclass
class Placement:
    """Where a monitor goes: from the profile, or captured from the current state."""
    identity: str
    x: int = 0
    y: int = 0
    scale: float = 1.0
    primary: bool = False
    transform: int = 0
    enabled: bool = True


@dataclass
class Target:
    monitor: Monitor
    candidates: list[Mode]          # best first; later entries are fallbacks (D13)
    placement: Placement

    @property
    def mode(self) -> Mode:
        return self.candidates[0]


def rank_modes(modes: tuple[Mode, ...] | list[Mode], prefer: str = "resolution") -> list[Mode]:
    """Best mode first. prefer=resolution: most pixels, then highest refresh;
    prefer=refresh: highest refresh, then most pixels. Duplicates removed."""
    if prefer == "refresh":
        key = lambda m: (round(m.refresh, 1), m.pixels, m.preferred)
    else:
        key = lambda m: (m.pixels, round(m.refresh, 1), m.preferred)
    seen, ranked = set(), []
    for m in sorted(modes, key=key, reverse=True):
        k = (m.width, m.height, round(m.refresh, 2))
        if k not in seen:
            seen.add(k)
            ranked.append(m)
    return ranked


def plan_layout(monitors: list[Monitor], placements: list[Placement], prefer: str,
                keep_positions: bool = False) -> list[Target]:
    """Combine detected monitors with the wanted placement.

    Monitors are laid out in the placements' left-to-right order (by x). Unless
    `keep_positions`, x is recomputed so that neighbours touch after the mode
    change (GNOME rejects gaps/overlaps); y and scale are kept."""
    by_id = {p.identity: p for p in placements}
    targets = []
    for mon in monitors:
        place = by_id.get(mon.identity) or by_id.get(mon.connector)
        if place is None:
            # new or unknown monitor: to the right of everything, not primary
            place = Placement(mon.identity, x=10**6, y=0)
        if not place.enabled:
            continue
        ranked = rank_modes(mon.modes, prefer)
        if not ranked:
            continue
        targets.append(Target(mon, ranked, replace(place, identity=mon.identity)))
    targets.sort(key=lambda t: (t.placement.x, t.placement.y))
    if not keep_positions:
        x = min((t.placement.x for t in targets), default=0) if targets else 0
        x = 0 if x >= 10**6 else x
        for t in targets:
            t.placement.x = x
            x += logical_width(t)
    if targets and not any(t.placement.primary for t in targets):
        builtin = [t for t in targets if t.monitor.builtin]
        (builtin[0] if builtin else targets[0]).placement.primary = True
    return targets


def logical_width(t: Target) -> int:
    w = t.mode.height if t.placement.transform in (1, 3, 5, 7) else t.mode.width
    return int(round(w / (t.placement.scale or 1.0)))


def placements_from_state(monitors: list[Monitor], logical: list[dict]) -> list[Placement]:
    """Current layout → placements (used by `arcon display capture`)."""
    out = []
    by_connector = {m.connector: m for m in monitors}
    for lm in logical:
        for conn in lm["connectors"]:
            mon = by_connector.get(conn)
            if mon:
                out.append(Placement(mon.identity, lm["x"], lm["y"], lm["scale"], lm["primary"], lm.get("transform", 0)))
    return out


def placements_from_profile(entries: list[dict]) -> list[Placement]:
    out = []
    for e in entries:
        x, y = 0, 0
        pos = str(e.get("position", "0,0")).replace("x", ",")
        if "," in pos:
            x, y = (int(v) for v in pos.split(",", 1))
        out.append(Placement(e["id"], x, y, float(e.get("scale", 1.0)), bool(e.get("primary", False)),
                             int(e.get("transform", 0)), bool(e.get("enabled", True))))
    return out


def placement_to_profile(p: Placement) -> dict:
    entry = {"id": p.identity, "position": f"{p.x},{p.y}", "scale": p.scale, "primary": p.primary}
    if p.transform:
        entry["transform"] = p.transform
    return entry
