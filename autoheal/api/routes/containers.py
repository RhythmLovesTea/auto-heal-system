from fastapi import APIRouter, HTTPException
import docker
import docker.errors

# ─── ROUTER ──────────────────────────────────────────────────────────────────
# Registered in main.py with prefix "/containers"
# GET /containers/        → list all containers + their status
# GET /containers/{name}  → info for one container
# POST /containers/{name}/restart → manually restart a container
router = APIRouter()

# Docker client — talks to the Docker daemon on the same host
# Uses the Unix socket /var/run/docker.sock (mounted in docker-compose.yml)
_docker = docker.from_env()


def _container_info(container) -> dict:
    """
    Pull the fields we care about from a Docker container object.
    This is what gets sent to the dashboard's service cards.
    """
    stats = {}
    try:
        # .stats(stream=False) gives a one-shot snapshot of CPU/mem usage
        raw = container.stats(stream=False)
        cpu_delta   = raw["cpu_stats"]["cpu_usage"]["total_usage"] - \
                      raw["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = raw["cpu_stats"]["system_cpu_usage"] - \
                       raw["precpu_stats"]["system_cpu_usage"]
        num_cpus    = raw["cpu_stats"].get("online_cpus", 1)
        cpu_pct     = round((cpu_delta / system_delta) * num_cpus * 100, 1) if system_delta > 0 else 0.0

        mem_used  = raw["memory_stats"].get("usage", 0)
        mem_limit = raw["memory_stats"].get("limit", 1)
        mem_pct   = round((mem_used / mem_limit) * 100, 1)

        stats = {"cpu_percent": cpu_pct, "mem_percent": mem_pct}
    except Exception:
        # Container might be stopped — stats unavailable
        stats = {"cpu_percent": None, "mem_percent": None}

    return {
        "name":        container.name,
        "status":      container.status,   # "running", "exited", "restarting" …
        "image":       container.image.tags[0] if container.image.tags else "unknown",
        "id":          container.short_id,
        **stats,
    }


# ─── GET /containers ──────────────────────────────────────────────────────────
# Lists all containers (running + stopped).
# The monitor (M1's code) also calls Docker directly, but the dashboard
# can use this endpoint for a manual refresh or initial load.
@router.get("/")
def list_containers():
    """
    Returns status + CPU/mem for every container.
    The dashboard's service cards are populated from this.
    """
    try:
        containers = _docker.containers.list(all=True)
        return [_container_info(c) for c in containers]
    except docker.errors.DockerException as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")


# ─── GET /containers/{name} ───────────────────────────────────────────────────
# Returns info for a single container by name.
# Example: GET /containers/payments-api
@router.get("/{name}")
def get_container(name: str):
    """
    Returns status + CPU/mem for one named container.
    Returns 404 if the container doesn't exist.
    """
    try:
        container = _docker.containers.get(name)
        return _container_info(container)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{name}' not found")
    except docker.errors.DockerException as e:
        raise HTTPException(status_code=503, detail=f"Docker error: {e}")


# ─── POST /containers/{name}/restart ─────────────────────────────────────────
# Manually triggers a container restart from the dashboard.
# In the hackathon demo, you can wire a button in App.jsx to call this.
@router.post("/{name}/restart")
def restart_container(name: str):
    """
    Manually restarts a container.
    The healer (M1) calls this automatically, but you can also
    trigger it from the dashboard for demo purposes.
    """
    try:
        container = _docker.containers.get(name)
        container.restart(timeout=10)
        return {"ok": True, "message": f"Container '{name}' restarted"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container '{name}' not found")
    except docker.errors.DockerException as e:
        raise HTTPException(status_code=500, detail=f"Restart failed: {e}")
