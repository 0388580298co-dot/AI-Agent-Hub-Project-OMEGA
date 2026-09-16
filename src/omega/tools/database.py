"""Parameterized SQLite database tool for local OMEGA workloads."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from .registry import ToolError, ToolValidationError


class SQLiteDatabaseTool:
    name = "database"

    def __init__(self, *, database_path: str | Path, max_rows: int = 1000) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be positive")
        self._path = str(database_path)
        self._max_rows = max_rows

    async def run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        params = arguments.get("params", [])
        if not isinstance(query, str) or not query.strip():
            raise ToolValidationError("query must be a non-empty string")
        if not isinstance(params, Sequence) or isinstance(params, (str, bytes)):
            raise ToolValidationError("params must be an array")
        return await asyncio.to_thread(self._execute, query.strip(), list(params))

    def _execute(self, query: str, params: list[Any]) -> dict[str, Any]:
        if ";" in query.rstrip("; "):
            raise ToolValidationError("Multiple SQL statements are not allowed")
        try:
            with sqlite3.connect(self._path) as connection:
                connection.row_factory = sqlite3.Row
                cursor = connection.execute(query, params)
                if cursor.description is None:
                    connection.commit()
                    return {"rowcount": cursor.rowcount}
                rows = [dict(row) for row in cursor.fetchmany(self._max_rows)]
                return {"columns": [column[0] for column in cursor.description], "rows": rows, "truncated": len(rows) == self._max_rows}
        except sqlite3.Error as exc:
            raise ToolError(f"SQLite operation failed: {exc}") from exc
