"""Per-file backup and restore (D6 fallback when no filesystem snapshot exists).

Every file ArCoN changes goes through `FileChanger.write()`:
  1. a verified copy of the old file (or the fact that it did not exist) is
     recorded in the journal,
  2. the new content is written atomically,
  3. rollback restores exactly what was recorded.
Root-owned files are handled through the CommandRunner with sudo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from arcon.core.runner import Runner
from arcon.recovery.journal import Journal


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _backup_path(journal: Journal, target: Path) -> Path:
    return journal.backup_dir / str(target.resolve()).lstrip(os.sep)


@dataclass
class FileChanger:
    journal: Journal
    runner: Runner

    def write(self, target: Path, content: bytes, *, root: bool = False, mode: int | None = None) -> bool:
        """Write `content` to `target`. Returns False when the file already has
        exactly this content (idempotent, nothing recorded)."""
        target = Path(target)
        existed = target.exists()
        if existed and target.read_bytes() == content:
            return False
        if self.runner.dry_run:
            self.journal.write("file_planned", path=str(target), existed=existed,
                               new_sha256=sha256_bytes(content))
            return True
        backup = None
        if existed:
            backup = _backup_path(self.journal, target)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            if sha256_file(backup) != sha256_file(target):
                raise OSError(f"backup verification failed for {target}")
        self.journal.write("file_backup", path=str(target), existed=existed,
                           backup=str(backup) if backup else None,
                           old_sha256=sha256_file(target) if existed else None,
                           new_sha256=sha256_bytes(content), root=root)
        if root:
            self.runner.run(["mkdir", "-p", str(target.parent)], sudo=True)
            self.runner.run(["tee", str(target)], sudo=True, input=content.decode())
            if mode is not None:
                self.runner.run(["chmod", f"{mode:o}", str(target)], sudo=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.arcon-")
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
            if mode is not None:
                os.chmod(tmp, mode)
            elif existed:
                shutil.copymode(backup, tmp)
            os.replace(tmp, target)
        self.journal.write("file_written", path=str(target), sha256=sha256_bytes(content))
        return True


def restore_files(journal: Journal, runner: Runner) -> list[str]:
    """Undo every file change of a run, newest first. Returns report lines."""
    report = []
    backups = [ev for ev in journal.events() if ev["event"] == "file_backup"]
    for ev in reversed(backups):
        target = Path(ev["path"])
        root = ev.get("root", False)
        if ev["existed"]:
            src = Path(ev["backup"])
            if not src.exists():
                report.append(f"MISSING BACKUP {target}")
                continue
            if root:
                runner.run(["cp", "-a", str(src), str(target)], sudo=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            report.append(f"restored {target}")
        else:
            if root:
                runner.run(["rm", "-f", str(target)], sudo=True)
            elif target.exists():
                target.unlink()
            report.append(f"removed {target} (did not exist before)")
    journal.write("rollback", files=len(backups))
    return report
