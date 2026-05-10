"""Static SQL guard backed by sqlglot AST.

Layer 2 of the 3-layer execution defence (per docs/02_architecture_v2.md §5):
- DB role enforces read-only at session level.
- This module enforces shape: SELECT-only, single statement, no DML in CTEs,
  function allowlist (deny pg_sleep, generate_series above N, ATTACH, file
  reads), no schema escalation.
- Runner enforces statement_timeout + result-payload cap.

The guard returns a ValidationReport describing every detected issue rather
than raising on the first one — the caller (repair_once node) needs the full
list to build a useful error context for the LLM retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from nl_sql.db.connection import Dialect

# Map our SQLAlchemy-style dialect names to sqlglot's canonical names.
_SQLGLOT_DIALECT: Final[dict[Dialect, str]] = {
    "sqlite": "sqlite",
    "postgresql": "postgres",
}

# Functions banned outright. Mostly resource-abuse vectors.
BANNED_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "lo_import",
        "lo_export",
        "dblink",
        "load_extension",
        "readfile",
    }
)

# generate_series is legitimate but easy to weaponize for DoS — capped at N.
GENERATE_SERIES_MAX_RANGE: Final[int] = 1_000_000

# Reading from these schemas/tables is denied unless on an explicit allowlist.
DENIED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "pg_user",
        "pg_authid",
        "pg_shadow",
        "pg_roles",
    }
)


@dataclass(frozen=True, slots=True)
class GuardViolation:
    code: str
    message: str


@dataclass(slots=True)
class ValidationReport:
    sql: str
    dialect: Dialect
    violations: list[GuardViolation] = field(default_factory=list)
    parsed: exp.Expression | None = None

    @property
    def ok(self) -> bool:
        return not self.violations

    def add(self, code: str, message: str) -> None:
        self.violations.append(GuardViolation(code=code, message=message))


def validate_sql(sql: str, dialect: Dialect = "sqlite") -> ValidationReport:
    """Run all static checks against `sql`. Always returns a report."""
    report = ValidationReport(sql=sql, dialect=dialect)

    parsed_list = _safe_parse(sql, dialect, report)
    if parsed_list is None:
        return report

    if len(parsed_list) != 1:
        report.add("multi_statement", f"expected 1 statement, got {len(parsed_list)}")
        return report

    parsed = parsed_list[0]
    if parsed is None:
        report.add("empty_statement", "parsed statement is empty")
        return report

    report.parsed = parsed

    _check_select_only(parsed, report)
    _check_no_dml_anywhere(parsed, report)
    _check_function_allowlist(parsed, report)
    _check_generate_series_bounds(parsed, report)
    _check_table_denylist(parsed, report)
    _check_no_attach_or_pragma(parsed, report)

    return report


def _safe_parse(
    sql: str, dialect: Dialect, report: ValidationReport
) -> list[exp.Expression | None] | None:
    sqlglot_name = _SQLGLOT_DIALECT[dialect]
    try:
        # sqlglot.parse returns list[Optional[Expression]] but its internal
        # Expr alias trips strict mypy; cast keeps the public API typed.
        return cast("list[exp.Expression | None]", sqlglot.parse(sql, read=sqlglot_name))
    except ParseError as exc:
        report.add("parse_error", str(exc))
        return None


def _check_select_only(parsed: exp.Expression, report: ValidationReport) -> None:
    if not isinstance(parsed, exp.Select | exp.Union | exp.Subquery):
        report.add(
            "not_select",
            f"top-level statement must be SELECT/UNION; got {type(parsed).__name__}",
        )


def _check_no_dml_anywhere(parsed: exp.Expression, report: ValidationReport) -> None:
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Alter)
    for node in parsed.walk():
        if isinstance(node, forbidden):
            report.add("dml_in_tree", f"{type(node).__name__} not permitted anywhere in query")
    # DDL via Create / Drop
    for node in parsed.walk():
        if isinstance(node, exp.Create | exp.Drop):
            report.add("ddl_in_tree", f"{type(node).__name__} not permitted")
    # SQLite-specific safety: ATTACH / PRAGMA arrive as their own AST nodes
    for node in parsed.walk():
        if isinstance(node, exp.Attach):
            report.add("attach_database", "ATTACH DATABASE is denied")
        if isinstance(node, exp.Pragma):
            report.add("pragma_statement", "PRAGMA is denied at the query layer")


def _check_function_allowlist(parsed: exp.Expression, report: ValidationReport) -> None:
    seen: set[str] = set()
    # Anonymous covers most user-named functions (pg_sleep, generate_series, etc.).
    for anon in parsed.find_all(exp.Anonymous):
        anon_name = (anon.name or "").lower()
        if anon_name in BANNED_FUNCTIONS and anon_name not in seen:
            seen.add(anon_name)
            report.add("banned_function", f"function {anon_name!r} is denied")
    # Some functions render as named exp.Func subclasses with key()-derived names.
    for node in parsed.walk():
        if isinstance(node, exp.Func):
            key = (node.key or "").lower()
            if key in BANNED_FUNCTIONS and key not in seen:
                seen.add(key)
                report.add("banned_function", f"function {key!r} is denied")


def _check_generate_series_bounds(parsed: exp.Expression, report: ValidationReport) -> None:
    # Postgres dialect produces a typed GenerateSeries node; SQLite-style or
    # unrecognized parses fall back to Anonymous("generate_series", ...).
    for node in parsed.walk():
        bounds = _generate_series_bounds(node)
        if bounds is None:
            continue
        start, stop = bounds
        span = abs(stop - start)
        if span > GENERATE_SERIES_MAX_RANGE:
            report.add(
                "generate_series_too_large",
                f"generate_series span {span} exceeds cap {GENERATE_SERIES_MAX_RANGE}",
            )


def _generate_series_bounds(node: Any) -> tuple[int, int] | None:
    start_node: Any
    end_node: Any
    if isinstance(node, exp.GenerateSeries):
        start_node = node.args.get("start")
        end_node = node.args.get("end")
    elif isinstance(node, exp.Anonymous) and (node.name or "").lower() == "generate_series":
        args = list(node.expressions)
        if len(args) < 2:
            return None
        start_node, end_node = args[0], args[1]
    else:
        return None

    if not (isinstance(start_node, exp.Literal) and start_node.is_int):
        return None
    if not (isinstance(end_node, exp.Literal) and end_node.is_int):
        return None
    return int(start_node.this), int(end_node.this)


def _check_table_denylist(parsed: exp.Expression, report: ValidationReport) -> None:
    for table in parsed.find_all(exp.Table):
        name = (table.name or "").lower()
        if name in DENIED_TABLES:
            report.add("denied_table", f"table {name!r} is on the denylist")


def _check_no_attach_or_pragma(parsed: exp.Expression, report: ValidationReport) -> None:
    # Already covered by _check_no_dml_anywhere via exp.Attach / exp.Pragma nodes;
    # kept as a no-op seam so future dialects (e.g. DuckDB ATTACH variants) can plug
    # additional textual heuristics without adding a new top-level check.
    return
