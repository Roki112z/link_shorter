import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings


class CacheManager:
    def __init__(self) -> None:
        self.redis: Redis | None = None

    async def connect(self) -> None:
        try:
            self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
            await self.redis.ping()
        except Exception:
            self.redis = None

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.close()

    async def get_json(self, key: str) -> dict[str, Any] | None:
        if self.redis is None:
            return None
        try:
            data = await self.redis.get(key)
            if data is None:
                return None
            return json.loads(data)
        except (RedisError, json.JSONDecodeError):
            return None

    async def set_json(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        if self.redis is None:
            return
        try:
            cache_ttl = ttl if ttl is not None else settings.cache_ttl_seconds
            await self.redis.set(key, json.dumps(value), ex=cache_ttl)
        except RedisError:
            return

    async def delete(self, *keys: str) -> None:
        if self.redis is None or not keys:
            return
        try:
            await self.redis.delete(*keys)
        except RedisError:
            return


cache = CacheManager()

