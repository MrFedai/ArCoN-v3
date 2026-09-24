"""Operating-system detection.

`/etc/os-release` is PARSED as data, never sourced/executed (v2.5 sourced it, S-07).
"""

from __future__ import annotations

import platform as _platform
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Family(str, Enum):
    ARCH = "arch"
    DEBIAN = "debian"   # Debian and Ubuntu share one provider (D4)
    FEDORA = "fedora"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


class Tier(str, Enum):
    SUPPORTED = "supported"        # D4: Arch, Debian, Ubuntu, Fedora
    EXPERIMENTAL = "experimental"  # known derivative of a supported distro
    STUB = "stub"                  # Windows / macOS: interfaces only (D3)
    UNSUPPORTED = "unsupported"


SUPPORTED_IDS = {"arch": Family.ARCH, "debian": Family.DEBIAN, "ubuntu": Family.DEBIAN, "fedora": Family.FEDORA}
_LIKE = {"arch": Family.ARCH, "debian": Family.DEBIAN, "ubuntu": Family.DEBIAN, "fedora": Family.FEDORA}


@dataclass(frozen=True)
class OSInfo:
    family: Family
    tier: Tier
    id: str
    name: str
    version_id: str = ""
    id_like: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_linux(self) -> bool:
        return self.family not in (Family.WINDOWS, Family.MACOS)


def parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.replace("_", "").isalnum():
            continue
        try:
            parts = shlex.split(value, posix=True)
        except ValueError:
            continue
        values[key] = parts[0] if parts else ""
    return values


def classify(values: dict[str, str]) -> OSInfo:
    os_id = values.get("ID", "").lower()
    like = tuple(values.get("ID_LIKE", "").lower().split())
    name = values.get("PRETTY_NAME") or values.get("NAME") or os_id or "unknown"
    version = values.get("VERSION_ID", "")
    if os_id in SUPPORTED_IDS:
        return OSInfo(SUPPORTED_IDS[os_id], Tier.SUPPORTED, os_id, name, version, like)
    for candidate in like:
        if candidate in _LIKE:
            return OSInfo(_LIKE[candidate], Tier.EXPERIMENTAL, os_id, name, version, like)
    return OSInfo(Family.UNKNOWN, Tier.UNSUPPORTED, os_id, name, version, like)


def detect(os_release: Path = Path("/etc/os-release"), system: str | None = None) -> OSInfo:
    system = system or _platform.system()
    if system == "Windows":
        return OSInfo(Family.WINDOWS, Tier.STUB, "windows", "Windows")
    if system == "Darwin":
        return OSInfo(Family.MACOS, Tier.STUB, "macos", "macOS")
    for path in (os_release, Path("/usr/lib/os-release")):
        try:
            return classify(parse_os_release(path.read_text(errors="replace")))
        except OSError:
            continue
    return OSInfo(Family.UNKNOWN, Tier.UNSUPPORTED, "", "unknown")
