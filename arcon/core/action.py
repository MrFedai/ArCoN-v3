"""Actions: the unit of work. Every mutating step in ArCoN is an Action with
plan() / apply() / verify() and an honest reversibility label."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover
    from arcon.core.profile import Profile
    from arcon.core.runner import Runner
    from arcon.core.ui import UI
    from arcon.platform.detect import OSInfo
    from arcon.recovery.backup import FileChanger
    from arcon.recovery.journal import Journal


class Risk(str, Enum):
    LOW = "low"        # reversible, no behaviour change
    MEDIUM = "medium"  # behaviour change, reversible
    HIGH = "high"      # hard to reverse or can lock the user out


class Reversible(str, Enum):
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"
    ONE_WAY = "one-way"  # third-party code (D16)


@dataclass(frozen=True)
class Change:
    kind: str    # package | flatpak | file | setting | service | repo | command | snapshot
    target: str
    detail: str = ""


@dataclass
class Context:
    runner: "Runner"
    profile: "Profile"
    os: "OSInfo"
    journal: "Journal"
    files: "FileChanger"
    ui: "UI"
    repo_root: Path
    home: Path
    facts: dict[str, Any] = field(default_factory=dict)  # detection results shared between actions

    @property
    def dry_run(self) -> bool:
        return self.runner.dry_run


class Action:
    """Subclass and override plan() and apply(); verify() defaults to True."""

    id: str = ""
    title: str = ""
    module: str = ""
    risk: Risk = Risk.LOW
    reversible: Reversible = Reversible.YES
    requires: tuple[str, ...] = ()   # ids of actions that must succeed first
    reboot: bool = False             # a reboot is needed for the change to take effect

    def plan(self, ctx: Context) -> list[Change]:
        raise NotImplementedError

    def apply(self, ctx: Context) -> None:
        raise NotImplementedError

    def verify(self, ctx: Context) -> bool:
        return True

    def __repr__(self) -> str:
        return f"<Action {self.id}>"


@dataclass
class Module:
    name: str
    title: str
    build: Callable[[Context], list[Action]]
    order: int = 100


_REGISTRY: dict[str, Module] = {}


def register(name: str, title: str, order: int = 100) -> Callable:
    """Explicit registration of a module's action factory (no import magic)."""
    def deco(fn: Callable[[Context], list[Action]]):
        _REGISTRY[name] = Module(name, title, fn, order)
        return fn
    return deco


def registered_modules() -> list[Module]:
    return sorted(_REGISTRY.values(), key=lambda m: (m.order, m.name))


def clear_registry() -> None:  # tests only
    _REGISTRY.clear()
