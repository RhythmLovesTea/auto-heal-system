import docker
import time
import json
from autoheal.utils.redis_client import get_client, PUBSUB_CHANNEL

def publish_resolved(container_name: str):
    """Tell the dashboard this service is back healthy."""
    client = get_client()
    event = {
        "type": "resolved",
        "service": container_name,
        "message": f"{container_name} was auto-healed and is back healthy",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    client.publish(PUBSUB_CHANNEL, json.dumps(event))

def get_full_container_name(short_name: str) -> str:
    client = docker.from_env()
    for container in client.containers.list(all=True):
        if short_name in container.name:
            return container.name
    return short_name

def heal(container_name: str) -> bool:
    print(f"[HEAL] Restarting container: {container_name}")
    try:
        client = docker.from_env()
        full_name = get_full_container_name(container_name)
        print(f"[HEAL] Resolved to: {full_name}")
        container = client.containers.get(full_name)
        container.exec_run("rm -f /tmp/unhealthy")
        container.restart()
        print(f"[HEAL] ✓ {full_name} restarted successfully.")
        # Notify dashboard that service is back healthy
        publish_resolved(container_name)
        return True
    except Exception as e:
        print(f"[HEAL] ✗ Failed to restart {container_name}: {e}")
        return False

class Healer:
    def heal(self, container_name: str) -> bool:
        return heal(container_name)

if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "my_container"
    heal(name)
