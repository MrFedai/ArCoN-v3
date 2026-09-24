"""Explicit list of feature modules (no import magic): importing a module
registers its action factory with `arcon.core.action.register`."""

import importlib

MODULES = (
    "arcon.system.actions",
    "arcon.package.actions",
    "arcon.display.actions",
    "arcon.desktop.gnome",
    "arcon.desktop.hyprland",
    "arcon.gaming.actions",
    "arcon.dotfiles.manager",
    "arcon.terminal.actions",
    "arcon.security.actions",
    "arcon.optimization.actions",
)


def load() -> None:
    for name in MODULES:
        importlib.import_module(name)
