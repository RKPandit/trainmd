"""Silent operator: data leakage via auxiliary feature injection (spec §4).

Motivation: data-leakage faults are a distinct failure mode from hyper-parameter
misconfiguration or data corruption.  Unlike lr_warmup or label_corruption, the
visible metrics actually IMPROVE — val_acc goes UP — making this a misleading
symptom.  Only hidden-test accuracy reveals the degradation.

The fault adds a config-controlled auxiliary feature column that is correlated with
the training label.  At hidden-test time, the upstream signal is unavailable and a
pure noise column is substituted, so accuracy drops below tolerance.

Strength mapping (noise rate p — lower p = stronger leak):
- mild:     p=0.35   correlation ≈ 0.30   subtle inflation
- moderate: p=0.20   correlation ≈ 0.60   clear inflation
- severe:   p=0.05   correlation ≈ 0.90   dramatic inflation

References:
    Yang et al. "Rethinking Data Leakage" arXiv:2209.03345
    Kapoor & Narayanan, "Leakage and the Reproducibility Crisis" Patterns 2023
    CMU arXiv:2403.16795
"""
from __future__ import annotations

import json
from pathlib import Path
from random import Random
from typing import Any, Literal

import yaml

from operators.base import (
    EvidenceRef,
    IncidentOperator,
    Manifest,
    MutationRecord,
    RepairSpecSchema,
)

# Noise rate per strength tier.
_STRENGTH_P: dict[str, float] = {
    "mild": 0.35,
    "moderate": 0.20,
    "severe": 0.05,
}


class DataLeakageOperator:
    """Inject a label-derived auxiliary feature via config flags.

    Implements :class:`IncidentOperator` (spec §4).
    Layer: dynamics (silent tier — runs complete, metrics finite, visible
    accuracy *inflated* but hidden accuracy degraded below tolerance).
    """

    id: str = "silent.data_leakage.v1"
    layer: Literal["dynamics"] = "dynamics"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Set ``data.include_aux_feature`` and ``data.aux_feature_strength``.

        Args:
            workspace: Root of the workspace copy.
            rng: Seeded RNG (accepted but unused — mutation is deterministic).
            strength: One of ``mild``, ``moderate``, ``severe``.

        Returns:
            :class:`Manifest` recording the aux-feature mutation.

        Raises:
            ValueError: If *strength* is not a recognised tier.
        """
        if strength not in _STRENGTH_P:
            raise ValueError(
                f"Unknown strength {strength!r}; "
                f"expected one of {sorted(_STRENGTH_P)}"
            )

        config_path = workspace / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        p = _STRENGTH_P[strength]

        config.setdefault("data", {})["include_aux_feature"] = True
        config["data"]["aux_feature_strength"] = p

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
                    key_path="data.include_aux_feature",
                    original_value=None,
                    mutated_value=True,
                    description="Enable auxiliary feature injection",
                ),
                MutationRecord(
                    file="config.yaml",
                    key_path="data.aux_feature_strength",
                    original_value=None,
                    mutated_value=p,
                    description=(
                        f"Set auxiliary feature noise rate to {p} "
                        f"({strength} strength, correlation ≈ {1 - 2 * p:.2f})"
                    ),
                ),
            ],
        )

    def evidence(self) -> list[EvidenceRef]:
        """Structural evidence refs for this operator.

        A correct diagnosis should cite:
        1. The config key ``data.include_aux_feature`` (the root cause).
        2. The config key ``data.aux_feature_strength`` — the operator mutates
           this key too, so per the "enumerate every artifact the fault
           touches" principle it is part of the root-cause ground truth.
        3. Anomalous metric_visible_val_acc — the leaked feature inflates
           visible accuracy above the healthy reference range.

        Both mutated config keys appear here: an operator's mutated keys are
        always evidence (code_spans remain excluded as mechanism).
        """
        return [
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": "data.include_aux_feature"},
            ),
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": "data.aux_feature_strength"},
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

        The only valid repair is disabling the auxiliary feature by setting
        ``data.include_aux_feature`` to ``false``.

        IMPORTANT: ``training.lr`` is NOT in ``allowed_keys``.  An agent
        that adjusts hyperparameters instead of disabling the leaked feature
        will be rejected.
        """
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=["data.include_aux_feature"],
            allowed_values={"data.include_aux_feature": [False]},
            # Absent in clean config; unset ≡ the clean default (feature off).
            absent_when_clean_keys=["data.include_aux_feature"],
            description=(
                "Set data.include_aux_feature to false to disable the "
                "auxiliary feature, or null to unset it (delete the injected key)."
            ),
        )

    def accepted_classes(self) -> frozenset[str]:
        """Class names an agent might use to correctly identify this fault."""
        return frozenset({
            "data_leakage", "feature_leakage", "target_leakage",
            "label_leakage", "information_leakage", "train_test_leakage",
            "data_contamination", "leaky_feature",
        })

    def core_tokens(self) -> list[frozenset[str]]:
        """Concept = leakage.  ``leak`` covers leak/leakage/leaky.

        Deliberately NOT satisfied by mechanism-only labels that name the knob
        (``aux_feature_enabled``, ``aux_feature_too_strong``) without the
        concept: identification scores the fault CONCEPT; naming the knob is
        what the EVIDENCE axis credits.  See docs/DECISIONS.md.
        """
        return [frozenset({"leak"})]

    def oracle_repair(self) -> dict:
        """Reference-restoring repair: disable the leaked auxiliary feature."""
        return {
            "repair_type": "config_patch",
            "patches": {"data.include_aux_feature": False},
        }

    def build_guard_checks(self, run_output: Path, stats: dict) -> list[str]:
        """Verify misleading symptom: val_acc above upper band (mean + 2σ).

        Returns a list of error messages (empty = pass).
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
                f"val_acc={final_val_acc:.6f} not above upper band "
                f"{upper_band:.6f} (mean + 2·std); "
                f"misleading symptom not confirmed"
            ]
        return []


# Verify protocol conformance at import time.
assert isinstance(DataLeakageOperator(), IncidentOperator), (
    "DataLeakageOperator does not satisfy IncidentOperator protocol"
)
