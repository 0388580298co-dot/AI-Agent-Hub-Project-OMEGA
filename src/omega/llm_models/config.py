"""Environment-driven provider selection; business code never imports a vendor adapter."""
from __future__ import annotations
import os
from dataclasses import dataclass
from omega.llm_models.gateway import LLMGateway, LLMRouter, ProviderRoute
from omega.llm_models.gemini import GeminiProvider
from omega.llm_models.providers import AnthropicProvider, LocalOpenAICompatibleProvider, OpenAICompatibleProvider

@dataclass(frozen=True, slots=True)
class LLMSettings:
    provider: str = "local"
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434/v1"
    @classmethod
    def from_env(cls) -> "LLMSettings": return cls(os.getenv("OMEGA_LLM_PROVIDER","local").lower(), os.getenv("OMEGA_LLM_MODEL","llama3.2"), os.getenv("OMEGA_LLM_BASE_URL","http://localhost:11434/v1"))

def build_gateway(settings: LLMSettings | None = None) -> LLMGateway:
    s=settings or LLMSettings.from_env(); providers={"openai":OpenAICompatibleProvider(base_url=os.getenv("OPENAI_BASE_URL","https://api.openai.com/v1")),"anthropic":AnthropicProvider(),"gemini":GeminiProvider(),"local":LocalOpenAICompatibleProvider(base_url=s.base_url)}
    if s.provider not in providers: raise ValueError(f"Unsupported OMEGA_LLM_PROVIDER={s.provider!r}")
    return LLMGateway(providers=providers, router=LLMRouter([ProviderRoute(s.provider,s.model,priority=1)]))
