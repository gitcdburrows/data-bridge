"""High-level DB operations exposed through /sql routes.

Keeps the read-only gate, row cap, and schema introspection in one place
so the HTTP layer stays thin.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.db.engine import get_engine


class SQLError(RuntimeError):
    """Raised for validation / write-guard failures before hitting the DB."""


# Commands that mutate state or change schema. Used for the read-only guard.
_WRITE_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "REPLACE",
    "TRUNCATE",
    "DROP",
    "ALTER",
    "CREATE",
    "GRANT",
    "REVOKE",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "CALL",
    "EXEC",
    "EXECUTE",
}


def _first_keyword(sql: str) -> str:
    # Strip leading SQL comments and whitespace, then take the first word.
    cleaned = re.sub(r"^\s*(--[^\n]*\n|/\*.*?\*/|\s+)+", "", sql, flags=re.DOTALL)
    match = re.match(r"([A-Za-z]+)", cleaned)
    return match.group(1).upper() if match else ""


def _assert_read_only(sql: str) -> None:
    keyword = _first_keyword(sql)
    if keyword in _WRITE_KEYWORDS:
        raise SQLError(
            f"{keyword} statements are blocked because SQL_READ_ONLY=true. "
            "Set SQL_READ_ONLY=false to enable writes."
        )
    # Block chained statements via `;` followed by another keyword.
    # SQLAlchemy typically rejects multi-statements anyway, but defence in depth.
    tail = sql.strip().rstrip(";")
    if ";" in tail:
        raise SQLError("Multiple statements are not allowed in a single request.")


def _jsonify(value: Any) -> Any:
    """Convert DB driver types into JSON-friendly Python primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    return str(value)


class SQLService:
    def __init__(self, engine: Optional[Engine] = None) -> None:
        self._engine = engine or get_engine()
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def execute(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not sql or not sql.strip():
            raise SQLError("Empty SQL statement")
        if self._settings.sql_read_only:
            _assert_read_only(sql)

        cap = min(
            max_rows or self._settings.sql_max_rows,
            self._settings.sql_max_rows,
        )

        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params or {})

            if not result.returns_rows:
                # Read-only guard already blocks writes in RO mode, so we
                # only get here if the user disabled SQL_READ_ONLY.
                conn.commit()
                return {
                    "columns": [],
                    "rows": [],
                    "row_count": result.rowcount,
                    "truncated": False,
                }

            columns = list(result.keys())
            rows_out: List[List[Any]] = []
            truncated = False
            for i, row in enumerate(result):
                if i >= cap:
                    truncated = True
                    break
                rows_out.append([_jsonify(v) for v in row])

            return {
                "columns": columns,
                "rows": rows_out,
                "row_count": len(rows_out),
                "truncated": truncated,
            }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_tables(self, schema: Optional[str] = None) -> Dict[str, Any]:
        insp = inspect(self._engine)
        return {
            "schema": schema,
            "tables": insp.get_table_names(schema=schema),
            "views": insp.get_view_names(schema=schema),
        }

    def describe_table(
        self, table: str, schema: Optional[str] = None
    ) -> Dict[str, Any]:
        insp = inspect(self._engine)
        try:
            cols = insp.get_columns(table, schema=schema)
        except Exception as exc:  # pragma: no cover - driver-specific
            raise SQLError(f"Unable to describe {table!r}: {exc}") from exc

        return {
            "schema": schema,
            "table": table,
            "columns": [
                {
                    "name": c["name"],
                    "type": str(c.get("type")),
                    "nullable": bool(c.get("nullable", True)),
                    "default": _jsonify(c.get("default")),
                    "primary_key": bool(c.get("primary_key", False)),
                }
                for c in cols
            ],
        }
