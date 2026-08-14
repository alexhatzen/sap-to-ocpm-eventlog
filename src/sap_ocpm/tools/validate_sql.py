"""validate_sql(query) — parse and dialect-check a SQL query.

Deterministic syntax validation via sqlglot. This does not (and should
not) validate that referenced tables/columns exist in the KB — that's a
separate, KB-aware concern the critic pass composes from
get_table_schema/find_join_path. This tool answers one question only:
is the SQL itself well-formed.

Two honesty notes, found the hard way while building this:

1. sqlglot ships no native SAP HANA dialect (its closest namesake is
   Athena, a different product). Claiming "hana" as a default would be
   exactly the kind of unearned precision this project exists to
   avoid, so the default is sqlglot's generic/ANSI-ish dialect, and the
   result always echoes back which dialect was actually used.
2. sqlglot.parse() is permissive: garbage like "SELEKT * FRM EKKO"
   does NOT raise — it silently reinterprets the typo'd keywords as
   column identifiers in a bare arithmetic expression ("SELEKT * FRM"
   parses as SELEKT multiplied by FRM, aliased EKKO). A naive
   try/except around parse() would report that as valid SQL. This
   tool additionally checks that the parsed result is a real
   statement (sqlglot.exp.Query: SELECT/INSERT/UPDATE/DELETE/WITH/...),
   not just a syntactically-legal expression, and rejects it otherwise.
"""
from __future__ import annotations

import sqlglot
from pydantic import BaseModel
from sqlglot import exp

DEFAULT_DIALECT = ""  # sqlglot's generic dialect — no native SAP HANA dialect exists


class SqlValidationResult(BaseModel):
    valid: bool
    dialect: str
    errors: list[str] = []


def validate_sql(query: str, dialect: str = DEFAULT_DIALECT) -> SqlValidationResult:
    query = (query or "").strip()
    if not query:
        return SqlValidationResult(valid=False, dialect=dialect, errors=["empty query"])

    try:
        statements = sqlglot.parse(query, read=dialect or None)
    except sqlglot.errors.ParseError as exc:
        return SqlValidationResult(valid=False, dialect=dialect, errors=[str(exc)])
    except sqlglot.errors.TokenError as exc:
        return SqlValidationResult(valid=False, dialect=dialect, errors=[f"tokenize error: {exc}"])

    errors: list[str] = []
    if not statements or any(s is None for s in statements):
        errors.append("query parsed to nothing")
    else:
        for stmt in statements:
            if not isinstance(stmt, (exp.Query, exp.DDL, exp.DML)):
                errors.append(
                    f"parsed as {type(stmt).__name__}, not a recognized SQL statement "
                    f"(SELECT/INSERT/UPDATE/DELETE/DDL/...) — likely a typo in a keyword "
                    f"that sqlglot's permissive parser reinterpreted as an expression"
                )

    return SqlValidationResult(valid=not errors, dialect=dialect, errors=errors)
