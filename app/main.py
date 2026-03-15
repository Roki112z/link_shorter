import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.cache import cache
from app.cleanup import cleanup_worker
from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.routers import auth, links


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cache.connect()

    stop_event = asyncio.Event()
    cleaner = asyncio.create_task(cleanup_worker(AsyncSessionLocal, stop_event))
    app.state.cleanup_stop_event = stop_event
    app.state.cleanup_task = cleaner
    app.state.redis_enabled = cache.redis is not None

    yield

    stop_event.set()
    cleaner.cancel()
    with suppress(asyncio.CancelledError):
        await cleaner

    await cache.close()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(links.router)


@app.get("/health")
async def health() -> dict[str, bool | str]:
    return {"status": "ok", "redis_cache": cache.redis is not None}

