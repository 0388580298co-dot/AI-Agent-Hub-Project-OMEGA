"""Provider-neutral LLM gateway with routing, retries, timeouts and usage accounting."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class LLMError(RuntimeError):
    """Base error for LLM operations."""


class LLMConfigurationError(LLMError):
    """Raised for invalid provider/model configuration."""


class LLMProvider(Protocol):
    name: str

    async def generate(self, *, model: str, system: str, prompt: str, parameters: Mapping[str, Any]) -> str:
        """Generate text from a provider."""


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str
    prompt: str
    model: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.system.strip() or not self.prompt.strip():
            raise ValueError("system and prompt must be non-empty")
        if self.max_tokens < 1 or self.max_tokens > 1_000_000:
            raise ValueError("max_tokens must be between 1 and 1,000,000")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: str
    model: str
    priority: int = 100
    enabled: bool = True


class LLMRouter:
    """Deterministic route selector; lower priority values are preferred."""

    def __init__(self, routes: list[ProviderRoute] | tuple[ProviderRoute, ...]) -> None:
        if not routes:
            raise ValueError("At least one LLM route is required")
        self._routes = tuple(sorted(routes, key=lambda r: r.priority))

    def select(self, requested_model: str | None = None) -> ProviderRoute:
        candidates = [r for r in self._routes if r.enabled and (requested_model is None or r.model == requested_model)]
        if not candidates:
            raise LLMConfigurationError(f"No enabled LLM route for model={requested_model!r}")
        return candidates[0]


class TokenEstimator:
    """Provider-independent conservative token estimate used for budgets."""

    @staticmethod
    def estimate(text: str) -> int:
        return max(1, (len(text) + 3) // 4)


class LLMGateway:
    """Async gateway that hides provider details from agents."""

    def __init__(self, *, providers: Mapping[str, LLMProvider], router: LLMRouter, max_retries: int = 2, retry_delay_seconds: float = 0.5) -> None:
        if max_retries < 0 or retry_delay_seconds < 0:
            raise ValueError("Retry configuration is invalid")
        self._providers = dict(providers)
        self._router = router
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds
        for route in self._router._routes:
            if route.provider not in self._providers:
                raise LLMConfigurationError(f"Missing provider for route: {route.provider}")

    async def generate(self, *, system: str, prompt: str, **kwargs: Any) -> str:
        request = LLMRequest(system=system, prompt=prompt, model=kwargs.get("model"), max_tokens=int(kwargs.get("max_tokens", 2048)), temperature=float(kwargs.get("temperature", 0.2)), timeout_seconds=float(kwargs.get("timeout_seconds", 60.0)), metadata=kwargs.get("metadata", {}))
        response = await self.complete(request)
        return response.text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        route = self._router.select(request.model)
        provider = self._providers[route.provider]
        parameters = {"max_tokens": request.max_tokens, "temperature": request.temperature, **dict(request.metadata)}
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            started = time.perf_counter()
            try:
                text = await asyncio.wait_for(provider.generate(model=route.model, system=request.system, prompt=request.prompt, parameters=parameters), timeout=request.timeout_seconds)
                if not isinstance(text, str) or not text.strip():
                    raise LLMError("Provider returned an empty response")
                return LLMResponse(text=text, provider=route.provider, model=route.model, input_tokens=TokenEstimator.estimate(request.system + request.prompt), output_tokens=TokenEstimator.estimate(text), latency_ms=round((time.perf_counter() - started) * 1000, 2), metadata={"attempt": attempt + 1})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay * (2**attempt))
        raise LLMError(f"LLM request failed after {self._max_retries + 1} attempts: {last_error}") from last_error
