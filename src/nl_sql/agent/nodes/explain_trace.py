"""Node: ≤2-sentence NL caption via mistral-large-latest (or any LLMProvider).

Per arch v2 §3, this is the ONLY place the pipeline calls a non-coder LLM.
We call it last so a caption failure can never mask the structured answer —
on any error here we fall back to a deterministic Sentence built from the
result shape.
"""

from __future__ import annotations

from collections.abc import Callable

from nl_sql.agent.prompts import load_prompt
from nl_sql.agent.state import PipelineState
from nl_sql.llm.providers.base import GenerateRequest, LLMProvider, ProviderError


def make_explain_trace_node(
    provider: LLMProvider,
    *,
    max_tokens: int = 200,
    temperature: float = 0.2,
    preview_rows: int = 5,
) -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        outcome = state.get("outcome")
        question = state.get("question", "")
        trace = list(state.get("trace") or [])

        if outcome is None or outcome.result is None:
            caption = state.get("error_message") or "no result available"
            trace.append({"node": "explain_trace", "fallback": True})
            return {"caption": caption, "trace": trace}

        result = outcome.result
        preview = ", ".join(str(row) for row in result.rows[:preview_rows]) or "(none)"
        prompt = load_prompt(
            "explain",
            question=question,
            sql=outcome.sql,
            columns=", ".join(result.columns),
            row_count=result.row_count,
            preview=preview,
        )
        try:
            response = provider.generate(
                GenerateRequest(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
            )
            caption = (response.text or "").strip()
        except ProviderError as exc:
            caption = f"(caption unavailable: {exc})"
            trace.append({"node": "explain_trace", "error": str(exc)})
            return {"caption": caption, "trace": trace}

        trace.append(
            {
                "node": "explain_trace",
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        return {"caption": caption, "trace": trace}

    return node
