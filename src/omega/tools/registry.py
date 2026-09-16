"""Safe, allow-listed tool registry for PROJECT OMEGA.

The code executor intentionally evaluates only a small arithmetic AST. It never
executes Python bytecode, imports modules, touches the filesystem, or starts a process.
"""

from __future__ import annotations

import ast
import asyncio
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class ToolError(RuntimeError):
    """Base class for tool failures."""


class ToolValidationError(ToolError, ValueError):
    """Raised when tool input is invalid."""


class Tool(Protocol):
    name: str

    async def run(self, arguments: Mapping[str, Any]) -> Any:
        """Execute the tool."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Tool name must be non-empty and trimmed")
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")


class ToolRegistry:
    """Allow-list registry with schema-level validation and per-call timeout."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._specs: dict[str, ToolSpec] = {}

    def register(self, tool: Tool, spec: ToolSpec) -> None:
        if spec.name != tool.name:
            raise ValueError("ToolSpec.name must equal tool.name")
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = tool
        self._specs[spec.name] = spec

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise KeyError(name)
        self._tools.pop(name)
        self._specs.pop(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs[name] for name in self.names())

    async def execute(self, name: str, arguments: Mapping[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolValidationError(f"Tool is not allow-listed: {name}")
        if not isinstance(arguments, Mapping):
            raise ToolValidationError("Tool arguments must be an object")
        self._validate_arguments(self._specs[name], arguments)
        try:
            return await asyncio.wait_for(tool.run(dict(arguments)), timeout=self._specs[name].timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise ToolError(f"Tool timed out: {name}") from exc
        except asyncio.CancelledError:
            raise
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"Tool {name} failed: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _validate_arguments(spec: ToolSpec, arguments: Mapping[str, Any]) -> None:
        schema = spec.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(required, list) or not isinstance(properties, Mapping):
            raise ToolValidationError(f"Invalid schema for tool: {spec.name}")
        missing = [key for key in required if key not in arguments]
        if missing:
            raise ToolValidationError(f"Missing required arguments: {missing}")
        unknown = [key for key in arguments if key not in properties]
        if unknown:
            raise ToolValidationError(f"Unknown arguments: {unknown}")
        for key, value in arguments.items():
            expected = properties[key].get("type") if isinstance(properties[key], Mapping) else None
            valid = {"string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool), "number": isinstance(value, (int, float)) and not isinstance(value, bool), "boolean": isinstance(value, bool), "object": isinstance(value, Mapping), "array": isinstance(value, list)}.get(expected, True)
            if not valid:
                raise ToolValidationError(f"Invalid type for argument '{key}': expected {expected}")


class WebSearchTool:
    name = "web_search"

    def __init__(self, corpus: Mapping[str, str] | None = None) -> None:
        self._corpus = dict(corpus or {
            "autonomous agents": "Autonomous agents combine perception, planning, tool use, memory, and reflection.",
            "multi agent systems": "Multi-agent systems coordinate specialized agents through a shared task graph and explicit state.",
            "agent operating system": "An agent operating system provides runtime, tools, memory, orchestration, policy, observability, and evaluation.",
        })

    async def run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"]).strip()
        limit = int(arguments.get("limit", 5))
        terms = set(query.lower().split())
        scored = []
        for title, content in self._corpus.items():
            haystack = f"{title} {content}".lower()
            score = sum(haystack.count(term) for term in terms if term)
            if score:
                scored.append((score, title, content))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return {"query": query, "results": [{"title": title, "snippet": content, "score": score} for score, title, content in scored[:limit]], "source": "OMEGA_SIMULATED_CORPUS"}


class SafeCodeExecutionTool:
    name = "code_execution"

    async def run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        expression = str(arguments["expression"]).strip()
        if len(expression) > 500:
            raise ToolValidationError("Expression exceeds 500 characters")
        tree = ast.parse(expression, mode="eval")
        value = await asyncio.to_thread(self._evaluate, tree.body)
        return {"expression": expression, "result": value, "sandbox": "arithmetic-only"}

    @classmethod
    def _evaluate(cls, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            if not math.isfinite(float(node.value)):
                raise ToolValidationError("Non-finite numeric constants are forbidden")
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = cls._evaluate(node.operand)
            return +value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
            left, right = cls._evaluate(node.left), cls._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(float(right)) > 12:
                raise ToolValidationError("Exponent is too large")
            if isinstance(node.op, ast.Div) and right == 0 or isinstance(node.op, (ast.FloorDiv, ast.Mod)) and right == 0:
                raise ToolValidationError("Division by zero")
            operations = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right, ast.Mult: lambda: left * right, ast.Div: lambda: left / right, ast.FloorDiv: lambda: left // right, ast.Mod: lambda: left % right, ast.Pow: lambda: left ** right}
            result = operations[type(node.op)]()
            if not isinstance(result, (int, float)) or not math.isfinite(float(result)) or abs(float(result)) > 1e100:
                raise ToolValidationError("Arithmetic result is outside safe bounds")
            return result
        raise ToolValidationError(f"Unsupported expression node: {type(node).__name__}")
