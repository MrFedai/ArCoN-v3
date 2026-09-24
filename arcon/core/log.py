"""Every run is logged to a file inside its run directory (D14)."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_file_logging(path: Path, verbose: bool = False) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("arcon")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    return handler
