"""Node: ask codestral (or any LLMProvider) for SQL given the schema context.

Builds the prompt from the active context bundle, dispatches to the provider,
parses the JSON response into a `GenerateSQLOutput`. The same node powers the
*initial* generation pass — the repair pass is a separate node that calls
this same provider with a different prompt.
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.nodes._support import (
    parse_generate_sql_output,
    render_fewshot_block,
    render_schema_block,
)
from nl_sql.agent.prompts import load_prompt
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider


def make_generate_sql_node(
    provider: LLMProvider,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    sort_schema_block: bool = False,
) -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        question = state.get("question", "")
        dialect = state.get("dialect", "sqlite")
        context = state.get("context")
        prompt = load_prompt(
            "generate_sql",
            dialect=dialect,
            schema_block=render_schema_block(
                context, sort_alphabetically=sort_schema_block
            ),
            fewshot_block=render_fewshot_block(context),
            question=question,
        )
        response = provider.generate(
            GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
        )
        parsed = parse_generate_sql_output(response.text)
        trace = list(state.get("trace") or [])
        trace.append(
            {
                "node": "generate_sql",
                "model": response.model,
                "confidence": parsed.confidence,
                "tables_used": list(parsed.tables_used),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        # Reset any stale outcome / error from a previous repair iteration.
        return {
            "generated": parsed,
            "outcome": None,
            "last_error": "",
            "trace": trace,
        }

    return node
