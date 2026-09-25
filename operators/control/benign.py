"""Benign-configuration controls — HEALTHY runs with a legitimate, deliberate config change
(STAGE4_PLAN 4.0.6; DECISIONS 2026-09-23).

A benign control is a control: the correct diagnosis is "no incident", evidence is empty, no repair is
admissible, the oracle repair is None, and it is retained at ANY band position (§5.1). Unlike
``control.healthy.v1`` its workspace carries one routine practitioner edit, so it tests whether an
agent (or a config-diff baseline) flags a legitimate CHANGE as a fault — the probe of "diagnosis vs
flagging". The CLAUDE.md operator rule inverts for this tier: the change must NOT degrade the model,
which is established at DESIGN time (``scripts/qualify_benign.py``; every type below QUALIFIED on
development seeds 0–29, ``docs/audits/benign_qualification.md``), never by gating individual cases.

One operator per change type (ids are W1-safe: no segment occurs in any workspace file). ``FORM`` is
"changed" (an existing key's value) or "added" (a new key) — reported separately, because four of the
five fault operators ADD a key. ``grad_clip_1.0`` is the new-key type: non-binding (the largest
pre-clip gradient norm is ≈ 0.59), so its case is byte-identical to a clean run except one config
line — any false positive on it is attributable to the new key alone.
"""
from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Literal

import yaml

from operators.base import EvidenceRef, IncidentOperator, Manifest, MutationRecord, RepairSpecSchema


class _BenignConfigOperator:
    """Base: apply a fixed, qualified config edit; ground truth identical to a healthy control."""

    id: str = ""
    layer: Literal["control"] = "control"
    EDITS: dict = {}           # key path -> value
    FORM: str = ""             # "changed" | "added"
    DESCRIPTION: str = ""

    def apply(self, workspace: Path, rng: Random, strength: str) -> Manifest:
        """Write the edit into ``config.yaml``. *strength* is accepted for interface uniformity and
        ignored (a benign change has one setting)."""
        config_path = workspace / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        mutations = []
        for path, value in self.EDITS.items():
            node = config
            *parents, leaf = path.split(".")
            for p in parents:
                node = node.setdefault(p, {})
            original = node.get(leaf)
            node[leaf] = value
            mutations.append(MutationRecord(file="config.yaml", key_path=path, original_value=original,
                                            mutated_value=value, description=self.DESCRIPTION))
        config_path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return Manifest(operator_id=self.id, layer=self.layer, strength=strength, seed=0,
                        mutations=mutations)

    def evidence(self) -> list[EvidenceRef]:
        """No fault → nothing to cite; any submitted ref is a false positive."""
        return []

    def admissible_repairs(self) -> RepairSpecSchema:
        """No repair is admissible: the change is legitimate (reverting it is a false intervention)."""
        return RepairSpecSchema(repair_type="none", allowed_keys=[],
                                description="Healthy run with a legitimate config change — no repair.")

    def accepted_classes(self) -> frozenset[str]:
        return frozenset({"none", "healthy", "no_incident", "no_fault", "nothing_wrong"})

    def core_tokens(self) -> list[frozenset[str]]:
        # Same concept (and spec) as control.healthy.v1 — the uniqueness guard counts concepts.
        return [frozenset({"none", "healthy", "no_incident", "nothing_wrong", "no_fault"})]

    def oracle_repair(self) -> None:
        return None


class BenignBatchSize(_BenignConfigOperator):
    id = "control.benign_bs128.v1"
    EDITS = {"training.batch_size": 128}
    FORM = "changed"
    DESCRIPTION = "Routine change: mini-batch size 256 -> 128"


class BenignEpochs(_BenignConfigOperator):
    id = "control.benign_ep25.v1"
    EDITS = {"training.epochs": 25}
    FORM = "changed"
    DESCRIPTION = "Routine change: train 25 epochs instead of 20"


class BenignWeightDecay(_BenignConfigOperator):
    id = "control.benign_wd5e4.v1"
    EDITS = {"training.weight_decay": 0.0005}
    FORM = "changed"
    DESCRIPTION = "Routine change: weight decay 1e-4 -> 5e-4"


class BenignDropout(_BenignConfigOperator):
    id = "control.benign_do01.v1"
    EDITS = {"model.dropout": 0.1}
    FORM = "changed"
    DESCRIPTION = "Routine change: dropout 0.0 -> 0.1"


class BenignLearningRate(_BenignConfigOperator):
    id = "control.benign_lr005.v1"
    EDITS = {"training.lr": 0.005}
    FORM = "changed"
    DESCRIPTION = "Routine change: learning rate 0.01 -> 0.005 (within normal range)"


class BenignGradClip(_BenignConfigOperator):
    id = "control.benign_clip1.v1"
    EDITS = {"training.grad_clip_norm": 1.0}
    FORM = "added"
    DESCRIPTION = "Routine change: enable gradient-norm clipping at 1.0 (new key)"


BENIGN_OPERATORS = (BenignBatchSize, BenignEpochs, BenignWeightDecay, BenignDropout,
                    BenignLearningRate, BenignGradClip)

for _cls in BENIGN_OPERATORS:
    assert isinstance(_cls(), IncidentOperator), f"{_cls.__name__} does not satisfy IncidentOperator"


def benign_design(seeds) -> list[tuple[str, str, int]]:
    """(operator_id, "mild", seed) for the benign-configuration controls: the sorted ``seeds`` split
    into equal consecutive blocks, type i (declaration order above) taking block i — for 70–93, type i
    gets 70+4i .. 73+4i. The ONE source of the type↔seed pairing: the case builder
    (scripts/build_all_cases.py) and the sweep planner (harness/sweep.py) both call it."""
    seeds = sorted(seeds)
    per = len(seeds) // len(BENIGN_OPERATORS)
    if per == 0 or per * len(BENIGN_OPERATORS) != len(seeds):
        raise ValueError(f"benign seeds must split evenly over {len(BENIGN_OPERATORS)} types; got {len(seeds)}")
    return [(cls.id, "mild", seeds[i * per + j])
            for i, cls in enumerate(BENIGN_OPERATORS) for j in range(per)]
