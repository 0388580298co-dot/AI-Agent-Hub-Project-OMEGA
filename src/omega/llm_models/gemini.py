"""Google Gemini adapter using the Gemini REST generateContent API."""
from __future__ import annotations
import asyncio, json, os, urllib.error, urllib.request
from typing import Any, Mapping
from omega.llm_models.gateway import LLMError

class GeminiProvider:
    name = "gemini"
    def __init__(self, *, api_key: str | None = None, base_url: str = "https://generativelanguage.googleapis.com/v1beta") -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._base_url = base_url.rstrip("/")
    async def generate(self, *, model: str, system: str, prompt: str, parameters: Mapping[str, Any]) -> str:
        if not self._api_key: raise LLMError("GEMINI_API_KEY is not configured")
        payload = {"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"temperature":parameters.get("temperature",0.2),"maxOutputTokens":parameters.get("max_tokens",2048)}}
        def call() -> dict[str, Any]:
            req = urllib.request.Request(f"{self._base_url}/models/{model}:generateContent?key={self._api_key}", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=float(parameters.get("timeout_seconds",60))) as response: return json.loads(response.read().decode())
            except urllib.error.HTTPError as exc: raise LLMError(f"Gemini HTTP {exc.code}: {exc.read().decode(errors='replace')[:1000]}") from exc
            except (urllib.error.URLError, json.JSONDecodeError) as exc: raise LLMError(f"Gemini transport/JSON error: {exc}") from exc
        data = await asyncio.to_thread(call)
        try: return str(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError) as exc: raise LLMError("Invalid Gemini response shape") from exc
