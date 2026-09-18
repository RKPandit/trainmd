"""Neutral-key variant of ``silent.data_leakage.v1`` (STAGE3 v3 Part 2).

Mechanically IDENTICAL to :class:`DataLeakageOperator` — same derivation
(``datautil._derived_column``), same per-split hashing, same hidden-test noise,
same strengths (p = 0.28/0.20/0.05), same confirmatory seeds — with the two
config keys renamed to semantically NEUTRAL names that carry no hint about the
fault concept:

    ``data.include_aux_feature`` → ``data.opt_c``
    ``data.aux_feature_strength`` → ``data.opt_c_level``

The fault IS still leakage, so the identification answer key
(``accepted_classes`` / ``core_tokens`` = {leak}) is inherited UNCHANGED — only
``evidence``/``admissible_repairs``/``oracle_repair`` track the neutral keys
(they read the names from the class attributes on the parent).

This operator's cases run on the ``tabular_adult_neutral`` workload family,
whose train.py reads ``opt_c``/``opt_c_level`` and imports the SAME
``_derived_column`` — so the only thing an agent can observe that differs from
the descriptive variant is the config key name (H8; see docs/HYPOTHESES.md).
"""
from __future__ import annotations

from typing import Literal

from operators.silent.data_leakage import DataLeakageOperator


class DataLeakageNeutralOperator(DataLeakageOperator):
    """Data leakage under neutral config-key names (identification ablation)."""

    id: str = "silent.data_leakage_neutral.v1"
    layer: Literal["dynamics"] = "dynamics"

    ENABLE_KEY: str = "opt_c"
    STRENGTH_KEY: str = "opt_c_level"
    WORKLOAD_FAMILY: str = "tabular_adult_neutral"
