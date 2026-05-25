"""Text-shape helpers for LLM output parsing.

Split out of `_support.py` (Kimi audit P1.4) to keep the public helper
module focused on prompt assembly. Used only by
`_support.parse_generate_sql_output`.
"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text


def _safe_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _coerce_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN guard
        return default
    return max(0.0, min(1.0, result))


def _strip_to_sql(text: str) -> str:
    """Best-effort: pull a single SELECT statement from a free-form blob.

    Used only when JSON parsing fails entirely. We never want to emit empty
    SQL — that masks a model regression as 'empty result'.
    """
    cleaned = re.sub(r"```\w*", "", text).strip("`\n ")
    match = re.search(r"(SELECT\b[\s\S]+?)(?:;|$)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned.split("\n")[0].strip()
