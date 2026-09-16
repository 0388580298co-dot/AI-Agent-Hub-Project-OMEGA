"""Async message-broker boundary with Redis and RabbitMQ adapters."""
from __future__ import annotations

import json
from typing import Any, Mapping, Protocol


class MessageBroker(Protocol):
    async def publish(self, topic: str, message: Mapping[str, Any]) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class RedisBroker:
    def __init__(self, url: str = "redis://redis:6379/0") -> None:
        try:
            from redis.asyncio import Redis
        except ImportError as exc:
            raise RuntimeError("Install omega-agent-os[redis]") from exc
        self._client = Redis.from_url(url, decode_responses=True)

    async def publish(self, topic: str, message: Mapping[str, Any]) -> None:
        await self._client.publish(topic, json.dumps(dict(message), separators=(",", ":")))

    async def close(self) -> None:
        await self._client.aclose()


class RabbitMQBroker:
    def __init__(self, url: str = "amqp://guest:guest@rabbitmq:5672/") -> None:
        try:
            import aio_pika
        except ImportError as exc:
            raise RuntimeError("Install omega-agent-os[rabbitmq]") from exc
        self._aio_pika = aio_pika
        self._url = url
        self._connection: Any = None

    async def _channel(self) -> Any:
        if self._connection is None or self._connection.is_closed:
            self._connection = await self._aio_pika.connect_robust(self._url)
        return await self._connection.channel()

    async def publish(self, topic: str, message: Mapping[str, Any]) -> None:
        channel = await self._channel()
        exchange = await channel.declare_exchange("omega", self._aio_pika.ExchangeType.TOPIC, durable=True)
        await exchange.publish(
            self._aio_pika.Message(json.dumps(dict(message), separators=(",", ":")).encode()),
            routing_key=topic,
        )

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
