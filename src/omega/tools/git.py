"""Read-only Git inspection tool for safe agent workflows."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .registry import ToolError, ToolValidationError


class GitInspectionTool:
    name = "git"

    def __init__(self, *, repository_root: str | Path) -> None:
        self._root = Path(repository_root).resolve()
        if not (self._root / ".git").exists():
            raise ValueError("repository_root must contain a .git directory")

    async def run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        operation = str(arguments["operation"])
        if operation not in {"status", "log", "diff"}:
            raise ToolValidationError("operation must be status, log, or diff")
        command = {"status": ["status", "--short"], "log": ["log", "-10", "--oneline"], "diff": ["diff", "--stat"]}[operation]
        return await asyncio.to_thread(self._run, command)

    def _run(self, command: list[str]) -> dict[str, Any]:
        try:
            result = subprocess.run(["git", *command], cwd=self._root, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(f"Git operation failed: {exc}") from exc
        if result.returncode != 0:
            raise ToolError(result.stderr.strip() or f"git exited with code {result.returncode}")
        return {"operation": command[0], "output": result.stdout}
