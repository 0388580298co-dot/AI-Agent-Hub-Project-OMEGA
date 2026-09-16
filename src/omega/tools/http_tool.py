"""Controlled outbound HTTP tool for OMEGA."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .registry import ToolError, ToolValidationError


class HTTPRequestTool:
    name = "http_request"

    def __init__(self, *, allowed_hosts: tuple[str, ...] = (), max_response_bytes: int = 1_000_000) -> None:
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self._allowed_hosts = tuple(host.lower() for host in allowed_hosts)
        self._max_response_bytes = max_response_bytes

    async def run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        method = str(arguments["method"]).upper()
        url = str(arguments["url"])
        headers = arguments.get("headers", {})
        body = arguments.get("body")
        self._validate(method, url, headers, body)
        return await asyncio.to_thread(self._request, method, url, headers, body)

    def _validate(self, method: str, url: str, headers: Any, body: Any) -> None:
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ToolValidationError("Unsupported HTTP method")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ToolValidationError("URL must use HTTP(S) and include a hostname")
        host = parsed.hostname.lower()
        if self._allowed_hosts and host not in self._allowed_hosts:
            raise ToolValidationError(f"Host is not allow-listed: {host}")
        if not isinstance(headers, Mapping):
            raise ToolValidationError("headers must be an object")
        if body is not None and not isinstance(body, (str, Mapping, list)):
            raise ToolValidationError("body must be string, object, array, or null")

    def _request(self, method: str, url: str, headers: Mapping[str, Any], body: Any) -> dict[str, Any]:
        payload: bytes | None = None
        request_headers = {str(k): str(v) for k, v in headers.items()}
        if body is not None:
            if isinstance(body, str):
                payload = body.encode("utf-8")
            else:
                payload = json.dumps(body).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read(self._max_response_bytes + 1)
                if len(data) > self._max_response_bytes:
                    raise ToolError("HTTP response exceeds configured size limit")
                text = data.decode("utf-8", errors="replace")
                return {"status": response.status, "url": response.geturl(), "headers": dict(response.headers), "body": text}
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            raise ToolError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ToolError(f"HTTP transport error: {exc.reason}") from exc
