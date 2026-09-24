"""GNOME/Mutter backend (D13): read and apply monitor configuration through
org.gnome.Mutter.DisplayConfig — Mutter writes monitors.xml itself when the
method is "persistent". Dry runs use method "verify": Mutter checks the
configuration without applying it.

The D-Bus connection is behind `Bus` so tests can use a fake.
"""

from __future__ import annotations

from typing import Any, Protocol

from arcon.display.model import Mode, Monitor, Target

VERIFY, TEMPORARY, PERSISTENT = 0, 1, 2
_PATH = "/org/gnome/Mutter/DisplayConfig"
_NAME = "org.gnome.Mutter.DisplayConfig"


class DisplayConfigError(RuntimeError):
    pass


class Bus(Protocol):
    def get_current_state(self) -> tuple: ...
    def apply_monitors_config(self, serial: int, method: int, logical: list, props: dict) -> None: ...


class JeepneyBus:
    """Real session-bus client (needs a GNOME session: DBUS_SESSION_BUS_ADDRESS)."""

    def __init__(self):
        from jeepney import DBusAddress
        from jeepney.io.blocking import open_dbus_connection
        self._addr = DBusAddress(_PATH, bus_name=_NAME, interface=_NAME)
        try:
            self._conn = open_dbus_connection(bus="SESSION")
        except Exception as exc:  # no session bus: not in a desktop session
            raise DisplayConfigError(f"no D-Bus session bus: {exc}") from exc

    def _call(self, method: str, signature: str | None = None, body: tuple = ()) -> tuple:
        from jeepney import new_method_call
        from jeepney.wrappers import DBusErrorResponse
        msg = new_method_call(self._addr, method, signature, body) if signature else new_method_call(self._addr, method)
        try:
            reply = self._conn.send_and_get_reply(msg, timeout=15)
        except DBusErrorResponse as exc:
            raise DisplayConfigError(str(exc)) from exc
        if reply.header.message_type.name == "error":
            raise DisplayConfigError(str(reply.body))
        return reply.body

    def get_current_state(self) -> tuple:
        return self._call("GetCurrentState")

    def apply_monitors_config(self, serial, method, logical, props):
        self._call("ApplyMonitorsConfig", "uua(iiduba(ssa{sv}))a{sv}", (serial, method, logical, props))


def _prop(props: dict, key: str, default: Any = None) -> Any:
    value = props.get(key, default)
    # jeepney returns variants as (signature, value)
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return value[1]
    return value


def parse_state(state: tuple) -> tuple[int, list[Monitor], list[dict]]:
    serial, monitors_raw, logical_raw, _props = state
    monitors = []
    for (connector, vendor, product, serial_no), modes_raw, props in monitors_raw:
        modes, current = [], None
        for mode_id, width, height, refresh, _pref_scale, _scales, mprops in modes_raw:
            mode = Mode(int(width), int(height), float(refresh), str(mode_id),
                        bool(_prop(mprops, "is-preferred", False)))
            modes.append(mode)
            if _prop(mprops, "is-current", False):
                current = mode
        monitors.append(Monitor(connector, vendor, product, serial_no, tuple(modes), current,
                                bool(_prop(props, "is-builtin", False)), str(_prop(props, "display-name", ""))))
    logical = []
    for x, y, scale, transform, primary, mons, _p in logical_raw:
        logical.append({"x": int(x), "y": int(y), "scale": float(scale), "transform": int(transform),
                        "primary": bool(primary), "connectors": [m[0] for m in mons]})
    return int(serial), monitors, logical


def build_config(targets: list[Target], modes: dict[str, Mode] | None = None) -> list:
    """ApplyMonitorsConfig logical-monitor list; `modes` overrides a target's mode (fallback)."""
    logical = []
    for t in targets:
        mode = (modes or {}).get(t.monitor.identity, t.mode)
        p = t.placement
        logical.append((p.x, p.y, float(p.scale), p.transform, p.primary,
                        [(t.monitor.connector, mode.id, {})]))
    return logical


class GnomeDisplay:
    name = "gnome"

    def __init__(self, bus: Bus):
        self.bus = bus

    def read(self) -> tuple[int, list[Monitor], list[dict]]:
        return parse_state(self.bus.get_current_state())

    def apply(self, targets: list[Target], dry_run: bool) -> dict[str, Mode]:
        """Apply best modes; on a mode that does not become active, fall back to
        the next candidate for that monitor. Returns the modes in effect."""
        serial, _, _ = self.read()
        chosen = {t.monitor.identity: t.mode for t in targets}
        self.bus.apply_monitors_config(serial, VERIFY if dry_run else PERSISTENT, build_config(targets, chosen), {})
        if dry_run:
            return chosen
        for _attempt in range(max((len(t.candidates) for t in targets), default=1)):
            _, monitors, _ = self.read()
            current = {m.identity: m.current for m in monitors}
            wrong = [t for t in targets if not _same(current.get(t.monitor.identity), chosen[t.monitor.identity])]
            if not wrong:
                return chosen
            for t in wrong:
                idx = t.candidates.index(chosen[t.monitor.identity])
                if idx + 1 >= len(t.candidates):
                    raise DisplayConfigError(f"{t.monitor.identity}: no working mode found")
                chosen[t.monitor.identity] = t.candidates[idx + 1]
            serial, _, _ = self.read()
            self.bus.apply_monitors_config(serial, PERSISTENT, build_config(targets, chosen), {})
        raise DisplayConfigError("monitor configuration did not settle")


def _same(a: Mode | None, b: Mode) -> bool:
    return a is not None and (a.width, a.height, round(a.refresh, 1)) == (b.width, b.height, round(b.refresh, 1))
