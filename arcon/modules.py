"""Explicit list of feature modules (no import magic): importing a module
registers its action factory with `arcon.core.action.register`."""

import importlib

MODULES = (
    "arcon.package.actions",
    "arcon.display.actions",
)


def load() -> None:
    for name in MODULES:
        importlib.import_module(name)
