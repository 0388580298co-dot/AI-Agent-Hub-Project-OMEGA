"""Sandboxed filesystem tool restricted to an injected workspace root."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Mapping

from .registry import ToolError, ToolValidationError


class SandboxedFilesystemTool:
    name = "filesystem"

    def __init__(self, *, root: str | Path, max_read_bytes: int = 2_000_000) -> None:
        self._root = Path(root).resolve()
        self._max_read_bytes = max_read_bytes

    def _path(self, relative: str) -> Path:
        if not relative or Path(relative).is_absolute():
            raise ToolValidationError("path must be a relative path")
        target = (self._root / relative).resolve()
        try:
            target.relative_to(self._root)
        except ValueError as exc:
            raise ToolValidationError("Path escapes filesystem sandbox") from exc
        return target

    async def run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        operation = str(arguments["operation"])
        path = self._path(str(arguments["path"]))
        if operation == "read":
            return await asyncio.to_thread(self._read, path)
        if operation == "write":
            content = arguments.get("content")
            if not isinstance(content, str):
                raise ToolValidationError("content must be a string")
            return await asyncio.to_thread(self._write, path, content)
        if operation == "list":
            return await asyncio.to_thread(self._list, path)
        raise ToolValidationError("operation must be read, write, or list")

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ToolError("File does not exist")
        if path.stat().st_size > self._max_read_bytes:
            raise ToolError("File exceeds read size limit")
        return {"path": str(path.relative_to(self._root)), "content": path.read_text(encoding="utf-8")}

    def _write(self, path: Path, content: str) -> dict[str, Any]:
        if len(content.encode("utf-8")) > self._max_read_bytes:
            raise ToolError("Content exceeds write size limit")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": str(path.relative_to(self._root)), "bytes": len(content.encode("utf-8"))}

    def _list(self, path: Path) -> dict[str, Any]:
        if not path.is_dir():
            raise ToolError("Directory does not exist")
        return {"path": str(path.relative_to(self._root)), "entries": sorted(item.name for item in path.iterdir())}
