"""Eval metrics: execution accuracy + schema recall.

Two metric families per docs/03_eval_methodology.md §1:
- Primary: Execution Accuracy (EA) on BIRD Mini-Dev.
- Secondary: Schema Recall@k (so we know whether RAG, not the LLM, is the
  bottleneck when EA is low).

Latency / token / cost stats are aggregated in `runner.py`, not here, since
they are run-shape data rather than per-prediction metrics.
"""

from __future__ import annotations

from nl_sql.eval.metrics.execution_accuracy import (
    ResultComparison,
    compare_results,
    execution_accuracy,
)
from nl_sql.eval.metrics.schema_recall import schema_recall_at_k

__all__ = [
    "ResultComparison",
    "compare_results",
    "execution_accuracy",
    "schema_recall_at_k",
]
