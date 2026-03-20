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
from autoheal.utils.redis_client import get_redis, PUBSUB_CHANNEL
from autoheal.config.settings import settings


# ── Lifespan: startup / shutdown ──────────────────────────────────────────────
from autoheal.monitor.monitor import start_monitor_thread

@asynccontextmanager
async def lifespan(app: FastAPI):
    from autoheal.db.database import init_db
    init_db()

    # Start the monitor in a background thread
    start_monitor_thread(interval=10)

    task = asyncio.create_task(_redis_event_consumer())
    yield
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
    async def event_generator():
        import asyncio
        from autoheal.utils.redis_client import get_client, PUBSUB_CHANNEL
        loop = asyncio.get_event_loop()
        redis = get_client()
        pubsub = redis.pubsub()
        pubsub.subscribe(PUBSUB_CHANNEL)
        try:
            while True:
                message = await loop.run_in_executor(None, pubsub.get_message, True, 1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
                else:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            pubsub.unsubscribe(PUBSUB_CHANNEL)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _redis_event_consumer():
    import asyncio
    from autoheal.utils.redis_client import get_client, PUBSUB_CHANNEL
    healer = Healer()
    loop = asyncio.get_event_loop()
    redis = get_client()
    pubsub = redis.pubsub()
    pubsub.subscribe(PUBSUB_CHANNEL)

    while True:
        try:
            message = await loop.run_in_executor(None, pubsub.get_message, True, 1.0)
            if message and message["type"] == "message":
                raw = message["data"]
                if isinstance(raw, bytes):
                    raw = raw.decode()
                event = json.loads(raw)
                if event.get("type") == "incident_detected":
                    container_id = event["container_id"]
                    healer.heal(container_id)
            else:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"[consumer] Error: {exc}")
            await asyncio.sleep(1)
# ── Background Redis consumer (triggers healer) ───────────────────────────────


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["meta"])
async def healthz():
    return {"status": "ok"}
