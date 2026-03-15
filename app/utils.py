import random
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Link


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_cache_key(short_code: str) -> str:
    return f"link:resolve:{short_code}"


def stats_cache_key(short_code: str) -> str:
    return f"link:stats:{short_code}"


async def generate_unique_short_code(db: AsyncSession) -> str:
    alphabet = string.ascii_letters + string.digits

    for _ in range(30):
        candidate = "".join(random.choices(alphabet, k=settings.short_code_length))
        exists = await db.execute(select(Link.id).where(Link.short_code == candidate))
        if exists.scalar_one_or_none() is None:
            return candidate

    raise RuntimeError("Не удалось сгенерировать уникальный short_code")
