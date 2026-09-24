#!/usr/bin/env python3
"""Verify the package catalog column of the distro this script runs on.

    python3 scripts/verify_catalog.py            # prints a Markdown section
    python3 scripts/verify_catalog.py --json     # machine-readable

Run it on Arch, Debian, Ubuntu and Fedora (CI containers do this, Phase 7) and
paste/merge the sections into docs/PACKAGE_CATALOG.md. Read-only: it only asks
the package manager whether a name exists. Stdlib only, no ArCoN imports, so it
runs in a bare container.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "arcon" / "data" / "packages.toml"


def os_id() -> str:
    for line in Path("/etc/os-release").read_text().splitlines():
        if line.startswith("ID="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def run(argv: list[str]) -> bool:
    return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def aur_exists(names: list[str]) -> set[str]:
    found: set[str] = set()
    for i in range(0, len(names), 50):
        q = "&".join("arg[]=" + urllib.parse.quote(n) for n in names[i:i + 50])
        with urllib.request.urlopen(f"https://aur.archlinux.org/rpc/v5/info?{q}", timeout=30) as r:
            found |= {p["Name"] for p in json.load(r)["results"]}
    return found


def check(distro: str, catalog: dict) -> dict[str, str]:
    col = "debian" if distro in ("debian",) else distro
    results: dict[str, str] = {}
    names: dict[str, str] = {}
    for pid, p in catalog["pkg"].items():
        name = p.get(col, p.get("debian", "")) if col == "ubuntu" else p.get(col, "")
        if name:
            names[pid] = name
        else:
            results[pid] = "not packaged (catalog)"
    if distro == "arch":
        aur = [n[4:] for n in names.values() if n.startswith("aur:")]
        plain = {pid: n for pid, n in names.items() if not n.startswith("aur:")}
        official = {pid for pid, n in plain.items() if run(["pacman", "-Si", n])}
        in_aur = aur_exists(aur + [n for pid, n in plain.items() if pid not in official])
        for pid, n in names.items():
            bare = n.removeprefix("aur:")
            if pid in official:
                results[pid] = "official" + (" (catalog says aur:)" if n.startswith("aur:") else "")
            elif bare in in_aur:
                results[pid] = "AUR"
            else:
                results[pid] = "MISSING"
    elif distro in ("debian", "ubuntu"):
        for pid, n in names.items():
            results[pid] = "ok" if run(["apt-cache", "show", n]) else "MISSING"
    elif distro == "fedora":
        for pid, n in names.items():
            query = ["dnf", "-q", "group", "info", n[1:]] if n.startswith("@") else ["dnf", "-q", "info", n]
            results[pid] = "ok" if run(query) else "MISSING"
    else:
        raise SystemExit(f"unsupported distro for verification: {distro}")
    if shutil.which("flatpak"):
        for pid, p in catalog["pkg"].items():
            if p.get("flatpak"):
                ok = run(["flatpak", "remote-info", "flathub", p["flatpak"]])
                results[pid] += f"; flatpak {'ok' if ok else 'MISSING'}"
    return results


def main() -> int:
    distro = os_id()
    catalog = tomllib.loads(CATALOG.read_text())
    results = check(distro, catalog)
    if "--json" in sys.argv:
        print(json.dumps({"distro": distro, "date": str(date.today()), "results": results}, indent=2))
    else:
        print(f"## {distro} — verified {date.today()}\n")
        print("| Package | Result |\n|---|---|")
        for pid in sorted(results):
            print(f"| {pid} | {results[pid]} |")
    return 1 if any("MISSING" in r for r in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
