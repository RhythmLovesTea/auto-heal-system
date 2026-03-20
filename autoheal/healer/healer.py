import docker

def heal(container_name: str) -> bool:
    print(f"[HEAL] Restarting container: {container_name}")
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart()
        print(f"[HEAL] ✓ {container_name} restarted successfully.")
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
