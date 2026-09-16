"""Stable model-provider contract used by the gateway and applications."""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class ILLMProvider(Protocol):
    name: str

    async def generate(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        parameters: Mapping[str, Any],
    ) -> str:
        """Generate a completion without exposing vendor-specific types."""
        raise NotImplementedError
