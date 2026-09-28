"""Locks for results/ (DECISIONS 2026-09-27 — created after a rescore and a running pilot raced on
results/index.jsonl and corrupted it).

* SWEEP LOCK — ``results/.sweep.lock``: a sweep phase (agents / verify) holds it for its whole run. While a
  live process other than the holder holds it, every writer to results/ REFUSES (``assert_can_write``):
  record writes, index writes, and the rescore / rebuild scripts. A lock whose holder pid is dead on the
  same host is stale and is replaced; a lock written on a DIFFERENT host (e.g. inside the container) cannot
  be liveness-checked and is treated as live — clear it ONLY when no sweep is running, with the unlock
  command (it shows the holder and asks for confirmation):

      python -m harness.results_lock status
      python -m harness.results_lock unlock
* INDEX LOCK — ``results/.index.lock``: every read-modify-write of results/index.jsonl happens under an
  exclusive ``flock`` and is written to a temp file then renamed into place (never a torn file).
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class ResultsLocked(RuntimeError):
    """Another live process holds the sweep lock on this checkout's results/."""


UNLOCK_HINT = ("If you are CERTAIN no sweep is running (e.g. a killed run inside Docker left a lock from another "
               "host), clear it with: python -m harness.results_lock unlock")


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
        f"write into a checkout a sweep is running from (DECISIONS 2026-09-26). {UNLOCK_HINT}")


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
                                f"(pid {h.get('pid')} on {h.get('host')}, since {h.get('since')}). {UNLOCK_HINT}")
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


# --------------------------------------------------------------------------- #
# CLI — status / unlock (DECISIONS 2026-09-28)
# --------------------------------------------------------------------------- #

def unlock(root: Path, confirm=input, out=print) -> int:
    """Remove the sweep lock after showing its holder and asking the user to type the holder's sweep name.

    Refuses outright when the holder is a LIVE process on THIS host (a sweep really is running). A lock from
    another host (e.g. a killed run inside a Docker container) or an unreadable one cannot be liveness-checked,
    which is exactly when this command is needed; a stale lock (dead pid, this host) is removed after
    confirmation too. Returns a process exit code."""
    p = _lock_path(root)
    if not p.is_file():
        out(f"no sweep lock at {p}")
        return 0
    raw = p.read_text()
    try:
        info = json.loads(raw)
    except Exception:
        info = None
    if info and info.get("host") == socket.gethostname() and _alive(int(info.get("pid") or 0)):
        out(f"REFUSED: {p} is held by a LIVE process on this host (pid {info.get('pid')}, sweep "
            f"{info.get('sweep')!r} {info.get('phase')}). Stop that sweep; never unlock a running one.")
        return 1
    where = ("unreadable lock file" if info is None else
             f"sweep {info.get('sweep')!r} {info.get('phase')}, pid {info.get('pid')} on host {info.get('host')!r}, "
             f"since {info.get('since')}")
    foreign = info is not None and info.get("host") != socket.gethostname()
    out(f"sweep lock: {p}\n  holder: {where}")
    if foreign:
        out("  This lock was written on ANOTHER host (e.g. inside a container), so whether that sweep is still "
            "running cannot be checked from here.")
    out("  Remove it ONLY if you are certain no sweep is running from this checkout.")
    expected = (info or {}).get("sweep") or "UNLOCK"
    answer = confirm(f"  Type {expected!r} to remove the lock (anything else cancels): ")
    if answer.strip() != expected:
        out("cancelled — lock kept")
        return 1
    if p.read_text() != raw:
        out("REFUSED: the lock changed while waiting for confirmation — re-run status")
        return 1
    p.unlink()
    out(f"removed {p}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="results/ sweep lock: status / unlock")
    ap.add_argument("cmd", choices=["status", "unlock"])
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        p = _lock_path(a.project_root)
        h = holder(a.project_root)
        print(f"{p}: " + ("no live holder" + (" (stale lock file present)" if p.is_file() else "") if h is None
                          else json.dumps(h)))
        return 0
    return unlock(a.project_root)


if __name__ == "__main__":
    sys.exit(main())
