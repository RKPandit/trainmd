"""Locks for results/ (DECISIONS 2026-09-27 — created after a rescore and a running pilot raced on
results/index.jsonl and corrupted it).

* SWEEP LOCK — ``results/.sweep.lock``: a sweep phase (agents / verify) holds it for its whole run. While a
  live process other than the holder holds it, every writer to results/ REFUSES (``assert_can_write``):
  record writes, index writes, and the rescore / rebuild scripts. A lock whose holder pid is dead on the
  same host is stale and is replaced; a lock written on a DIFFERENT host (e.g. inside the container) cannot
  be liveness-checked and is treated as live — clear it by hand only when no sweep is running.
* INDEX LOCK — ``results/.index.lock``: every read-modify-write of results/index.jsonl happens under an
  exclusive ``flock`` and is written to a temp file then renamed into place (never a torn file).
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class ResultsLocked(RuntimeError):
    """Another live process holds the sweep lock on this checkout's results/."""


def _lock_path(root: Path) -> Path:
    return Path(root) / "results" / ".sweep.lock"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def holder(root: Path) -> dict | None:
    """The current LIVE holder's lock record, or None (no lock, or a stale one on this host)."""
    p = _lock_path(root)
    if not p.is_file():
        return None
    try:
        info = json.loads(p.read_text())
    except Exception:
        return {"pid": None, "host": "?", "sweep": "?", "unreadable": True}
    if info.get("host") == socket.gethostname() and not _alive(int(info.get("pid") or 0)):
        return None                                                     # stale (dead pid, same host)
    return info


def assert_can_write(root: Path, what: str = "write to results/") -> None:
    """Raise ResultsLocked if a live process OTHER than this one holds the sweep lock."""
    h = holder(root)
    if h is None:
        return
    if h.get("pid") == os.getpid() and h.get("host") == socket.gethostname():
        return                                                          # the holder itself
    raise ResultsLocked(
        f"refusing to {what}: sweep {h.get('sweep')!r} holds {_lock_path(root)} "
        f"(pid {h.get('pid')} on {h.get('host')}, since {h.get('since')}). Wait for it to finish — never "
        "write into a checkout a sweep is running from (DECISIONS 2026-09-26). If you are certain no sweep "
        "is running, remove the lock file by hand.")


@contextlib.contextmanager
def sweep_lock(root: Path, sweep: str, phase: str):
    """Hold the sweep lock for a sweep phase; refuse if another live process holds it."""
    p = _lock_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    mine = {"pid": os.getpid(), "host": socket.gethostname(), "sweep": sweep, "phase": phase,
            "since": datetime.now(timezone.utc).isoformat()}
    with index_lock(root):                                   # check-and-take is atomic across processes
        h = holder(root)
        if h is not None and not (h.get("pid") == os.getpid() and h.get("host") == socket.gethostname()):
            raise ResultsLocked(f"refusing to start {sweep!r} {phase}: sweep {h.get('sweep')!r} holds {p} "
                                f"(pid {h.get('pid')} on {h.get('host')}, since {h.get('since')}).")
        write_text_atomic(p, json.dumps(mine))
    try:
        yield mine
    finally:
        try:
            if json.loads(p.read_text()).get("pid") == os.getpid():
                p.unlink()
        except Exception:
            pass


@contextlib.contextmanager
def index_lock(root: Path):
    """Exclusive lock around a read-modify-write of results/index.jsonl."""
    p = Path(root) / "results" / ".index.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to a temp file beside ``path``, fsync, then rename over it (readers never see a torn
    file)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
