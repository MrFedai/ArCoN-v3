"""`gnome` module (F17, F18): dconf settings from configs/gno.conf with the D18
substitutions, a full `dconf dump /` backup first, verification of the owner's
settings afterwards; optional debloat."""

from __future__ import annotations

import configparser
import os

from arcon.core.paths import current_user
from arcon.core.action import Action, Change, Context, Reversible, Risk, register
from arcon.dotfiles.rules import WALLPAPER_KEYS, WALLPAPER_SECTIONS
from arcon.package.actions import request
from arcon.package.providers import native_for
from arcon.recovery.backup import dconf_user

BLOAT = ("gnome-tour", "gnome-weather", "gnome-maps", "gnome-contacts", "gnome-music", "epiphany")
OWNER_KEYS = ("/org/gnome/desktop/interface/color-scheme", "/org/gnome/desktop/interface/gtk-theme")


def user_name() -> str:
    return current_user()


def render_gno(ctx: Context, text: str) -> str:
    """D18: user name + wallpaper keys from the profile (default: none → solid black)."""
    text = text.replace("USER_PLACEHOLDER", user_name())
    mode = ctx.profile.get("wallpaper", "mode")
    uri = ""
    if mode == "file":
        path = os.path.expanduser(ctx.profile.get("wallpaper", "file"))
        uri = f"file://{path}" if path else ""
    out, section = [], None
    for line in text.splitlines(keepends=True):
        head = line.strip()
        if head.startswith("[") and head.endswith("]"):
            section = head[1:-1]
        key = head.split("=", 1)[0] if "=" in head and not head.startswith("#") else None
        if section in WALLPAPER_SECTIONS and key in WALLPAPER_KEYS:
            value = "'none'" if key == "picture-options" and not uri else ("'zoom'" if key == "picture-options" else f"'{uri}'")
            line = f"{key}={value}\n"
        out.append(line)
    return "".join(out)


def dconf_keys(text: str) -> dict[str, str]:
    """path -> value literal for every key in a dconf keyfile."""
    cp = configparser.ConfigParser(interpolation=None, strict=False, comment_prefixes=("#",))
    cp.optionxform = str
    cp.read_string(text)
    return {f"/{section}/{key}": value for section in cp.sections() for key, value in cp.items(section)}


def _norm(value: str) -> str:
    return "".join(value.split())


def session_ok(ctx: Context) -> bool:
    return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")) and \
        ctx.runner.run(["sh", "-c", "command -v dconf"], mutating=False, check=False).ok


class ApplyGnomeSettings(Action):
    id, title = "gnome.settings", "GNOME settings (gno.conf: dark theme, keybindings, app folders)"
    risk, reversible = Risk.MEDIUM, Reversible.YES

    def _rendered(self, ctx):
        return render_gno(ctx, (ctx.repo_root / "configs" / "gno.conf").read_text())

    def plan(self, ctx):
        if not session_ok(ctx):
            ctx.ui.warn("gnome: no D-Bus session or dconf missing — run ArCoN inside your GNOME session")
            return []
        changes = []
        for path, value in dconf_keys(self._rendered(ctx)).items():
            current = ctx.runner.run(["dconf", "read", path], mutating=False, check=False).stdout.strip()
            if _norm(current) != _norm(value):
                changes.append(Change("setting", path, f"{current or '(default)'} -> {value}"))
        return changes

    def apply(self, ctx):
        dump = dconf_user(ctx.runner, "dump", "/", mutating=False).stdout  # user db only
        backup = ctx.journal.backup_dir / "dconf-full.ini"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(dump)
        ctx.journal.write("dconf_backup", path=str(backup))
        ctx.runner.run(["dconf", "reset", "-f", "/org/gnome/desktop/app-folders/"])
        ctx.runner.run(["dconf", "load", "/"], input=self._rendered(ctx))

    def verify(self, ctx):
        wanted = dconf_keys(self._rendered(ctx))
        for path in OWNER_KEYS:
            got = ctx.runner.run(["dconf", "read", path], mutating=False, check=False).stdout.strip()
            if _norm(got) != _norm(wanted[path]):
                return False
        return True


class Debloat(Action):
    id, title = "gnome.debloat", "Remove GNOME bloatware"
    risk, reversible = Risk.LOW, Reversible.PARTIAL

    def plan(self, ctx):
        if not ctx.profile.get("gnome", "debloat"):
            return []
        self._present = sorted(native_for(ctx.os, ctx.runner).installed(BLOAT))  # exact names (v2.5 used a regex)
        return [Change("package-remove", n) for n in self._present]

    def apply(self, ctx):
        native_for(ctx.os, ctx.runner).remove(self._present)
        ctx.journal.write("packages_removed", names=self._present)


@register("gnome", "GNOME", order=40)
def build(ctx: Context):
    request(ctx, ids=["wl-clipboard", "adw-gtk-theme", "gnome-shell-extension-clipboard-indicator"])
    return [ApplyGnomeSettings(), Debloat()]
