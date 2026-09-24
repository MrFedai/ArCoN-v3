"""JSON-lines journal — ALWAYS written (D6). Drives resume, idempotency,
rollback and the final report.

Layout:  <state>/runs/<run_id>/journal.jsonl
         <state>/runs/<run_id>/backup/<absolute path of each backed-up file>
         <state>/runs/latest -> <run_id>   (text file, not a symlink)
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# action status as recorded in the journal
STARTED, DONE, SKIPPED, FAILED = "started", "done", "skipped", "failed"


def new_run_id() -> str:
    """Sortable and unique even for several runs in the same second."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + secrets.token_hex(2)


@dataclass
class Journal:
    run_dir: Path

    @classmethod
    def create(cls, runs_dir: Path, run_id: str | None = None, **meta: Any) -> "Journal":
        run_id = run_id or new_run_id()
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        journal = cls(run_dir)
        journal.write("run_start", **meta)
        (runs_dir / "latest").write_text(run_id + "\n")
        return journal

    @classmethod
    def open(cls, runs_dir: Path, run_id: str | None = None) -> "Journal":
        if run_id is None:
            latest = runs_dir / "latest"
            if not latest.exists():
                raise FileNotFoundError("no previous run")
            run_id = latest.read_text().strip()
        run_dir = runs_dir / run_id
        if not (run_dir / "journal.jsonl").exists():
            raise FileNotFoundError(f"run {run_id} has no journal")
        return cls(run_dir)

    @property
    def run_id(self) -> str:
        return self.run_dir.name

    @property
    def path(self) -> Path:
        return self.run_dir / "journal.jsonl"

    @property
    def backup_dir(self) -> Path:
        return self.run_dir / "backup"

    def write(self, event: str, **data: Any) -> None:
        record = {"ts": time.time(), "event": event, **data}
        line = json.dumps(record, sort_keys=True, default=str)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def events(self) -> Iterator[dict[str, Any]]:
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line cut by a crash is ignored, not fatal

    def action_status(self) -> dict[str, str]:
        """Last recorded status per action id."""
        status: dict[str, str] = {}
        for ev in self.events():
            if ev["event"] == "action":
                status[ev["id"]] = ev["status"]
        return status

    def finished(self) -> bool:
        return any(ev["event"] == "run_end" for ev in self.events())


def list_runs(runs_dir: Path) -> list[Journal]:
    if not runs_dir.is_dir():
        return []
    return [Journal(d) for d in sorted(runs_dir.iterdir()) if (d / "journal.jsonl").exists()]
