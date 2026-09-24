"""Package manager interface. Linux providers arrive in Phase 4; Windows and
macOS are stubs that report "not implemented" (D3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from arcon.core.runner import Runner


class NotSupported(RuntimeError):
    """The platform/provider exists as an interface only (D3)."""


class PackageManager(ABC):
    name: str = ""

    def __init__(self, runner: Runner):
        self.runner = runner

    @abstractmethod
    def installed(self, names: Iterable[str]) -> set[str]:
        """Subset of `names` that is installed (read-only)."""

    @abstractmethod
    def available(self, names: Iterable[str]) -> set[str]:
        """Subset of `names` available from the configured repositories (read-only)."""

    @abstractmethod
    def install(self, names: list[str]) -> None:
        """Install in ONE transaction (v2.5 called the manager once per package)."""

    @abstractmethod
    def remove(self, names: list[str]) -> None: ...


class StubPackageManager(PackageManager):
    platform = ""

    def _no(self, *_a, **_k):
        raise NotSupported(f"{self.name} on {self.platform} is not implemented in ArCoN v3.0 (skeleton only)")

    installed = available = install = remove = _no  # type: ignore[assignment]


class Winget(StubPackageManager):
    name, platform = "winget", "Windows"


class Homebrew(StubPackageManager):
    name, platform = "brew", "macOS"
