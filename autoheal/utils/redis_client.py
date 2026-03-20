import json
import time

import redis

from autoheal.config.settings import settings

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
        )
    return _client


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _incident_key(container: str) -> str:
    return f"autoheal:incidents:{container}"

def _restart_key(container: str) -> str:
    return f"autoheal:restarts:{container}"

def _cooldown_key(container: str) -> str:
    return f"autoheal:cooldown:{container}"

PUBSUB_CHANNEL = "autoheal:events"


# ---------------------------------------------------------------------------
# Cooldown — prevent hammering a broken container
# ---------------------------------------------------------------------------

def is_on_cooldown(container: str) -> bool:
    """Return True if this container was healed recently."""
    return get_client().exists(_cooldown_key(container)) == 1


def set_cooldown(container: str) -> None:
    """Mark container as recently healed; expires after settings.heal_cooldown seconds."""
    get_client().setex(_cooldown_key(container), settings.heal_cooldown, "1")


# ---------------------------------------------------------------------------
# Restart counter
# ---------------------------------------------------------------------------

def increment_restart_count(container: str) -> int:
    """Bump and return the lifetime restart counter for a container."""
    r = get_client()
    key = _restart_key(container)
    count = r.incr(key)
    # Keep the key alive — refresh TTL on every increment
    r.expire(key, settings.redis_ttl)
    return count


def get_restart_count(container: str) -> int:
    val = get_client().get(_restart_key(container))
    return int(val) if val else 0


# ---------------------------------------------------------------------------
# Incident log (capped list per container)
# ---------------------------------------------------------------------------

MAX_INCIDENTS = 100  # max stored per container


def log_incident(incident_dict: dict) -> None:
    """
    Append a serialised incident to the container's incident list.
    Trims the list to MAX_INCIDENTS to avoid unbounded growth.
    """
    r = get_client()
    key = _incident_key(incident_dict["container_name"])
    payload = json.dumps(incident_dict)
    r.lpush(key, payload)
    r.ltrim(key, 0, MAX_INCIDENTS - 1)
    r.expire(key, settings.redis_ttl)


def get_incidents(container: str, limit: int = 20) -> list[dict]:
    """Return the most recent `limit` incidents for a container."""
    raw = get_client().lrange(_incident_key(container), 0, limit - 1)
    return [json.loads(r) for r in raw]


def get_all_incident_keys() -> list[str]:
    """Return all container names that have incident history."""
    keys = get_client().keys("autoheal:incidents:*")
    return [k.replace("autoheal:incidents:", "") for k in keys]


# ---------------------------------------------------------------------------
# Pub/sub — real-time event broadcast
# ---------------------------------------------------------------------------

def publish_event(incident_dict: dict) -> None:
    """Publish an incident event to the autoheal channel."""
    get_client().publish(PUBSUB_CHANNEL, json.dumps(incident_dict))


def subscribe() -> redis.client.PubSub:
    """Return a PubSub object subscribed to the autoheal events channel."""
    ps = get_client().pubsub()
    ps.subscribe(PUBSUB_CHANNEL)
    return ps
# Alias for compatibility
async def get_redis():
    return get_client()
