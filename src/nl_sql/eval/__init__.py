"""Evaluation harness: ablation matrix, metrics, HTML report.

Stage 6 of the v2 pipeline (per docs/03_eval_methodology.md).

Public surface:
- `BirdExample`, `load_bird_mini_dev`, `dev_split` — dataset access.
- `compare_results`, `execution_accuracy` — order-insensitive EA, BIRD parity.
- `schema_recall_at_k` — secondary RAG metric.
- `Configuration`, `EvalRecord`, `EvalRun`, `run_config_a` — runner.
- `write_json_report`, `write_html_report` — artefact writers.
"""

from __future__ import annotations

from nl_sql.eval.dataset import (
    BirdExample,
    dev_split,
    extract_gold_tables,
    load_bird_mini_dev,
)
from nl_sql.eval.metrics.execution_accuracy import (
    ResultComparison,
    compare_results,
    execution_accuracy,
)
from nl_sql.eval.metrics.schema_recall import schema_recall_at_k
from nl_sql.eval.report import write_html_report, write_json_report
from nl_sql.eval.runner import (
    Configuration,
    EvalRecord,
    EvalRun,
    EvalSummary,
    run_config_a,
)

__all__ = [
    "BirdExample",
    "Configuration",
    "EvalRecord",
    "EvalRun",
    "EvalSummary",
    "ResultComparison",
    "compare_results",
    "dev_split",
    "execution_accuracy",
    "extract_gold_tables",
    "load_bird_mini_dev",
    "run_config_a",
    "schema_recall_at_k",
    "write_html_report",
    "write_json_report",
]
