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
    render_m_schema,
    render_schema_block,
)
from nl_sql.agent.prompts import load_prompt
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider
from nl_sql.schema_index.value_retrieval import format_value_grounding


def make_generate_sql_node(
    provider: LLMProvider,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    sort_schema_block: bool = False,
    use_m_schema: bool = False,
    use_dac_prompt: bool = False,
    use_compact_prompt: bool = False,
    enable_bird_rescue_hints: bool = False,
) -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        question = state.get("question", "")
        dialect = state.get("dialect", "sqlite")
        context = state.get("context")
        plan_raw = (state.get("plan") or "").strip()
        plan_block = plan_raw if plan_raw else "(no plan — generate SQL directly from question)"
        # Schema rendering: M-Schema (XiYan-SQL compact) vs verbose card layout.
        # Driven by `PipelineConfig.use_m_schema`; api/main.py bootstraps the
        # flag from `NLSQL_M_SCHEMA=1` env so existing eval scripts keep working.
        if use_m_schema:
            schema_text = render_m_schema(context)
        else:
            schema_text = render_schema_block(
                context,
                sort_alphabetically=sort_schema_block,
                enable_bird_rescue_hints=enable_bird_rescue_hints,
            )
        # A8: targeted column descriptions ride as a schema appendix. Empty
        # when the lever is off, keeping the prompt (and LLM cache) identical
        # to the historical path.
        column_notes = (state.get("column_notes") or "").strip()
        if column_notes:
            schema_text = f"{schema_text}\n\n{column_notes}"
        # CHESS-style value grounding: append short "value X appears in T.C"
        # lines to the question so they sit next to the NL (and any Hint).
        # Empty when the flag is off or nothing matched — prompt text then
        # matches the historical path, so the LLM cache stays warm.
        value_block = ""
        if context is not None and getattr(context, "value_matches", None):
            value_block = format_value_grounding(list(context.value_matches))
        question_for_prompt = f"{question}\n\n{value_block}" if value_block else question
        # A4 (E-SQL): explicit restatement rides NEXT TO the question, never
        # instead of it — an enrichment mistake must not override the original.
        # Empty when the lever is off, so the prompt text (and the LLM cache)
        # matches the historical path exactly.
        enriched = (state.get("enriched_question") or "").strip()
        if enriched:
            question_for_prompt = (
                f"{question_for_prompt}\n\n"
                f"Explicit restatement (auxiliary; the original question above is "
                f"authoritative):\n{enriched}"
            )
        # Prompt selection. The default `generate_sql` grew around codestral:
        # heavy projection coaching, a DISTINCT rule taught on Chinook tables,
        # per-database disambiguation. `generate_sql_compact` keeps only what is
        # dataset- or dialect-true and drops the model-specific coaching, which
        # matters for a frontier model on a metered browser path — the long
        # prompt is both the coaching it does not need and the latency it pays
        # for. DAC (CHASE-SQL divide-and-conquer) is the third option.
        if use_compact_prompt:
            prompt_name = "generate_sql_compact"
        elif use_dac_prompt:
            prompt_name = "generate_sql_dac"
        else:
            prompt_name = "generate_sql"
        prompt = load_prompt(
            prompt_name,
            dialect=dialect,
            schema_block=schema_text,
            fewshot_block=render_fewshot_block(context),
            plan_block=plan_block,
            question=question_for_prompt,
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
