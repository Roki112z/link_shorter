import asyncio
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.config import settings
from app.models import Link
from app.utils import now_utc, resolve_cache_key, stats_cache_key


async def cleanup_expired_links_once(db: AsyncSession) -> int:
    current_time = now_utc()
    result = await db.execute(
        select(Link).where(
            Link.expires_at.is_not(None),
            Link.expires_at <= current_time,
        )
    )
    expired_links = list(result.scalars().all())

    if not expired_links:
        return 0

    cache_keys: list[str] = []
    for link in expired_links:
        cache_keys.extend([resolve_cache_key(link.short_code), stats_cache_key(link.short_code)])
        await db.delete(link)

    await db.commit()
    await cache.delete(*cache_keys)
    return len(expired_links)


async def cleanup_worker(
    session_factory: Callable[[], AsyncSession],
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        async with session_factory() as db:
            try:
                await cleanup_expired_links_once(db)
            except Exception:
                await db.rollback()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.cleanup_interval_seconds)
        except asyncio.TimeoutError:
            continue

