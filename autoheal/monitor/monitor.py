import subprocess
import json


def detect_issues() -> list[dict]:
    """
    Detect failed or stopped Docker containers.
    Returns a list of dicts with container info.
    """
    result = subprocess.run(
        [
            "docker", "ps", "-a",
            "--format", "{{json .}}",
            "--filter", "status=exited",
            "--filter", "status=dead",
        ],
        capture_output=True,
        text=True,
    )

    containers = []
    for line in result.stdout.strip().splitlines():
        if line:
            containers.append(json.loads(line))

    # Also grab unhealthy running containers
    result_unhealthy = subprocess.run(
        [
            "docker", "ps",
            "--format", "{{json .}}",
            "--filter", "health=unhealthy",
        ],
        capture_output=True,
        text=True,
    )

    for line in result_unhealthy.stdout.strip().splitlines():
        if line:
            containers.append(json.loads(line))

    return containers


if __name__ == "__main__":
    issues = detect_issues()
    if issues:
        for c in issues:
            print(f"[ISSUE] {c['Names']} — status: {c['Status']}")
    else:
        print("All containers healthy.")
