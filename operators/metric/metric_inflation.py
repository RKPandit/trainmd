"""Metric-tier operator: inflated validation metric via a biased computation (spec §4).

Motivation — the SECOND positive-symptom operator, of a genuinely different KIND
from data_leakage. Where data_leakage inflates the visible metric by giving the
MODEL a label-derived feature (the model really is different), this operator
leaves the model, its training, and its saved checkpoint BITWISE identical to a
clean run and only computes the REPORTED validation accuracy incorrectly: it is
measured on the most-confident fraction q of validation rows (by |logit|, an
innocuous criterion available at evaluation time — NOT the labels) rather than on
the full split. Selective evaluation reads far above the healthy band while the
model is fine; hidden-test accuracy, always computed correctly on the full split
by the evaluator, stays inside the band.

This exists to test "positive-symptom under-detection" as a property of symptom
DIRECTION rather than of one operator (breaks the L9 symptom↔operator confound):
same misleading direction as data_leakage (visible looks BETTER than healthy),
different mechanism (a biased metric, not a leaked feature), and — new for this
tier — a healthy model.

Layer: metric (observability). Build guard: visible ABOVE mean+2σ AND hidden
WITHIN band. Recovery: restore the correct computation (evaluate the full split);
the reported metric returns into the band and hidden stays in band.

KNOWN WITHIN-CASE SIGNAL (kept deliberately — the realistic version of this bug).
Only the reported ACCURACY is computed on the confidence subset; ``val_loss`` is
still computed on the FULL validation split (train.py is unchanged there). So an
epoch row can read a normal loss (≈0.30) next to an inflated accuracy (≈0.94–0.98)
— internally inconsistent numbers an agent could flag with NO external baseline. A
subset-accuracy bug plausibly would not touch the loss, so this is the faithful
form; we do not "fix" it by biasing the loss too. But it means this operator is NOT
matched to data_leakage on within-case detectability (data_leakage has no such
internal contradiction — the model genuinely learned the feature, so its loss and
accuracy agree). See docs/DECISIONS.md and docs/LIMITATIONS.md (L16); a matched
variant (loss computed on the same subset) is a Sweep-3 pre-registration candidate
in docs/HYPOTHESES.md.

Strength mapping (fraction q of the most-confident val rows KEPT; smaller q =
stronger inflation). The kept sets are nested by construction — all three q take a
prefix of ONE confidence ordering, so keep(0.50) ⊆ keep(0.70) ⊆ keep(0.92) — a
monotone ladder. The ladder deliberately SPANS a PLAUSIBLE → IMPLAUSIBLE reported
metric so a sweep can measure whether detection depends on the MAGNITUDE of the
inflation, not only its direction: the mild rung sits in the same plausible regime
as data_leakage's inflated ~0.90, so this operator probes the same detection
question rather than an obviously-impossible number. Calibrated on seeds {0,1,2}
(scripts/calibrate_metric_inflation.py); every rung clears mean+2σ by >=2σ (min
reported ≥ mean+4σ) with the model healthy and the checkpoint identical to clean:
- mild:     q=0.92  → reported ≈ 0.88  (plausible; margin +0.021, ~14σ over edge)
- moderate: q=0.70  → reported ≈ 0.94
- severe:   q=0.50  → reported ≈ 0.98

References:
    Roth et al., "Selective Prediction and Metric Inflation" arXiv:2604.04199
    Kapoor & Narayanan, "Leakage and the Reproducibility Crisis" Patterns 2023
"""
from __future__ import annotations

import json
from pathlib import Path
from random import Random
from typing import Literal

import yaml

from operators.base import (
    EvidenceRef,
    IncidentOperator,
    Manifest,
    MutationRecord,
    RepairSpecSchema,
)

# Fraction of the most-confident validation rows the reported metric keeps.
# Smaller = stronger inflation.  Calibrated on all seeds in Step 0.
_STRENGTH_Q: dict[str, float] = {
    "mild": 0.92,      # reported ≈ 0.88 — PLAUSIBLE (cf. data_leakage's ~0.90)
    "moderate": 0.70,  # reported ≈ 0.94
    "severe": 0.50,    # reported ≈ 0.98 — implausible end of the span
}

_KNOB = "metrics.eval_subset_fraction"


class MetricInflationOperator:
    """Compute the reported validation metric on a confidence-selected subset.

    Implements :class:`IncidentOperator` (spec §4).
    Layer: metric (observability tier — run completes, model healthy/hidden
    within band, but the reported visible accuracy is inflated above the band).
    """

    id: str = "silent.metric_inflation.v1"
    layer: Literal["metric"] = "metric"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Set ``metrics.eval_subset_fraction`` to the strength's q.

        Args:
            workspace: Root of the workspace copy.
            rng: Seeded RNG (accepted but unused — the fault is deterministic;
                the confidence ordering is model-derived, so there is no
                injected randomness at all).
            strength: One of ``mild``, ``moderate``, ``severe``.

        Returns:
            :class:`Manifest` recording the single config mutation.

        Raises:
            ValueError: If *strength* is not a recognised tier.
        """
        if strength not in _STRENGTH_Q:
            raise ValueError(
                f"Unknown strength {strength!r}; "
                f"expected one of {sorted(_STRENGTH_Q)}"
            )

        config_path = workspace / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        q = _STRENGTH_Q[strength]
        config.setdefault("metrics", {})["eval_subset_fraction"] = q

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return Manifest(
            operator_id=self.id,
            layer=self.layer,
            strength=strength,
            seed=0,  # deterministic — seed unused
            mutations=[
                MutationRecord(
                    file="config.yaml",
                    key_path=_KNOB,
                    original_value=None,
                    mutated_value=q,
                    description=(
                        f"Report validation accuracy on the most-confident "
                        f"{q:.0%} of rows instead of the full split "
                        f"({strength} strength)"
                    ),
                ),
            ],
        )

    def evidence(self) -> list[EvidenceRef]:
        """Structural evidence refs for this operator.

        A correct diagnosis should cite:
        1. The config key ``metrics.eval_subset_fraction`` (the mutated knob —
           an operator's mutated keys are always evidence ground truth).
        2. The inflated ``metric_visible_val_acc`` series.

        code_spans are excluded (minimal-sufficient rule): reading the biased
        computation in train.py is a fair third signal but is not required
        ground truth, exactly as for data_leakage.
        """
        return [
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": _KNOB},
            ),
            EvidenceRef(
                kind="metric_window",
                artifact_id="metrics.jsonl",
                detail={
                    "series": "metric_visible_val_acc",
                    "start_epoch": 0,
                },
            ),
        ]

    def admissible_repairs(self) -> RepairSpecSchema:
        """Schema of valid repairs.

        The correct repair restores the correct computation — evaluate the FULL
        validation split — by setting ``metrics.eval_subset_fraction`` to 1.0
        (keep every row) or unsetting it (delete the injected key so the workload
        falls back to the full split). Both are oracle-equivalent.
        """
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=[_KNOB],
            allowed_values={_KNOB: [1.0]},
            # Absent in the clean config; unset ≡ the clean default (full split).
            absent_when_clean_keys=[_KNOB],
            description=(
                "Set metrics.eval_subset_fraction to 1.0 (report the full "
                "validation split), or null to unset it (delete the injected key)."
            ),
        )

    def accepted_classes(self) -> frozenset[str]:
        """Class names an agent might use to correctly identify this fault."""
        return frozenset({
            "metric_inflation", "inflated_metric", "biased_metric",
            "biased_evaluation", "evaluation_bias", "selective_evaluation",
            "cherry_picked_evaluation", "misleading_metric",
            "metric_misreporting", "validation_metric_bias",
            "non_representative_evaluation", "overstated_accuracy",
            "evaluation_on_easy_subset",
        })

    def core_tokens(self) -> list[frozenset[str]]:
        """Concept = the reported metric / evaluation is inflated or biased.

        One group (OR within). Deliberately NOT satisfied by labels that name
        only the mechanism knob (``eval_subset_fraction``, ``subset``) without
        the concept: identification scores the fault CONCEPT (the metric is
        inflated / the evaluation is biased); naming the knob is what the
        EVIDENCE axis credits. Stems chosen not to collide with any other
        operator's tokens (lr / label+nois / leak / shape+dim / none). See
        docs/DECISIONS.md.
        """
        return [frozenset({
            "inflat", "bias", "cherry", "selective", "overstat",
            "misreport", "misleading", "unrepresentative", "skew",
        })]

    def oracle_repair(self) -> dict:
        """Reference-restoring repair: unset the knob (report the full split)."""
        return {
            "repair_type": "config_patch",
            "patches": {_KNOB: None},
        }

    def build_guard_checks(self, run_output: Path, stats: dict) -> list[str]:
        """Verify the misleading symptom: reported val_acc above mean + 2σ.

        The hidden-within-band half of the metric-tier guard is enforced in
        build_case (it has the hidden accuracy); here we confirm the visible
        half from the produced metrics. Returns a list of error messages
        (empty = pass).
        """
        metrics_path = run_output / "metrics.jsonl"
        with open(metrics_path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        epoch_lines = [l for l in lines if l.get("end_of_epoch")]
        if not epoch_lines:
            return ["No epoch-level metrics found"]
        final_val_acc = epoch_lines[-1].get("metric_visible_val_acc", 0.0)
        ref_mean = stats["metric_visible_val_acc"]["mean"]
        ref_std = stats["metric_visible_val_acc"]["std"]
        upper_band = ref_mean + 2 * ref_std
        if final_val_acc <= upper_band:
            return [
                f"reported val_acc={final_val_acc:.6f} not above upper band "
                f"{upper_band:.6f} (mean + 2·std); "
                f"misleading symptom not confirmed"
            ]
        return []


# Verify protocol conformance at import time.
assert isinstance(MetricInflationOperator(), IncidentOperator), (
    "MetricInflationOperator does not satisfy IncidentOperator protocol"
)
