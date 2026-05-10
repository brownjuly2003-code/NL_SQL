"""Prompt templates for the LangGraph pipeline.

Each .txt file is a Python ``str.format``-style template — fields are filled
by `prompts.load_prompt`. Keeping the templates as text (not f-strings in code)
lets us tweak wording without re-running tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PROMPT_DIR = Path(__file__).parent


def load_prompt(name: str, **fields: Any) -> str:
    """Load `<name>.txt` and substitute `{field}` placeholders.

    Raises FileNotFoundError if the template is missing — we'd rather fail
    loud than silently send an unrendered template to the LLM.
    """
    path = _PROMPT_DIR / f"{name}.txt"
    template = path.read_text(encoding="utf-8")
    return template.format(**fields)
