"""Node: deterministic format picker (no LLM).

Per arch v2 §3 / §8 / picker.py, the chart-or-not decision is pure Python
heuristics on the result shape. The LLM never emits Vega-Lite.
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.state import PipelineState
from nl_sql.render.formats import Sentence
from nl_sql.render.picker import pick_format


def make_format_node() -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        outcome = state.get("outcome")
        trace = list(state.get("trace") or [])

        if outcome is None or outcome.result is None:
            # Either we never executed, or execution failed and there's no
            # result payload. Surface a clear sentence so the user UI never
            # sees "format=null".
            error_msg = state.get("error_message") or (
                outcome.error_message if outcome else "no result available"
            )
            placeholder = Sentence(text=f"could not produce a result: {error_msg}")
            trace.append(
                {"node": "deterministic_format", "shape": "error_sentence"}
            )
            return {"output_format": placeholder, "trace": trace}

        result = outcome.result
        formatted = pick_format(result.columns, result.rows)
        trace.append(
            {
                "node": "deterministic_format",
                "shape": type(formatted).__name__,
                "row_count": result.row_count,
            }
        )
        return {"output_format": formatted, "trace": trace}

    return node
