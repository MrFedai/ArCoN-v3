"""Run a v2.5 scenario and reduce its result to a comparable snapshot.

    python tests/characterization/snapshot.py --update   # rewrite golden files (review the diff!)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent / "golden" / "v25"
SCENARIOS = sorted(p.stem for p in (HERE / "scenarios").glob("*.answers"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_scenario(name: str, out: Path) -> dict:
    proc = subprocess.run(
        [str(HERE / "run_v25.sh"), name, str(out)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"harness failed for {name}: {proc.stderr}")
    home = out / "home"
    return {
        "scenario": name,
        "exit_code": int((out / "exit.txt").read_text().strip()),
        "commands": (out / "commands.log").read_text().splitlines(),
        "files": {
            str(p.relative_to(home)): sha256(p)
            for p in sorted(home.rglob("*")) if p.is_file()
        },
        "captures": {p.name: sha256(p) for p in sorted((out / "capture").iterdir())},
    }


def golden_path(name: str) -> Path:
    return GOLDEN / f"{name}.json"


def main() -> int:
    import tempfile

    if "--update" not in sys.argv:
        print(__doc__)
        return 2
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            snap = run_scenario(name, Path(tmp))
            golden_path(name).write_text(json.dumps(snap, indent=2) + "\n")
            for cap in (Path(tmp) / "capture").iterdir():
                if cap.name.endswith("dconf-load.ini"):
                    (GOLDEN / f"{name}.dconf-load.ini").write_bytes(cap.read_bytes())
        print(f"updated {golden_path(name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
