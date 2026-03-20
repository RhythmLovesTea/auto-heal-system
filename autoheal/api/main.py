"""
autoheal/api/main.py
M3's file — FastAPI app, SSE stream, Redis consumer background task
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from autoheal.api.routes import containers, incidents, inject
from autoheal.db.database import engine, Base
from autoheal.healer.healer import Healer
from autoheal.utils.redis_client import get_redis
from autoheal.config.settings import settings


# ── Lifespan: startup / shutdown ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all DB tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start the Redis-event consumer as a background task
    task = asyncio.create_task(_redis_event_consumer())
    yield
    # Shutdown: cancel the background task cleanly
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AutoHeal API",
    version="1.0.0",
    description="Self-healing infrastructure orchestrator",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount sub-routers
app.include_router(incidents.router,   prefix="/api/incidents",   tags=["incidents"])
app.include_router(containers.router,  prefix="/api/containers",  tags=["containers"])
app.include_router(inject.router,      prefix="/api/inject",      tags=["inject"])


# ── SSE stream endpoint ───────────────────────────────────────────────────────

@app.get("/stream", summary="Server-Sent Events stream for live incident updates")
async def stream_events():
    """
    Dashboard subscribes here.  Pushes every Redis 'autoheal:events' message
    straight to the browser as an SSE payload.
    """
    async def event_generator():
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(settings.REDIS_EVENT_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(settings.REDIS_EVENT_CHANNEL)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # required for nginx proxying SSE
        },
    )


# ── Background Redis consumer (triggers healer) ───────────────────────────────

async def _redis_event_consumer():
    """
    Listens to the SAME Redis channel as the SSE stream.
    When the monitor publishes an incident event it calls healer.heal().
    This is the glue between M1's monitor and M1's healer.
    """
    healer = Healer()
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.REDIS_EVENT_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode()
            event = json.loads(raw)

            # Only act on new incidents detected by the monitor
            if event.get("type") == "incident_detected":
                container_id = event["container_id"]
                asyncio.create_task(healer.heal(container_id, event))

        except (json.JSONDecodeError, KeyError) as exc:
            print(f"[consumer] Bad event payload: {exc}")
        except Exception as exc:
            print(f"[consumer] Unexpected error: {exc}")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["meta"])
async def healthz():
    return {"status": "ok"}
