"""Drift guard for ``scripts/build_index.py``.

The chunks stored in Chroma bake in a fixed number of sample values per
column at index-build time. Runtime advertises this density through
``PipelineConfig.primary_sample_size``. If the two drift apart, the
sample-mixture appendix logic (``extended_sample_size > primary_sample_size``)
appends the wrong tail rows and silently degrades retrieval quality.

This test fails fast if a future edit reintroduces the historic mismatch
(build_index default 5 vs PipelineConfig default 3) called out in
``audit_codex_12_05_26.md`` §7.
"""

from __future__ import annotations

from dataclasses import fields

from nl_sql.agent.graph import PipelineConfig
from scripts import build_index


def test_default_sample_size_matches_pipeline_config() -> None:
    runtime_default = next(
        field.default for field in fields(PipelineConfig) if field.name == "primary_sample_size"
    )
    assert runtime_default == build_index.DEFAULT_SAMPLE_SIZE


def test_cli_default_uses_module_constant() -> None:
    namespace = build_index.build_parser().parse_args(["--db", "chinook"])
    assert namespace.sample_size == build_index.DEFAULT_SAMPLE_SIZE
