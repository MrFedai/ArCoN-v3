"""Package catalog (arcon/data/packages.toml, D28): logical id → per-distro name."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from arcon.platform.detect import Family, OSInfo

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "packages.toml"


@dataclass(frozen=True)
class Entry:
    id: str
    groups: tuple[str, ...]
    arch: str
    debian: str
    ubuntu: str
    fedora: str
    flatpak: str
    description: str

    def native(self, os: OSInfo) -> str:
        """Distro package name ('' = not packaged). Arch AUR names keep the 'aur:' prefix."""
        if os.family is Family.ARCH:
            return self.arch
        if os.family is Family.FEDORA:
            return self.fedora
        if os.family is Family.DEBIAN:
            return self.ubuntu if os.id == "ubuntu" else self.debian
        return ""


@lru_cache(maxsize=4)
def load(path: Path = CATALOG_PATH) -> dict[str, Entry]:
    data = tomllib.loads(path.read_text())
    entries = {}
    for pid, p in data["pkg"].items():
        debian = p.get("debian", "")
        entries[pid] = Entry(pid, tuple(p.get("groups", ())), p.get("arch", ""), debian,
                             p.get("ubuntu", debian), p.get("fedora", ""), p.get("flatpak", ""),
                             p.get("description", ""))
    return entries


def group(name: str, catalog: dict[str, Entry] | None = None) -> list[Entry]:
    catalog = catalog or load()
    return [e for e in catalog.values() if name in e.groups]
