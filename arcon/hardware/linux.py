"""Hardware detection on Linux from sysfs/procfs (read-only).

`root` lets tests point at a fixture tree instead of `/`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from arcon.core.runner import Runner

PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x1022": "amd", "0x8086": "intel",
               "0x1af4": "virtual", "0x15ad": "virtual", "0x1234": "virtual", "0x80ee": "virtual",
               "0x1414": "virtual"}

# NVIDIA Turing (TU1xx, PCI device ids from 0x1e00) and newer are supported by the
# open kernel modules; Volta/Pascal/Maxwell (below 0x1e00) are not.
NVIDIA_OPEN_MIN_DEVICE = 0x1E00


@dataclass(frozen=True)
class GPU:
    vendor: str          # nvidia | amd | intel | virtual | unknown
    device_id: int
    slot: str
    boot_vga: bool = False
    label: str = ""

    @property
    def nvidia_open_capable(self) -> bool:
        return self.vendor == "nvidia" and self.device_id >= NVIDIA_OPEN_MIN_DEVICE


@dataclass
class Hardware:
    gpus: list[GPU] = field(default_factory=list)
    cpu_vendor: str = "unknown"
    ram_mb: int = 0
    root_rotational: bool | None = None   # None = unknown
    has_battery: bool = False
    on_battery: bool = False
    virtualization: str = "none"
    kernels: list[str] = field(default_factory=list)   # installed kernel flavours: linux, linux-lts, …

    @property
    def gpu_vendors(self) -> list[str]:
        return sorted({g.vendor for g in self.gpus})

    @property
    def is_hybrid(self) -> bool:
        real = {g.vendor for g in self.gpus if g.vendor in ("nvidia", "amd", "intel")}
        return len(real) > 1

    @property
    def root_is_ssd(self) -> bool:
        return self.root_rotational is False


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return default


def detect_gpus(root: Path = Path("/")) -> list[GPU]:
    gpus = []
    base = root / "sys" / "bus" / "pci" / "devices"
    if not base.is_dir():
        return gpus
    for dev in sorted(base.iterdir()):
        if not _read(dev / "class").startswith("0x03"):
            continue
        vendor = PCI_VENDORS.get(_read(dev / "vendor").lower(), "unknown")
        try:
            device = int(_read(dev / "device", "0x0"), 16)
        except ValueError:
            device = 0
        gpus.append(GPU(vendor, device, dev.name.replace("_", ":"),
                        _read(dev / "boot_vga") == "1", _read(dev / "label")))
    return gpus


def _root_rotational(root: Path) -> bool | None:
    """Rotational flag of the block device holding `/` (via /proc/mounts + sysfs)."""
    source = ""
    for line in _read(root / "proc" / "mounts").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1] == "/":
            source = parts[0]
    name = Path(source).name if source.startswith("/dev/") else ""
    if not name:
        return None
    block = root / "sys" / "class" / "block" / name
    if not block.exists():
        return None
    # a partition's queue lives on its parent disk
    queue = block / "queue" / "rotational"
    if not queue.exists():
        queue = block.resolve().parent / "queue" / "rotational"
    value = _read(queue)
    return None if value == "" else value == "1"


def detect(runner: Runner | None = None, root: Path = Path("/")) -> Hardware:
    hw = Hardware(gpus=detect_gpus(root))
    cpuinfo = _read(root / "proc" / "cpuinfo")
    if "GenuineIntel" in cpuinfo:
        hw.cpu_vendor = "intel"
    elif "AuthenticAMD" in cpuinfo:
        hw.cpu_vendor = "amd"
    for line in _read(root / "proc" / "meminfo").splitlines():
        if line.startswith("MemTotal:"):
            hw.ram_mb = int(line.split()[1]) // 1024
    hw.root_rotational = _root_rotational(root)
    supplies = root / "sys" / "class" / "power_supply"
    if supplies.is_dir():
        for s in supplies.iterdir():
            kind = _read(s / "type")
            if kind == "Battery":
                hw.has_battery = True
            if kind == "Mains" and _read(s / "online") == "0":
                hw.on_battery = True
    modules = root / "usr" / "lib" / "modules"
    if modules.is_dir():
        hw.kernels = sorted({_read(m / "pkgbase") for m in modules.iterdir() if (m / "pkgbase").exists()} - {""})
    if runner is not None and root == Path("/"):
        res = runner.run(["systemd-detect-virt"], mutating=False, check=False, timeout=10)
        hw.virtualization = res.stdout.strip() or "none"
    return hw
