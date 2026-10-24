"""Small cross-process lock used by update and training jobs.

The Windows scheduler and cron each prevent overlap within one job definition, but
they do not prevent an update and a retrain from running at the same time.  This
lock is deliberately filesystem-only so it works on Windows and Unix without an
extra dependency.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class OperationLocked(RuntimeError):
    """Another BADIA daily operation still owns the shared lock."""


@contextmanager
def operation_lock(path: Path, *, operation: str, stale_after_s: float = 6 * 3600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            age = time.time() - path.stat().st_mtime
            if attempt == 0 and age > stale_after_s:
                path.unlink(missing_ok=True)
                continue
            try:
                owner = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                owner = {"detail": "unreadable lock"}
            raise OperationLocked(f"daily operation already running: {owner}")
    else:  # pragma: no cover - defensive; loop either breaks or raises
        raise OperationLocked("could not acquire daily operation lock")

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "operation": operation,
                       "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, stream)
        yield
    finally:
        path.unlink(missing_ok=True)
