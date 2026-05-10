"""Output format taxonomy.

The pipeline emits exactly one of these. Selection is deterministic from the
result shape (see picker.py); LLMs only ever pick a chart *intent* and write
a caption. Spec generation is never delegated to an LLM — that was the v1
mistake CX/KM both flagged.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Scalar(BaseModel):
    kind: Literal["scalar"] = "scalar"
    value: object
    column: str = ""


class Sentence(BaseModel):
    kind: Literal["sentence"] = "sentence"
    text: str
    fields: dict[str, object] = Field(default_factory=dict)


class Table(BaseModel):
    kind: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[object]]


class _ChartBase(BaseModel):
    columns: list[str]
    rows: list[list[object]]
    x_field: str
    y_fields: list[str]


class BarChart(_ChartBase):
    kind: Literal["bar"] = "bar"


class LineChart(_ChartBase):
    kind: Literal["line"] = "line"


class PieChart(_ChartBase):
    kind: Literal["pie"] = "pie"


class ScatterChart(_ChartBase):
    kind: Literal["scatter"] = "scatter"


ChartSpec = BarChart | LineChart | PieChart | ScatterChart
OutputFormat = Scalar | Sentence | Table | ChartSpec
