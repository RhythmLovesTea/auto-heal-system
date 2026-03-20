import subprocess


def heal(container_name: str) -> bool:
    """
    Restart a Docker container by name.
    Returns True on success, False on failure.
    """
    print(f"[HEAL] Restarting container: {container_name}")
    result = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"[HEAL] ✓ {container_name} restarted successfully.")
        return True
    else:
        print(f"[HEAL] ✗ Failed to restart {container_name}: {result.stderr.strip()}")
        return False


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "my_container"
    heal(name)
