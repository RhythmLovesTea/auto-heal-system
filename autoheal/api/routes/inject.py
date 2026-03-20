from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import docker
import docker.errors

# ─── ROUTER ──────────────────────────────────────────────────────────────────
# Registered in main.py with prefix "/inject"
# POST /inject/fault  → inject a fault into a named container
router = APIRouter()

_docker = docker.from_env()

# ─── REQUEST BODY SCHEMA ──────────────────────────────────────────────────────
# This is what the caller sends in the POST body (JSON).
class FaultRequest(BaseModel):
    service: str        # e.g. "payments-api"
    fault:   str        # e.g. "oom", "cpu", "exit", "slow"

# ─── FAULT TYPES ─────────────────────────────────────────────────────────────
# These match what each victim's inject.py agent can handle.
# The victim containers expose a POST /inject endpoint themselves —
# we just forward the instruction to the right container.
SUPPORTED_FAULTS = {"oom", "cpu", "exit", "slow", "disk"}


# ─── POST /inject/fault ───────────────────────────────────────────────────────
# Injects a fault into a running container.
# Two strategies depending on fault type:
#   1. HTTP forward → call POST /inject on the victim container directly
#      (victim's inject.py is already running inside and listens for this)
#   2. Docker exec  → run a command inside the container as fallback
#
# During the hackathon demo, scripts/inject_all.sh calls this endpoint
# to trigger failures one by one so the audience can watch the healer respond.
@router.post("/fault")
def inject_fault(req: FaultRequest):
    """
    Inject a simulated fault into a victim service.

    Fault types:
      oom  → allocates memory until the container is OOM-killed
      cpu  → spins CPU to 100% to trigger high-CPU alert
      exit → calls sys.exit(1) to crash the process
      slow → adds artificial sleep to all responses (latency fault)
      disk → fills /tmp until disk-full error
    """
    if req.fault not in SUPPORTED_FAULTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fault '{req.fault}'. Supported: {sorted(SUPPORTED_FAULTS)}"
        )

    # ── Strategy 1: HTTP forward to the victim container ─────────────────────
    # Each victim container runs a Flask app with a POST /inject endpoint.
    # Docker Compose puts them on the same network, so we can reach them
    # by their service name (e.g. http://payments-api:5000/inject).
    import httpx

    victim_url = f"http://{req.service}:5000/inject"
    try:
        response = httpx.post(
            victim_url,
            json={"fault": req.fault},
            timeout=5.0,
        )
        response.raise_for_status()
        return {
            "ok":      True,
            "service": req.service,
            "fault":   req.fault,
            "message": f"Fault '{req.fault}' injected into '{req.service}' via HTTP",
        }
    except httpx.HTTPError:
        # ── Strategy 2: Docker exec fallback ─────────────────────────────────
        # If the HTTP forward fails (container not ready, wrong port, etc.),
        # we exec a Python one-liner directly inside the container.
        exec_commands = {
            "oom":  ["python3", "-c",
                     "x=[bytearray(10**6) for _ in iter(int, 1)]"],
            "cpu":  ["python3", "-c",
                     "while True: pass"],
            "exit": ["python3", "-c",
                     "import sys; sys.exit(1)"],
            "slow": ["python3", "-c",
                     "import time; time.sleep(9999)"],
            "disk": ["sh", "-c",
                     "dd if=/dev/zero of=/tmp/fill bs=1M count=2048"],
        }

        try:
            container = _docker.containers.get(req.service)
            container.exec_run(exec_commands[req.fault], detach=True)
            return {
                "ok":      True,
                "service": req.service,
                "fault":   req.fault,
                "message": f"Fault '{req.fault}' injected into '{req.service}' via exec",
            }
        except docker.errors.NotFound:
            raise HTTPException(
                status_code=404,
                detail=f"Container '{req.service}' not found"
            )
        except docker.errors.DockerException as e:
            raise HTTPException(
                status_code=500,
                detail=f"Exec failed: {e}"
            )


# ─── GET /inject/faults ───────────────────────────────────────────────────────
# Returns the list of supported fault types.
# The dashboard can use this to build a dropdown for the demo inject button.
@router.get("/faults")
def list_faults():
    """Returns all supported fault types with descriptions."""
    return {
        "faults": [
            {"id": "oom",  "label": "OOM Kill",      "description": "Allocates memory until kernel kills the container"},
            {"id": "cpu",  "label": "CPU Spike",     "description": "Pegs CPU at 100% to trigger high-CPU alert"},
            {"id": "exit", "label": "Crash (exit 1)","description": "Crashes the process immediately"},
            {"id": "slow", "label": "Latency Fault", "description": "Adds artificial delay to all responses"},
            {"id": "disk", "label": "Disk Fill",     "description": "Fills /tmp to trigger disk-full error"},
        ]
    }
