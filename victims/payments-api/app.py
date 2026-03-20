import os
import random
import signal
import threading
import time

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Payments API (Faulty)")

# Tune via env — lower = more chaos
CRASH_PROBABILITY = float(os.getenv("CRASH_PROBABILITY", 0.3))  # 30% chance per /health hit
SLOW_PROBABILITY  = float(os.getenv("SLOW_PROBABILITY",  0.2))  # 20% chance of slow response

_request_count = 0


def _suicide(delay: float = 0.5):
    """Kill the process after a short delay (lets the response go out first)."""
    def _kill():
        time.sleep(delay)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_kill, daemon=True).start()


@app.get("/health")
def health():
    global _request_count
    _request_count += 1
    roll = random.random()

    # --- hard crash: process dies, container exits ---
    if roll < CRASH_PROBABILITY * 0.4:
        _suicide()
        return {"status": "dying", "note": "process will exit shortly"}

    # --- HTTP 500: service is up but reports unhealthy ---
    if roll < CRASH_PROBABILITY * 0.7:
        raise HTTPException(status_code=500, detail="internal meltdown")

    # --- slow response: healthcheck timeout bait ---
    if roll < CRASH_PROBABILITY * 0.7 + SLOW_PROBABILITY:
        time.sleep(random.uniform(3, 8))
        raise HTTPException(status_code=503, detail="response too slow")

    return {"status": "ok", "requests_served": _request_count}


@app.get("/payments")
def list_payments():
    if random.random() < 0.15:
        raise HTTPException(status_code=503, detail="payment service unavailable")
    return {
        "payments": [
            {"id": 1, "amount": 99.99,  "status": "settled"},
            {"id": 2, "amount": 249.00, "status": "pending"},
        ]
    }


@app.get("/chaos")
def force_crash():
    """Manually trigger a process crash — useful for demo / testing."""
    _suicide(delay=0.1)
    return {"status": "crash initiated"}
