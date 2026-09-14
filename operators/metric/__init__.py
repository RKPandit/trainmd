"""Metric-tier (observability) operators (spec §4).

The run completes and the MODEL is healthy — hidden-test accuracy stays inside
the reference band — but the REPORTED visible metric is computed incorrectly and
reads above the healthy band. The fault lives only in the reported number, never
in the model, its training, or its saved checkpoint. See docs/DECISIONS.md
(third fault tier).
"""
