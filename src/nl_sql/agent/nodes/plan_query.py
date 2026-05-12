"""Node: plan_query — emit a structured plan before SQL generation.

Two-stage decomposition (DIN-SQL / MAC-SQL style). The plan node produces a
JSON skeleton (tables/joins/filters/group/agg/projection/expected_row_count)
that the downstream `generate_sql` node sees as additional grounding context.

Empirically, forcing the model to commit to row-shape and projection BEFORE
writing SQL fixes a large fraction of "row_count_off" and "projection_diff"
failures observed in the BIRD baseline taxonomy (see scripts/error_taxonomy.py).
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.nodes._support import (
    render_fewshot_block,
    render_schema_block,
)
from nl_sql.agent.prompts import load_prompt
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider


def make_plan_node(
    provider: LLMProvider,
    *,
    max_tokens: int = 600,
    temperature: float = 0.0,
    sort_schema_block: bool = False,
) -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        question = state.get("question", "")
        dialect = state.get("dialect", "sqlite")
        context = state.get("context")
        prompt = load_prompt(
            "plan",
            dialect=dialect,
            schema_block=render_schema_block(context, sort_alphabetically=sort_schema_block),
            fewshot_block=render_fewshot_block(context),
            question=question,
        )
        response = provider.generate(
            GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        )
        plan_text = (response.text or "").strip()
        trace = list(state.get("trace") or [])
        trace.append(
            {
                "node": "plan_query",
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        return {
            "plan": plan_text,
            "trace": trace,
        }

    return node
