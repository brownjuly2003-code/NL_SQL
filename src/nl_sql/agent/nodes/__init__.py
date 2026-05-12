"""Pipeline node factories. Each ``make_*_node`` returns a callable that
takes `PipelineState` and returns a partial state dict for LangGraph to merge.

Why factories: the graph topology is fixed but providers/index/registry are
runtime-injected. Keeping construction explicit (factory closures over deps)
makes tests trivial — pass fakes, run the node, assert the partial dict.
"""

from __future__ import annotations

from nl_sql.agent.nodes.context_builder import make_context_builder_node
from nl_sql.agent.nodes.execute import make_execute_node
from nl_sql.agent.nodes.explain_trace import make_explain_trace_node
from nl_sql.agent.nodes.format import make_format_node
from nl_sql.agent.nodes.generate_sql import make_generate_sql_node
from nl_sql.agent.nodes.plan_query import make_plan_node
from nl_sql.agent.nodes.repair_once import make_repair_once_node
from nl_sql.agent.nodes.validate import make_validate_node

__all__ = [
    "make_context_builder_node",
    "make_execute_node",
    "make_explain_trace_node",
    "make_format_node",
    "make_generate_sql_node",
    "make_plan_node",
    "make_repair_once_node",
    "make_validate_node",
]
