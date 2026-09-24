"""Static extraction of data embedded in ArCoN v2.5 `setup.sh`.

Only literal data is read (package arrays and inline package strings);
nothing from setup.sh is executed.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V25_TAG = "v2.5.0"

# declare -a NAME=( ... )  (multi-line arrays at top level and in sector 9)
_ARRAY = re.compile(r"(?:declare -a\s+)?\b([A-Za-z_]+)=\((.*?)\)", re.S)
# name="a b c"  (inline space-separated package strings)
_STRING = re.compile(r'\b(hypr_pkgs|base_gaming)="([^"]*)"')
# GPU choices inside the `select gpu` case
_GPU = re.compile(r"^\s*(Nvidia|AMD|Intel)\)\s+gpu_pkgs=\"([^\"]*)\"", re.M)

ARRAYS = (
    "PKG_ESSENTIALS", "PKG_MEDIA", "PKG_CYBER", "PKG_REMOTE", "PKG_POWER",
    "PROTECTED_PKGS", "bloat_packages", "sec_tools",
)


def v25_setup_sh() -> str:
    """setup.sh exactly as tagged v2.5.0 (independent of the working tree)."""
    return subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V25_TAG}:setup.sh"],
        check=True, capture_output=True, text=True,
    ).stdout


def extract_package_lists(src: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name, body in _ARRAY.findall(src):
        if name in ARRAYS and name not in found:
            found[name] = shlex.split(body, comments=True)
    for name, body in _STRING.findall(src):
        found.setdefault(name, body.split())
    for vendor, body in _GPU.findall(src):
        found[f"gpu_{vendor.lower()}"] = body.split()
    missing = [n for n in ARRAYS if n not in found]
    if missing:
        raise ValueError(f"arrays not found in setup.sh: {missing}")
    return dict(sorted(found.items()))
