"""LangGraph pipeline (stage 4 of v2 architecture).

Six-node graph (per docs/02_architecture_v2.md §3):

    context_builder → generate_sql → validate
                                       │
                                       ▼
                        ┌─── repair_once ◄─── (validate or execute fail, once)
                        │
                        ▼
                       execute → deterministic_format → explain_trace → END

`build_pipeline()` returns a compiled graph; pass `PipelineConfig` to inject
provider instances (lets tests swap real Mistral/Groq for fakes).
"""

from __future__ import annotations

from nl_sql.agent.graph import (
    PipelineConfig,
    PipelineRunResult,
    build_pipeline,
    run_pipeline,
)
from nl_sql.agent.state import GenerateSQLOutput, PipelineState

__all__ = [
    "GenerateSQLOutput",
    "PipelineConfig",
    "PipelineRunResult",
    "PipelineState",
    "build_pipeline",
    "run_pipeline",
]
