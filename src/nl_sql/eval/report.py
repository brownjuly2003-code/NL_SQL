"""Eval artefact writers: JSON (machine-readable) + HTML (portfolio-ready).

JSON layout matches `EvalRun` exactly so a downstream notebook can `json.load`
it and rebuild dataframes. HTML is a single static file — no JS, no CSS
framework, just a server-rendered table per the methodology doc.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from nl_sql.eval.runner import Configuration, EvalRecord, EvalRun, EvalSummary

REPORTS_ROOT = Path("eval") / "reports"


def write_json_report(run: EvalRun, *, root: Path | str = REPORTS_ROOT) -> Path:
    """Dump one EvalRun as `eval/reports/<date>/<config>.json`."""
    out_dir = _date_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run.configuration.value}.json"
    payload = {
        "configuration": run.configuration.value,
        "sql_model": run.sql_model,
        "overall": asdict(run.overall),
        "per_difficulty": {k: asdict(v) for k, v in run.per_difficulty.items()},
        "records": [asdict(r) for r in run.records],
    }
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    return path


def write_html_report(
    runs: Sequence[EvalRun], *, root: Path | str = REPORTS_ROOT
) -> Path:
    """Render `eval/reports/<date>/index.html` with one table per run."""
    out_dir = _date_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    body_parts: list[str] = [
        f"<h1>NL→SQL eval — {datetime.now(tz=UTC):%Y-%m-%d}</h1>",
        "<p>Source: BIRD Mini-Dev (SQLite). "
        "Methodology: <code>docs/03_eval_methodology.md</code>.</p>",
    ]
    body_parts.append(_render_overall_table(runs))
    for run in runs:
        body_parts.append(_render_run_section(run))
    html = _wrap_html("\n".join(body_parts))
    path.write_text(html, encoding="utf-8")
    return path


def _date_dir(root: Path | str) -> Path:
    return Path(root) / datetime.now(tz=UTC).strftime("%Y-%m-%d")


def load_run_from_json(path: Path | str) -> EvalRun:
    """Re-hydrate an EvalRun previously written by `write_json_report`.

    Used by the live driver so an HTML report can combine today's freshly-
    finished configuration with whatever runs already sit in the same date
    directory. Roundtrip-stable on all dataclass fields (tuples come back
    as tuples; the `_json_default` writer sends them as lists).
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    overall = EvalSummary(**raw["overall"])
    per_difficulty = {k: EvalSummary(**v) for k, v in (raw.get("per_difficulty") or {}).items()}
    records = [_record_from_dict(r) for r in raw.get("records") or []]
    return EvalRun(
        configuration=Configuration(raw["configuration"]),
        sql_model=raw["sql_model"],
        overall=overall,
        per_difficulty=per_difficulty,
        records=records,
    )


def _record_from_dict(raw: dict[str, Any]) -> EvalRecord:
    """Convert one record dict into an EvalRecord; tuple fields are restored."""
    coerced = dict(raw)
    for key in ("gold_tables", "retrieved_tables"):
        value = coerced.get(key)
        if isinstance(value, list):
            coerced[key] = tuple(value)
    return EvalRecord(**coerced)


def _render_overall_table(runs: Iterable[EvalRun]) -> str:
    headers = [
        "Configuration",
        "Model",
        "n",
        "EA",
        "Simple",
        "Moderate",
        "Challenging",
        "Validity",
        "Recall@k",
        "Empty %",
        "P50 latency",
        "P95 latency",
    ]
    rows: list[str] = []
    for run in runs:
        diff = run.per_difficulty
        rows.append(
            "<tr>"
            + _td(run.configuration.value)
            + _td(run.sql_model)
            + _td(str(run.overall.n))
            + _td(_pct(run.overall.ea))
            + _td(_pct(diff.get("simple", _zero()).ea))
            + _td(_pct(diff.get("moderate", _zero()).ea))
            + _td(_pct(diff.get("challenging", _zero()).ea))
            + _td(_pct(run.overall.validity_rate))
            + _td(_pct(run.overall.schema_recall_at_k))
            + _td(_pct(run.overall.empty_result_rate))
            + _td(_ms(run.overall.latency_p50_ms))
            + _td(_ms(run.overall.latency_p95_ms))
            + "</tr>"
        )
    return (
        "<h2>Summary</h2>"
        "<table><thead><tr>"
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def _render_run_section(run: EvalRun) -> str:
    return (
        f"<h2>{escape(run.configuration.value)}</h2>"
        f"<p>Model: <code>{escape(run.sql_model)}</code> · "
        f"n={run.overall.n} · "
        f"EA={_pct(run.overall.ea)} · "
        f"Validity={_pct(run.overall.validity_rate)} · "
        f"Recall@k={_pct(run.overall.schema_recall_at_k)}</p>"
        + _render_records_table(run.records[:200])
        + (
            f"<p><em>Showing first 200 of {len(run.records)} records.</em></p>"
            if len(run.records) > 200
            else ""
        )
    )


def _render_records_table(records: Sequence[EvalRecord]) -> str:
    if not records:
        return "<p><em>No records.</em></p>"
    headers = [
        "qid",
        "db",
        "diff",
        "match",
        "recall",
        "err",
        "lat ms",
        "tokens",
        "question",
    ]
    rows: list[str] = []
    for r in records:
        rows.append(
            "<tr>"
            + _td(str(r.question_id))
            + _td(r.db_id)
            + _td(r.difficulty)
            + _td("✓" if r.match else "✗")
            + _td("✓" if r.schema_recall else "✗")
            + _td(r.error_kind or "")
            + _td(f"{r.latency_ms:.0f}")
            + _td(str(r.input_tokens + r.output_tokens))
            + _td(r.question[:120])
            + "</tr>"
        )
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def _wrap_html(body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>NL→SQL eval</title>"
        "<style>"
        "body{font-family:system-ui,Segoe UI,sans-serif;margin:24px;color:#222;}"
        "table{border-collapse:collapse;margin:12px 0;font-size:14px;}"
        "th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}"
        "th{background:#f6f6f6;}"
        "code{background:#f0f0f0;padding:1px 4px;border-radius:2px;}"
        "h1{margin-top:0;}h2{margin-top:32px;}"
        "</style></head><body>"
        f"{body}"
        "</body></html>"
    )


def _td(text: str) -> str:
    return f"<td>{escape(text)}</td>"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _ms(value: float) -> str:
    return f"{value:.0f} ms"


def _zero() -> EvalSummary:
    return EvalSummary(
        n=0,
        ea=0.0,
        validity_rate=0.0,
        schema_recall_at_k=0.0,
        repair_success_rate=0.0,
        first_pass_ea=0.0,
        empty_result_rate=0.0,
        latency_p50_ms=0.0,
        latency_p95_ms=0.0,
        tokens_p50=0.0,
        tokens_p95=0.0,
    )


def _json_default(value: object) -> object:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"not json-serialisable: {type(value).__name__}")
