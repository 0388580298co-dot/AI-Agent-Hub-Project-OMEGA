"""Fail-closed Docker sandbox runner for untrusted agent code."""
from __future__ import annotations
import asyncio, os, shlex, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

class SandboxError(RuntimeError): pass
@dataclass(frozen=True, slots=True)
class SandboxResult:
    stdout: str; stderr: str; return_code: int

class DockerSandbox:
    def __init__(self, *, image: str = "python:3.12-alpine", timeout_seconds: int = 30, memory: str = "256m", cpus: str = "0.5") -> None:
        if timeout_seconds < 1: raise ValueError("timeout_seconds must be positive")
        self.image, self.timeout_seconds, self.memory, self.cpus = image, timeout_seconds, memory, cpus
    async def run_python(self, code: str) -> SandboxResult:
        if not code.strip(): raise ValueError("code cannot be empty")
        if "docker" not in os.getenv("OMEGA_SANDBOX_ENGINE", "docker"): raise SandboxError("sandbox engine is disabled")
        with tempfile.TemporaryDirectory(prefix="omega-sandbox-") as tmp:
            script = Path(tmp) / "main.py"; script.write_text(code, encoding="utf-8")
            cmd: Sequence[str] = ("docker","run","--rm","--network","none","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges","--pids-limit","64","--memory",self.memory,"--cpus",self.cpus,"--user","65532:65532","-v",f"{script}:/app/main.py:ro","-w","/app",self.image,"python","/app/main.py")
            try:
                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError as exc:
                process.kill(); await process.wait(); raise SandboxError("sandbox execution timed out") from exc
            except OSError as exc: raise SandboxError(f"Docker sandbox unavailable: {exc}") from exc
            return SandboxResult(stdout.decode(errors="replace")[:100_000], stderr.decode(errors="replace")[:100_000], int(process.returncode or 0))
