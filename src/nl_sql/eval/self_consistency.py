"""Execution-based self-consistency voting for SQL candidates.

For a single question we run the LangGraph pipeline N times at distinct
sampling temperatures, collect the candidates, and pick the one whose
execution result has the largest agreement cluster.

This is the standard NL→SQL technique from Wang et al. (2023) — clustering
on the *execution result* (not the SQL string) tolerates equivalent SQL
spelt differently and is robust to small surface-level diversity.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from nl_sql.agent.graph import PipelineRunResult
from nl_sql.execution.errors import ExecutionErrorKind


@dataclass(frozen=True, slots=True)
class Candidate:
    """One pipeline pass + its sampling temperature."""

    result: PipelineRunResult
    temperature: float


def fingerprint_rows(rows: list[tuple[Any, ...]]) -> str:
    """Order-agnostic, type-stable fingerprint of a row set.

    BIRD-style execution accuracy is set-based unless the gold SQL has
    ORDER BY, so the canonical voting key sorts rows. Floats are rounded
    to 6 decimals to merge candidates that differ only in CAST precision.
    Heterogeneous types (None mixed with str/int) are made comparable
    by sorting on the repr — never on the raw value.
    """
    canon_rows = [tuple(_normalise_value(v) for v in row) for row in rows]
    canon = sorted(canon_rows, key=lambda r: tuple((type(v).__name__, repr(v)) for v in r))
    return hashlib.sha256(repr(canon).encode("utf-8")).hexdigest()


def _normalise_value(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, str):
        return v.strip()
    return v


def vote(candidates: list[Candidate]) -> Candidate:
    """Pick the winning candidate by execution-result clustering.

    Algorithm:
      1. Drop candidates whose execution failed (INVALID_SQL or
         EXECUTION_FAILED). EMPTY_RESULT counts as a real cluster — an
         empty answer can be the right answer.
      2. If no candidate executed, fall back to the highest-confidence
         candidate (the LLM's own self-rating, breaking ties by
         temperature ascending so greedy wins).
      3. Otherwise cluster on the row fingerprint. Pick the largest
         cluster; ties broken by max confidence within cluster, then
         by lowest temperature (greedy preferred).
    """
    if not candidates:
        raise ValueError("vote() requires at least one candidate")

    runnable = [c for c in candidates if _executed(c)]
    if not runnable:
        return max(
            candidates,
            key=lambda c: (_confidence(c), -c.temperature),
        )

    clusters: dict[str, list[Candidate]] = defaultdict(list)
    for c in runnable:
        rows = c.result.outcome.result.rows if c.result.outcome and c.result.outcome.result else []
        clusters[fingerprint_rows(rows)].append(c)

    def cluster_score(key: str) -> tuple[int, float, float]:
        members = clusters[key]
        return (
            len(members),
            max(_confidence(m) for m in members),
            -min(m.temperature for m in members),
        )

    best_key = max(clusters, key=cluster_score)
    return max(
        clusters[best_key],
        key=lambda c: (_confidence(c), -c.temperature),
    )


def _executed(c: Candidate) -> bool:
    """True iff the candidate produced rows we can vote on.

    Treat EMPTY_RESULT as runnable: zero rows is a legitimate answer
    (e.g. "list customers with no purchases"). INVALID_SQL and
    EXECUTION_FAILED are not eligible.
    """
    if c.result.outcome is None or c.result.outcome.result is None:
        return False
    kind = c.result.error_kind
    return kind not in (ExecutionErrorKind.INVALID_SQL, ExecutionErrorKind.EXECUTION_FAILED)


def _confidence(c: Candidate) -> float:
    """LLM self-rating from generate_sql trace, default 0.0 if missing."""
    for step in reversed(c.result.trace):
        if step.get("node") in ("generate_sql", "repair_once"):
            value = step.get("confidence")
            if isinstance(value, int | float):
                return float(value)
    return 0.0
