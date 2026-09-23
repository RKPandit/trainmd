"""Non-LLM baselines (STAGE3_PLAN v3 Part 1) — free floor contestants.

Each baseline is scored by the SAME path as an agent (``harness.scoring``), reading
ONLY the agent-visible surface (never the hidden card). They test whether the LLM's
value clears a trivial floor on detection, and expose where it does not.

- **B1 band detector** — flags if the visible metric leaves the supplied band. CRASH-AWARE:
  a run with no metrics has nothing out of band, so ``detected=False`` is the correct answer
  to "is a monitored metric out of band," not a miss. A band monitor is structurally blind to
  crashes; report B1 detection split crash / non-crash.
- **B2 config-delta** — diffs the run's RESOLVED config against a committed clean RESOLVED
  reference (``reference/config.resolved.yaml``) and flags any changed / newly-present key.
  **B2 carries two pieces of WORKLOAD-SPECIFIC knowledge that a generic config-diff does NOT
  have, and this must be stated wherever B2 is compared to an agent:** (1) the clean resolved
  config (so a per-case value is judged against a known-good baseline, not guessed), and (2)
  which keys are DERIVED (``_DERIVED_KEYS`` — e.g. ``model.input_dim`` is a function of the
  data schema, so a leakage-added column bumps it as a *consequence*, not a knob). B2 keeps a
  derived key in the repair only when it is the SOLE delta (the injected knob itself, as in
  shape_mismatch); otherwise it resets the root-cause knobs and lets train.py re-derive it.
  This is defensible — a real remediation tool learns which keys are derived — but it is
  knowledge, not triviality, and is disclosed as such. identification = the changed key's leaf
  name (scored against the operator's ``core_tokens`` exactly like an agent, so
  config-legibility is measured); evidence = ``config_key`` refs for ALL reset knobs; repair =
  reset every changed knob to clean (unset if absent-when-clean).
- **B2+ — UPPER BOUND, NOT A BASELINE: "config-diff with perfect knob semantics"** (STAGE4
  4.0.6) — B2 exactly (same deltas, evidence and repair), but identification maps the changed knob
  through ``harness/b2plus_map.yaml``: the ANSWER KEY, i.e. exactly the knobs our operators inject
  (test-enforced). For our own operators its identification is therefore perfect BY CONSTRUCTION;
  it bounds what config-diffing achieves when every injected knob's meaning is known, and is never
  a baseline an LLM is compared against to claim value. Any other changed knob (a benign setting,
  a future operator's knob) FALLS BACK to B2's leaf name; ``b2plus_map_hit`` records which, and the
  fallback rate is what ``scripts/b2plus_report.py`` reports.
- **BF form-only comparator** (STAGE4 4.0.6) — flags iff the resolved config has a key the clean
  resolved reference does NOT (a newly-present key), ignoring whether an existing value changed.
  Four of the five fault operators ADD a key, so BF quantifies how far the edit's FORM alone
  separates faults from benign changes; benign false positives are reported separately for new-key
  and changed-value benign cases. A comparator, not a contestant.
- **B0 exitcode** — the trivially honest crash detector: detected iff the process exited
  nonzero. Detection-only floor (no identification/evidence/repair); a band/config monitor is
  structurally blind to crashes, B0 is not.
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

    def reference_resolved_config(self) -> dict:
        """The clean RESOLVED config committed beside the reference stats
        (`reference/config.resolved.yaml`). B2 diffs resolved-vs-resolved against
        this so that train.py-written keys (e.g. model.input_dim) are present on
        BOTH sides — no longer a spurious delta on every case. Falls back to the
        source config for old checkouts that lack the reference resolved file."""
        wl = (self.resolved_config().get("workload", {}) or {}).get("name", "tabular_adult")
        p = self.project_root / "workloads" / wl / "reference" / "config.resolved.yaml"
        try:
            return yaml.safe_load(p.read_text()) or {}
        except FileNotFoundError:
            return self.clean_config()

    def exitcode(self):
        """Process exit code (None if unavailable). Nonzero == crash (B0)."""
        try:
            return int(self._read("workspace/run_output/exitcode").strip())
        except (FileNotFoundError, ValueError):
            return None


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

# `seed` legitimately differs per case (not a fault); the reference block is not a
# training knob. model.input_dim is NO LONGER ignored: B2 diffs resolved-vs-resolved
# against reference/config.resolved.yaml, where input_dim is present on both sides,
# so a mutated input_dim (shape_mismatch) is a real delta, not a per-case artifact.
_IGNORE_KEYS = {"seed"}
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


# Keys train.py DERIVES from the data (present in resolved, not an independent knob).
# They shift as a CONSEQUENCE of a root-cause change (e.g. an added leakage column
# bumps model.input_dim), so B2 keeps them only when they are the SOLE delta — i.e.
# the injected knob itself (shape_mismatch). Otherwise they are dropped from the
# repair/identification (resetting the root cause makes train.py re-derive them).
_DERIVED_KEYS = {"model.input_dim"}


def b2(surface: VisibleSurface) -> dict:
    """Config-delta heuristic: diff the run's RESOLVED config against the clean
    RESOLVED reference. A config-delta remediation resets ALL changed knobs to
    clean (not just the first) — that is what the delta *is*."""
    deltas = _config_deltas(surface.resolved_config(), surface.reference_resolved_config())
    if not deltas:
        return _sub(False, repair={"repair_type": "none", "patches": {}})
    non_derived = [(k, v) for k, v in deltas if k not in _DERIVED_KEYS]
    effective = non_derived if non_derived else deltas   # derived-only == the injected knob
    patches = {k: v for k, v in effective}
    return _sub(True,
                operator_class=effective[0][0].split(".")[-1],  # leaf -> scored vs core_tokens
                evidence=[_config_key(k) for k, _ in effective],
                repair={"repair_type": "config_patch", "patches": patches})


B2PLUS_MAP_PATH = Path(__file__).resolve().parent / "b2plus_map.yaml"


def load_b2plus_map(path: Path = B2PLUS_MAP_PATH) -> dict[str, str]:
    """The answer-key knob→concept table (``knobs``) — see harness/b2plus_map.yaml."""
    return dict((yaml.safe_load(Path(path).read_text()) or {}).get("knobs") or {})


def b2plus(surface: VisibleSurface, knob_map: dict[str, str] | None = None) -> dict:
    """UPPER BOUND — config-diff with perfect knob semantics (B2 + the answer-key knob map).

    Deltas, evidence and repair are B2's, unchanged; only ``operator_class`` differs: the concept
    of B2's identifying key (the first effective delta), or B2's leaf name if that key is unmapped.
    """
    sub = b2(surface)
    if not sub["diagnosis"]["detected"]:
        return sub
    knob_map = load_b2plus_map() if knob_map is None else knob_map
    key = sub["evidence_refs"][0]["detail"]["key_path"]  # B2's identifying key (first effective delta)
    concept = knob_map.get(key)
    sub["diagnosis"]["operator_class"] = concept or sub["diagnosis"]["operator_class"]
    sub["b2plus_map_hit"] = concept is not None
    return sub


def bform(surface: VisibleSurface) -> dict:
    """Form-only comparator: detected iff some delta key is NEWLY PRESENT (absent from the clean
    resolved reference). Evidence = those keys; no identification, no repair."""
    ref = _flatten(surface.reference_resolved_config())
    new_keys = [k for k, _ in _config_deltas(surface.resolved_config(), surface.reference_resolved_config())
                if k not in ref and k not in _DERIVED_KEYS]
    return _sub(bool(new_keys), evidence=[_config_key(k) for k in new_keys])


def b0(surface: VisibleSurface) -> dict:
    """B0 exitcode detector — the trivially honest crash detector. detected iff the
    process exited nonzero. Detection-only floor: no identification/evidence/repair."""
    ec = surface.exitcode()
    return _sub(ec is not None and ec != 0)


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

_BASELINES = {"b0": b0, "b1": b1, "b2": b2, "b2plus": b2plus, "b3": b3, "bform": bform}


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
    ap.add_argument("--baseline", choices=["b0", "b1", "b2", "b2plus", "b3", "b4", "bform"],
                    required=True)
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
