"""Non-LLM baselines (STAGE3_PLAN v3 Part 1) — free floor contestants.

Each baseline is scored by the SAME path as an agent (``harness.scoring``), reading
ONLY the agent-visible surface (never the hidden card). They test whether the LLM's
value clears a trivial floor on detection, and expose where it does not.

- **B1 band detector** — flags if the visible metric leaves the supplied band. CRASH-AWARE:
  a run with no metrics has nothing out of band, so ``detected=False`` is the correct answer
  to "is a monitored metric out of band," not a miss. A band monitor is structurally blind to
  crashes; report B1 detection split crash / non-crash.
- **B2 config-delta** — flags a non-default / newly-present config key; identification = that
  key's leaf name (scored against the operator's ``core_tokens`` exactly like an agent, so
  config-legibility is measured), evidence = a ``config_key`` ref, repair = reset it to clean
  (or unset if absent-when-clean).
- **B3 union** — B1 OR B2; identification/evidence/repair from B2 when it fires, else B1's
  evidence only.
- **B4 REFERENCE-INFORMED ORACLE** — ``max|z|`` of the visible metric vs the reference mean/sd,
  a swept-threshold ROC. It has reference knowledge no anchor-off agent has, so it is an UPPER
  BOUND on a threshold detector, NOT a fair off-arm opponent — labelled as such wherever it
  appears. (B1's arm-conditional variant, ``b1(surface, band=arm_band)``, is the FAIR opponent
  for the stats/rule arms.)
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import yaml

# --------------------------------------------------------------------------- #
# Visible-only read surface (never the hidden card)
# --------------------------------------------------------------------------- #

_FORBIDDEN_TOKENS = ("/hidden/", "card.hidden", "verify.yaml", "evidence.yaml")


class HiddenAccessError(PermissionError):
    """A baseline attempted to read a hidden (answer-key) artifact."""


class VisibleSurface:
    """The single read gate for a baseline: only agent-visible artifacts.

    Any path resolving under ``hidden/`` (or a hidden filename) raises — a baseline
    that tries to read the answer key fails here (test-enforced)."""

    def __init__(self, case_dir, project_root=None):
        self.case_dir = Path(case_dir).resolve()
        self.project_root = (Path(project_root).resolve() if project_root
                             else self.case_dir.parents[1])

    def _read(self, rel: str) -> str:
        rp = (self.case_dir / rel).resolve()
        low = str(rp).lower().replace("\\", "/")
        if any(tok in low for tok in _FORBIDDEN_TOKENS):
            raise HiddenAccessError(f"baseline may not read hidden artifact: {rel}")
        return rp.read_text()

    def epochs(self) -> list[dict]:
        try:
            text = self._read("workspace/run_output/metrics.jsonl")
        except FileNotFoundError:
            return []
        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("end_of_epoch") and "metric_visible_val_acc" in r:
                rows.append(r)
        return rows

    def val_acc_series(self) -> list[tuple[int, float]]:
        return [(e["epoch"], e["metric_visible_val_acc"]) for e in self.epochs()]

    def is_crash(self) -> bool:
        """No visible metric series -> the band monitor is structurally blind (crash tier)."""
        return not self.epochs()

    def public_band(self) -> tuple[float | None, float | None]:
        card = yaml.safe_load((self.case_dir / "card.public.yaml").read_text())
        rv = card.get("reference_visible_metric", {}) or {}
        return rv.get("mean"), rv.get("std")

    def resolved_config(self) -> dict:
        for rel in ("workspace/run_output/config.resolved.yaml", "workspace/config.yaml"):
            try:
                return yaml.safe_load(self._read(rel)) or {}
            except FileNotFoundError:
                continue
        return {}

    def clean_config(self) -> dict:
        wl = (self.resolved_config().get("workload", {}) or {}).get("name", "tabular_adult")
        p = self.project_root / "workloads" / wl / "config.yaml"
        return yaml.safe_load(p.read_text()) or {}


# --------------------------------------------------------------------------- #
# Submission / evidence helpers (same shapes an agent emits)
# --------------------------------------------------------------------------- #

def _sub(detected, operator_class="none", evidence=None, repair=None) -> dict:
    return {
        "diagnosis": {"detected": bool(detected), "operator_class": operator_class},
        "evidence_refs": evidence or [],
        "repair_spec": repair,
    }


def _metric_window(series, start, end) -> dict:
    return {"kind": "metric_window", "artifact_id": "metrics.jsonl",
            "detail": {"series": series, "start_epoch": start, "end_epoch": end}}


def _config_key(key_path) -> dict:
    return {"kind": "config_key", "artifact_id": "config.yaml", "detail": {"key_path": key_path}}


# --------------------------------------------------------------------------- #
# Config diff (B2)
# --------------------------------------------------------------------------- #

# Keys added by train.py at resolution time (not fault knobs); the reference block
# is not a training knob. Excluded so B2 flags only operator mutations.
_IGNORE_KEYS = {"seed", "model.input_dim"}
_IGNORE_SECTIONS = {"reference"}


def _flatten(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                out.update(_flatten(v, key + "."))
            else:
                out[key] = v
    return out


def _config_deltas(resolved: dict, clean: dict) -> list[tuple[str, object]]:
    """(key_path, clean_value_or_None) for keys that differ or are newly present.
    clean_value is None when the key is absent-when-clean (repair = unset)."""
    rf, cf = _flatten(resolved), _flatten(clean)
    deltas = []
    for k, v in sorted(rf.items()):
        if k in _IGNORE_KEYS or k.split(".")[0] in _IGNORE_SECTIONS:
            continue
        if k not in cf:
            deltas.append((k, None))            # newly present -> unset to clean
        elif v != cf[k]:
            deltas.append((k, cf[k]))           # changed -> reset to clean value
    return deltas


# --------------------------------------------------------------------------- #
# The baselines
# --------------------------------------------------------------------------- #

def b1(surface: VisibleSurface, band: tuple[float, float] | None = None) -> dict:
    """Band detector. `band` overrides the public-card band (arm-conditional variant)."""
    series = surface.val_acc_series()
    if not series:                               # crash: no metric -> correctly not detected
        return _sub(False)
    if band is None:
        mean, std = surface.public_band()
        band = (mean - 2 * std, mean + 2 * std)
    lo, hi = band
    oob = [(ep, v) for ep, v in series if not (lo <= v <= hi)]
    if not oob:
        return _sub(False)
    return _sub(True, evidence=[_metric_window("metric_visible_val_acc", oob[0][0], oob[-1][0])])


def b2(surface: VisibleSurface) -> dict:
    """Config-delta heuristic."""
    deltas = _config_deltas(surface.resolved_config(), surface.clean_config())
    if not deltas:
        return _sub(False, repair={"repair_type": "none", "patches": {}})
    key, clean_val = deltas[0]
    return _sub(True,
                operator_class=key.split(".")[-1],          # leaf name -> scored vs core_tokens
                evidence=[_config_key(key)],
                repair={"repair_type": "config_patch", "patches": {key: clean_val}})


def b3(surface: VisibleSurface, band: tuple[float, float] | None = None) -> dict:
    """Union: detected if B1 or B2; identification/evidence/repair from B2 when it fires."""
    s2 = b2(surface)
    if s2["diagnosis"]["detected"]:
        return s2
    s1 = b1(surface, band)
    return s1                                    # detected iff B1 fired; evidence only, no id/repair


def b4_max_z(surface: VisibleSurface) -> float | None:
    """REFERENCE-INFORMED ORACLE detection score: max|z| vs reference mean/sd. None on crash."""
    series = surface.val_acc_series()
    if not series:
        return None
    mean, std = surface.public_band()
    if not std:
        return None
    return max(abs((v - mean) / std) for _, v in series)


def b4_roc(scores: list[tuple[float | None, bool]]) -> dict:
    """ROC/AUC over (max_z, is_faulty). Crash (None) counts as not-detected at every threshold.
    AUC via the Mann-Whitney rank statistic (ties = 0.5)."""
    pos = [s for s, f in scores if f]            # faulty
    neg = [s for s, f in scores if not f]        # control
    if not pos or not neg:
        return {"available": False, "reason": "need both faulty and control cases"}

    def _cmp(a, b):
        # None (crash) ranks below any real score
        if a is None and b is None:
            return 0.5
        if a is None:
            return 0.0
        if b is None:
            return 1.0
        return 1.0 if a > b else (0.5 if a == b else 0.0)

    wins = sum(_cmp(p, n) for p in pos for n in neg)
    auc = wins / (len(pos) * len(neg))
    reals = sorted({s for s, _ in scores if s is not None})
    roc = []
    for t in [-float("inf")] + reals:
        tp = sum(1 for s in pos if s is not None and s > t)
        fp = sum(1 for s in neg if s is not None and s > t)
        roc.append({"z": t, "tpr": tp / len(pos), "fpr": fp / len(neg)})
    return {"available": True, "auc": round(auc, 4), "n_faulty": len(pos),
            "n_control": len(neg), "roc": roc, "note": "REFERENCE-INFORMED ORACLE — upper bound"}


def operating_point_for_rate(roc: list[dict], target_tpr: float) -> dict | None:
    """The z-threshold whose TPR is closest to `target_tpr` (the LLM's detection rate)."""
    if not roc:
        return None
    return min(roc, key=lambda r: abs(r["tpr"] - target_tpr))


# --------------------------------------------------------------------------- #
# Scoring — the SAME scorer as an agent (baseline reads visible; scorer reads hidden)
# --------------------------------------------------------------------------- #

_BASELINES = {"b1": b1, "b2": b2, "b3": b3}


def score_baseline(case_dir, name, band=None, project_root=None) -> tuple[dict, dict]:
    """Build a baseline submission from the VISIBLE surface, then grade it with the
    standard scorer (which legitimately reads the hidden card). Returns (submission, scores)."""
    from harness.scoring import score_diagnosis
    surface = VisibleSurface(case_dir, project_root)
    fn = _BASELINES[name]
    submission = fn(surface, band) if name in ("b1", "b3") else fn(surface)
    scores = score_diagnosis({"submission": submission, "tool_transcript": []}, Path(case_dir))
    return submission, scores


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description="Non-LLM baselines (STAGE3_PLAN Part 1)")
    ap.add_argument("--baseline", choices=["b1", "b2", "b3", "b4"], required=True)
    ap.add_argument("--cases", default="cases/case_*", help="glob for case dirs")
    ap.add_argument("--project-root", type=Path, default=None)
    args = ap.parse_args()

    root = args.project_root or Path.cwd()
    case_dirs = sorted(Path(p) for p in glob.glob(str(root / args.cases))
                       if (Path(p) / "card.public.yaml").exists())
    if not case_dirs:
        print(f"no cases matched {args.cases}", file=sys.stderr)
        return 1

    if args.baseline == "b4":
        # detection ROC only; tier from the VISIBLE surface (crash = no metrics)
        rows = []
        for cd in case_dirs:
            s = VisibleSurface(cd, root)
            # a case is "faulty" iff not a control — but the baseline may not read the tier.
            # For the CLI summary we read the (public) registry-free heuristic: control cards
            # have no distinguishing public field, so faulty/control labelling is supplied by
            # the caller in the real pipeline. Here we just print per-case max|z|.
            print(f"{cd.name}\tmax_z={b4_max_z(s)}")
        return 0

    for cd in case_dirs:
        submission, scores = score_baseline(cd, args.baseline, project_root=root)
        det = scores["detection"]
        print(f"{cd.name}\tdetected={det['detected_predicted']}\tcorrect={det['correct']}"
              f"\tid={scores['identification']['correct']}\tevF1={scores['evidence']['f1']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
