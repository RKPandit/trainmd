#!/usr/bin/env python3
"""Build harness/price_table_history.json — every distinct price table in git history.

R8 (harness/audit_index.py) recomputes each trial's cost from the price table it was priced with.
Records carry either ``usage.price_table_version`` (a content hash, from 2026-09-23) or only their
``harness_git_commit``. Reconstructing a table from a commit needs git, which the canonical container
does not ship — so this script snapshots history ONCE (on a host with git) into a committed archive:

  {"tables":  {version_hash: table},          # every distinct _PRICE_TABLE ever committed
   "commits": {commit_sha: version_hash}}     # every commit whose tree has harness/pricing.py

R8 then resolves tables with no git at all. Re-run this whenever ``_PRICE_TABLE`` changes (a test
fails CI until the current table's version is in the archive). Tables are PARSED (ast.literal_eval),
never executed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.pricing import _PRICE_TABLE, _table_at_commit, table_version  # noqa: E402

OUT = ROOT / "harness" / "price_table_history.json"


def main() -> int:
    shas = subprocess.run(["git", "rev-list", "--all"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.split()
    tables, commits = {}, {}
    for sha in shas:
        t = _table_at_commit(sha)
        if t is None:
            continue
        v = table_version(t)
        tables.setdefault(v, t)
        commits[sha] = v
    cur = table_version(_PRICE_TABLE)
    tables.setdefault(cur, _PRICE_TABLE)      # the working tree's table (may not be committed yet)
    OUT.write_text(json.dumps({"tables": dict(sorted(tables.items())),
                               "commits": dict(sorted(commits.items()))},
                              indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(tables)} distinct table(s) over {len(commits)} commit(s); "
          f"current version {cur}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
