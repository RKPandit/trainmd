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

from operators.margins import positive_symptom_bar
from operators.base import (
    EvidenceRef,
    IncidentOperator,
    Manifest,
    MutationRecord,
    RepairSpecSchema,
)

# Noise rate per strength tier.
_STRENGTH_P: dict[str, float] = {
    # p is the label-corruption fraction of the aux feature: correlation = 1 - 2p,
    # so LOWER p = STRONGER leak = higher visible inflation. mild was 0.35 (corr
    # 0.30), which sat AT the mean+2σ edge with zero margin and flaked when the
    # reference moved to the 200-229 band. Recalibrated DOWN to clear the margined
    # symptom bar (mean+4σ+1e-3, operators/margins.py).
    # 0.28 is the LARGEST p (mildest leak) that clears BOTH halves with >= 2σ+1e-3
    # on every calibration seed, per the NATIVE sweep scripts/calibrate_data_leakage.py
    # (CI run 35290173830: p=0.30 fails symptom by 0.0029; p=0.28 clears by +0.011
    # visible / +0.016 hidden). mild visible val_acc ~0.877 (plausible inflation).
    "mild": 0.28,
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

    # The two config keys this operator mutates, under ``data``.  Subclasses
    # (e.g. the neutral-key variant) override ONLY these two names + ``id`` +
    # ``WORKLOAD_FAMILY``; every method below reads the names from here, so the
    # mechanism and answer key stay identical and only the key NAME differs.
    ENABLE_KEY: str = "include_aux_feature"
    STRENGTH_KEY: str = "aux_feature_strength"
    # Workload family whose train.py reads this operator's keys.
    WORKLOAD_FAMILY: str = "tabular_adult"

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Set ``data.{ENABLE_KEY}`` and ``data.{STRENGTH_KEY}``.

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

        config.setdefault("data", {})[self.ENABLE_KEY] = True
        config["data"][self.STRENGTH_KEY] = p

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
                    key_path=f"data.{self.ENABLE_KEY}",
                    original_value=None,
                    mutated_value=True,
                    description="Enable the derived-column injection",
                ),
                MutationRecord(
                    file="config.yaml",
                    key_path=f"data.{self.STRENGTH_KEY}",
                    original_value=None,
                    mutated_value=p,
                    description=(
                        f"Set derived-column disagreement rate to {p} "
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
                detail={"key_path": f"data.{self.ENABLE_KEY}"},
            ),
            EvidenceRef(
                kind="config_key",
                artifact_id="config.yaml",
                detail={"key_path": f"data.{self.STRENGTH_KEY}"},
            ),
            EvidenceRef(
                kind="metric_window",
                artifact_id="metrics.jsonl",
                detail={
                    # Inflated across the whole run (measured: outside the healthy
                    # band on all seeds at every epoch). Evidence-v2 ground truth
                    # is a single CONTAINMENT window [0, 19] (epochs 0..19); any
                    # in-run localization is credited, out-of-run/unbounded is not.
                    "series": "metric_visible_val_acc",
                    "start_epoch": 0,
                    "end_epoch": 19,
                    "match": "contain",
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
            # Both keys the operator mutates are admissible so that unsetting
            # BOTH exactly restores clean (STAGE3 ruling 2026-09-17: every mutated
            # key must be unsettable). include_aux_feature=False alone also recovers.
            allowed_keys=[f"data.{self.ENABLE_KEY}", f"data.{self.STRENGTH_KEY}"],
            allowed_values={f"data.{self.ENABLE_KEY}": [False]},
            # Absent in clean config; unset ≡ the clean default (feature off).
            absent_when_clean_keys=[f"data.{self.ENABLE_KEY}", f"data.{self.STRENGTH_KEY}"],
            description=(
                f"Set data.{self.ENABLE_KEY} to false to disable the injected "
                f"column, or null to unset it (delete the injected key)."
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

    def off_concept_vetoes(self) -> frozenset[str]:
        """Off-concept uses of the token ``leak`` that are NOT data leakage.

        A memory/resource/gradient leak is an execution or numerical fault, not
        train/eval contamination.  Vetoed on the token path (root_token_v2) even
        though the token ``leak`` is present.  See docs/DECISIONS.md 2026-09-22.
        """
        return frozenset({
            "memory_leak", "memory_leakage", "ram_leak", "vram_leak",
            "gpu_memory_leak", "gpu_leak", "resource_leak", "gradient_leak",
            "buffer_leak", "socket_leak", "connection_leak", "file_handle_leak",
            "handle_leak", "fd_leak",
        })

    def oracle_repair(self) -> dict:
        """Reference-restoring repair: disable the injected column."""
        return {
            "repair_type": "config_patch",
            "patches": {f"data.{self.ENABLE_KEY}": False},
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
        # Structural margin rule (operators/margins.py, DECISIONS 2026-09-17):
        # the misleading symptom must clear the band edge by >= 2σ + 1e-3.
        bar = positive_symptom_bar(stats)
        if final_val_acc < bar:
            return [
                f"val_acc={final_val_acc:.6f} below margined symptom bar "
                f"{bar:.6f} (mean + 4·std + 1e-3); misleading symptom lacks "
                f"the required >= 2σ + 1e-3 margin"
            ]
        return []


# Verify protocol conformance at import time.
assert isinstance(DataLeakageOperator(), IncidentOperator), (
    "DataLeakageOperator does not satisfy IncidentOperator protocol"
)
