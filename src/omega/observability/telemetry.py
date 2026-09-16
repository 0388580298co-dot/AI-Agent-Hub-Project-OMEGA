"""OpenTelemetry-compatible tracing boundary with a dependency-free fallback."""
from __future__ import annotations
import time, uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping

@dataclass(slots=True)
class Span:
    name: str; trace_id: str; span_id: str; started_at: float; attributes: dict[str, Any] = field(default_factory=dict); ended_at: float | None = None; error: str | None = None
    def finish(self, *, error: Exception | None = None) -> None: self.ended_at=time.time(); self.error=str(error) if error else None
    @property
    def latency_ms(self) -> float | None: return None if self.ended_at is None else round((self.ended_at-self.started_at)*1000,2)

class Telemetry:
    def __init__(self) -> None: self.spans: list[Span] = []
    @asynccontextmanager
    async def span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> AsyncIterator[Span]:
        trace_id = str(uuid.uuid4()); span=Span(name, trace_id, str(uuid.uuid4()), time.time(), dict(attributes or {})); self.spans.append(span)
        try: yield span
        except Exception as exc: span.finish(error=exc); raise
        else: span.finish()
    def export_otel(self) -> None:
        """Install/configure an OpenTelemetry exporter at the application boundary."""
        try:
            from opentelemetry import trace
        except ImportError: return
        tracer=trace.get_tracer("omega")
        for span in self.spans:
            with tracer.start_as_current_span(span.name) as otel:
                for key,value in span.attributes.items(): otel.set_attribute(key,str(value))
                if span.error: otel.record_exception(Exception(span.error))
