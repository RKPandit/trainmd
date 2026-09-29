"""Silent operator (image workload): a learning-rate step decay whose interval is counted in the wrong unit —
design §2 #4 (as built 2026-09-28).

The clean config trains at a constant learning rate. The fault ADDS a step-decay schedule (``sched.decay_every: 1``,
``sched.decay_gamma: γ``) whose interval is counted in optimizer STEPS instead of epochs
(``sched.interval_unit: steps``; ``train.py::_lr_now``), so the rate falls by γ every step — to ≈ 0 within the first
epoch — and training stalls: a smooth, GRADED under-training (visible and hidden degrade), not workload 1's
bimodal divergence. The two workloads' learning-rate faults are DIFFERENT mechanisms, compared at the family level
only (author's decision 2026-09-28).

Strengths (γ closer to 1 = milder), rule-v2 ladder on development seeds 0–5 (docs/audits/part3_calibration.md;
DECISIONS 2026-09-29): mild γ = 0.97 (worst seed hidden 0.0233 under its bar), moderate 0.90, severe 0.80.

Identification: this operator's OWN concept — a learning-rate SCHEDULE / decay fault: the label must name the
learning rate AND a schedule / decay term, or (alternatives) the learning rate AND "too low" / "vanishing". The workload-1 learning-rate concept is NOT widened (that would change
workload-1 scoring after the freeze), and identification uniqueness is judged within each workload's own operator
set (operators/registry.py, workload groups), so the two concepts never meet.
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

from operators.base import EvidenceRef, IncidentOperator, Manifest, RepairSpecSchema
from operators.image.common import VISIBLE_SERIES, WORKLOAD_FAMILY, check_strength, config_key, edit_config, window

_STRENGTH_GAMMA: dict[str, float] = {"mild": 0.97, "moderate": 0.90, "severe": 0.80}
_EVERY, _GAMMA, _UNIT = "sched.decay_every", "sched.decay_gamma", "sched.interval_unit"


class DecayUnitOperator:
    """Add a per-step learning-rate decay that should have been per-epoch (image workload)."""

    id: str = "silent.decay_unit.v1"
    layer: Literal["dynamics"] = "dynamics"
    WORKLOAD_FAMILY: str = WORKLOAD_FAMILY
    # The read of sched.decay_every + the block it gates, and the schedule function that applies the unit.
    CODE_PATH = (("train.py", "reads", "decay_every"), ("train.py", "function", "_lr_now"))

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        check_strength(strength, _STRENGTH_GAMMA)
        g = _STRENGTH_GAMMA[strength]
        muts = edit_config(workspace, {_EVERY: 1, _GAMMA: g, _UNIT: "steps"},
                           f"Decay the learning rate by {g} every 1 interval, counted in optimizer steps "
                           f"({strength})")
        return Manifest(operator_id=self.id, layer=self.layer, strength=strength, seed=0, mutations=muts)

    def evidence(self) -> list[EvidenceRef]:
        """The three added keys; the logged learning rate, training loss and visible top-1 across the run (the
        ``lr`` series is the fault's direct trace: it falls towards zero within the first epoch)."""
        return [config_key(_EVERY), config_key(_GAMMA), config_key(_UNIT),
                window("lr"), window("train_loss"), window(VISIBLE_SERIES)]

    def admissible_repairs(self) -> RepairSpecSchema:
        """Unset the schedule (null on any of the added keys; the clean run has none), count the interval in
        epochs, or make the decay factor 1.0. Whether a repair RECOVERS is measured by the evaluator."""
        return RepairSpecSchema(
            repair_type="config_patch",
            allowed_keys=[_EVERY, _GAMMA, _UNIT],
            value_ranges={_GAMMA: (1.0, 1.0)},
            allowed_values={_UNIT: ["epochs"], _EVERY: []},          # decay_every: unset (null) only
            absent_when_clean_keys=[_EVERY, _GAMMA, _UNIT],
            description=(f"Set {_UNIT} to 'epochs' or {_GAMMA} to 1.0, or null to unset any of {_EVERY}, "
                         f"{_GAMMA}, {_UNIT} (the reference run has no schedule)."),
        )

    def accepted_classes(self) -> frozenset[str]:
        return frozenset({
            "lr_schedule", "learning_rate_schedule", "lr_decay", "learning_rate_decay",
            "lr_schedule_misconfiguration", "learning_rate_schedule_misconfiguration", "lr_scheduler_bug",
            "lr_decay_too_fast", "learning_rate_decay_too_fast",
        })

    def core_tokens(self) -> list[frozenset[str]]:
        """Concept = the learning rate's SCHEDULE / decay: {learning_rate, lr} AND {schedul, decay, anneal}
        (``schedul`` covers schedule/scheduler/scheduled/scheduling)."""
        return [frozenset({"learning_rate", "lr"}), frozenset({"schedul", "decay", "anneal"})]

    def core_token_alternatives(self) -> list[list[frozenset[str]]]:
        """From its implementation, never from model output (author 2026-09-29): (a) the CONSEQUENCE — the rate
        decays towards zero within the first epoch: the learning rate AND {too low, too small, near zero,
        vanishing}; (b) the MECHANISM — the schedule's interval counted in the wrong unit: {schedul, decay} AND
        {step, unit, interval}. "epoch" is deliberately NOT a term: the frozen negation gate would read
        "per_step_not_epoch" (the right diagnosis) as negated, while "per_epoch_not_step" (the wrong unit blamed)
        is correctly rejected (author 2026-09-29). The ``weight_decay`` veto applies to every spec."""
        return [[frozenset({"learning_rate", "lr"}), frozenset({"too_low", "too_small", "near_zero", "vanish"})],
                [frozenset({"schedul", "decay"}), frozenset({"step", "unit", "interval"})]]

    def off_concept_vetoes(self) -> frozenset[str]:
        """``weight_decay`` is a different hyperparameter (L2 regularisation), not a learning-rate decay."""
        return frozenset({"weight_decay"})

    def oracle_repair(self) -> dict:
        """Remove the schedule: without ``decay_every`` the rate is constant, exactly the reference run."""
        return {"repair_type": "config_patch", "patches": {_EVERY: None}}


assert isinstance(DecayUnitOperator(), IncidentOperator), "DecayUnitOperator does not satisfy IncidentOperator"
