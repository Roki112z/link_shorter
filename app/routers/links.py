from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_optional_user
from app.cache import cache
from app.database import get_db
from app.models import Link, User
from app.schemas import (
    LinkCreateRequest,
    LinkInfoResponse,
    LinkStatsResponse,
    LinkUpdateRequest,
    MessageResponse,
    SearchResponse,
)
from app.utils import ensure_utc, generate_unique_short_code, now_utc, resolve_cache_key, stats_cache_key

router = APIRouter(prefix="/links", tags=["links"])


def build_short_url(request: Request, short_code: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/links/{short_code}"


def parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return ensure_utc(parsed)


def validate_link_owner(link: Link, user: User) -> None:
    if link.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ссылка создана анонимно, ее нельзя изменять или удалять",
        )
    if link.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для управления этой ссылкой",
        )


async def delete_if_expired(link: Link, db: AsyncSession) -> bool:
    expires_at = ensure_utc(link.expires_at)
    if expires_at is None:
        return False
    if expires_at > now_utc():
        return False

    await db.delete(link)
    await db.commit()
    await cache.delete(resolve_cache_key(link.short_code), stats_cache_key(link.short_code))
    return True


@router.post("/shorten", response_model=LinkInfoResponse, status_code=status.HTTP_201_CREATED)
async def create_short_link(
    payload: LinkCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> LinkInfoResponse:
    if payload.custom_alias:
        existing_alias = await db.execute(select(Link).where(Link.short_code == payload.custom_alias))
        if existing_alias.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Этот custom_alias уже занят",
            )
        short_code = payload.custom_alias
    else:
        short_code = await generate_unique_short_code(db)

    link = Link(
        short_code=short_code,
        original_url=str(payload.original_url),
        expires_at=payload.expires_at,
        owner_id=current_user.id if current_user else None,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    await cache.set_json(
        resolve_cache_key(short_code),
        {
            "original_url": link.original_url,
            "expires_at": ensure_utc(link.expires_at).isoformat() if link.expires_at else None,
        },
    )

    return LinkInfoResponse(
        short_code=link.short_code,
        short_url=build_short_url(request, link.short_code),
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )


@router.get("/search", response_model=SearchResponse)
async def search_by_original_url(
    request: Request,
    original_url: str = Query(..., description="Оригинальный URL"),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    result = await db.execute(select(Link).where(Link.original_url == original_url).order_by(Link.created_at.desc()))
    links = list(result.scalars().all())

    active_links: list[Link] = []
    for link in links:
        if await delete_if_expired(link, db):
            continue
        active_links.append(link)

    return SearchResponse(
        items=[
            LinkInfoResponse(
                short_code=link.short_code,
                short_url=build_short_url(request, link.short_code),
                original_url=link.original_url,
                created_at=link.created_at,
                expires_at=link.expires_at,
            )
            for link in active_links
        ]
    )


@router.get("/{short_code}/stats", response_model=LinkStatsResponse)
async def get_link_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
) -> LinkStatsResponse:
    cache_key = stats_cache_key(short_code)
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return LinkStatsResponse(
            short_code=cached["short_code"],
            original_url=cached["original_url"],
            created_at=datetime.fromisoformat(cached["created_at"]),
            expires_at=parse_optional_datetime(cached.get("expires_at")),
            visits=cached["visits"],
            last_used_at=parse_optional_datetime(cached.get("last_used_at")),
        )

    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")

    if await delete_if_expired(link, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка истекла и удалена")

    response = LinkStatsResponse(
        short_code=link.short_code,
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        visits=link.visits,
        last_used_at=link.last_used_at,
    )

    await cache.set_json(
        cache_key,
        {
            "short_code": response.short_code,
            "original_url": response.original_url,
            "created_at": response.created_at.isoformat(),
            "expires_at": ensure_utc(response.expires_at).isoformat() if response.expires_at else None,
            "visits": response.visits,
            "last_used_at": ensure_utc(response.last_used_at).isoformat()
            if response.last_used_at
            else None,
        },
    )
    return response


@router.get("/{short_code}")
async def redirect_to_original(
    short_code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    cached = await cache.get_json(resolve_cache_key(short_code))
    if cached is not None:
        expires_at = parse_optional_datetime(cached.get("expires_at"))
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            await cache.delete(resolve_cache_key(short_code))
            result = await db.execute(select(Link).where(Link.short_code == short_code))
            link = result.scalar_one_or_none()
            if link is not None:
                await db.delete(link)
                await db.commit()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка истекла и удалена")

        result = await db.execute(select(Link).where(Link.short_code == short_code))
        link = result.scalar_one_or_none()
        if link is None:
            await cache.delete(resolve_cache_key(short_code))
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")

        link.visits += 1
        link.last_used_at = now_utc()
        await db.commit()
        await cache.delete(stats_cache_key(short_code))
        return RedirectResponse(url=cached["original_url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")

    if await delete_if_expired(link, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка истекла и удалена")

    link.visits += 1
    link.last_used_at = now_utc()
    await db.commit()

    await cache.set_json(
        resolve_cache_key(short_code),
        {
            "original_url": link.original_url,
            "expires_at": ensure_utc(link.expires_at).isoformat() if link.expires_at else None,
        },
    )
    await cache.delete(stats_cache_key(short_code))
    return RedirectResponse(url=link.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.put("/{short_code}", response_model=LinkInfoResponse)
async def update_short_link(
    short_code: str,
    payload: LinkUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LinkInfoResponse:
    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")

    if await delete_if_expired(link, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка истекла и удалена")

    validate_link_owner(link, current_user)

    if payload.original_url is not None:
        link.original_url = str(payload.original_url)
    if payload.expires_at is not None:
        link.expires_at = payload.expires_at

    await db.commit()
    await db.refresh(link)
    await cache.delete(resolve_cache_key(short_code), stats_cache_key(short_code))

    return LinkInfoResponse(
        short_code=link.short_code,
        short_url=build_short_url(request, link.short_code),
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )


@router.delete("/{short_code}", response_model=MessageResponse)
async def delete_short_link(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не найдена")

    if await delete_if_expired(link, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка истекла и удалена")

    validate_link_owner(link, current_user)

    await db.delete(link)
    await db.commit()
    await cache.delete(resolve_cache_key(short_code), stats_cache_key(short_code))

    return MessageResponse(message="Ссылка успешно удалена")
