"""Dependency-light HTTP adapters for OpenAI-compatible, Anthropic, and local APIs."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any, Mapping

from omega.llm_models.gateway import LLMError, LLMProvider


class HTTPJSONClient:
    """Small stdlib HTTP client kept isolated so provider adapters remain testable."""

    async def post(self, *, url: str, headers: Mapping[str, str], payload: Mapping[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        def request() -> dict[str, Any]:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise LLMError(f"HTTP {exc.code}: {detail[:1000]}") from exc
            except urllib.error.URLError as exc:
                raise LLMError(f"HTTP transport error: {exc.reason}") from exc
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LLMError("Provider returned invalid JSON") from exc
            if not isinstance(value, dict):
                raise LLMError("Provider response must be a JSON object")
            return value
        return await asyncio.to_thread(request)


class OpenAICompatibleProvider:
    """Adapter for OpenAI and OpenAI-compatible /v1/chat/completions endpoints."""

    name = "openai"

    def __init__(self, *, api_key: str | None = None, base_url: str = "https://api.openai.com/v1", client: HTTPJSONClient | None = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = client or HTTPJSONClient()

    async def generate(self, *, model: str, system: str, prompt: str, parameters: Mapping[str, Any]) -> str:
        if not self._api_key:
            raise LLMError("OPENAI_API_KEY is not configured")
        payload = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "max_tokens": parameters.get("max_tokens", 2048), "temperature": parameters.get("temperature", 0.2)}
        data = await self._client.post(url=f"{self._base_url}/chat/completions", headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}, payload=payload)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Invalid OpenAI-compatible response shape") from exc


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, base_url: str = "https://api.anthropic.com/v1", client: HTTPJSONClient | None = None) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._client = client or HTTPJSONClient()

    async def generate(self, *, model: str, system: str, prompt: str, parameters: Mapping[str, Any]) -> str:
        if not self._api_key:
            raise LLMError("ANTHROPIC_API_KEY is not configured")
        payload = {"model": model, "system": system, "messages": [{"role": "user", "content": prompt}], "max_tokens": parameters.get("max_tokens", 2048), "temperature": parameters.get("temperature", 0.2)}
        data = await self._client.post(url=f"{self._base_url}/messages", headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, payload=payload)
        try:
            content = data["content"]
            if not isinstance(content, list) or not content:
                raise ValueError
            return str(content[0]["text"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("Invalid Anthropic response shape") from exc


class LocalOpenAICompatibleProvider(OpenAICompatibleProvider):
    """Local model adapter for Ollama/vLLM/LM Studio servers exposing OpenAI-compatible APIs."""

    name = "local"

    def __init__(self, *, base_url: str = "http://localhost:11434/v1", client: HTTPJSONClient | None = None) -> None:
        super().__init__(api_key="local", base_url=base_url, client=client)
