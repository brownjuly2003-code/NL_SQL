"""Node: re-ask the LLM for SQL given the previous failure context.

Per arch v2 §3, exactly one repair pass per question. The graph guards this
by checking ``state["repair_attempted"]`` before routing here. This node
sets the flag itself before returning so a second routing attempt would be
a programming error in the graph.
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.nodes._support import (
    parse_generate_sql_output,
    render_schema_block,
)
from nl_sql.agent.prompts import load_prompt
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider


def make_repair_once_node(
    provider: LLMProvider,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    sort_schema_block: bool = False,
) -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        generated = state.get("generated")
        previous_sql = generated.sql if generated else ""
        error_context = state.get("last_error") or "(no error context — likely a programming bug)"
        question = state.get("question", "")
        dialect = state.get("dialect", "sqlite")
        context = state.get("context")

        plan_raw = (state.get("plan") or "").strip()
        plan_block = plan_raw if plan_raw else "(no plan — repair SQL directly)"
        prompt = load_prompt(
            "repair_sql",
            dialect=dialect,
            schema_block=render_schema_block(context, sort_alphabetically=sort_schema_block),
            question=question,
            previous_sql=previous_sql,
            error_context=error_context,
            plan_block=plan_block,
        )
        response = provider.generate(
            GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        )
        parsed = parse_generate_sql_output(response.text)

        trace = list(state.get("trace") or [])
        trace.append(
            {
                "node": "repair_once",
                "model": response.model,
                "confidence": parsed.confidence,
                "previous_error": error_context,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        return {
            "generated": parsed,
            "outcome": None,
            "repair_attempted": True,
            "last_error": "",
            "error_kind": None,
            "error_message": "",
            "trace": trace,
        }

    return node
