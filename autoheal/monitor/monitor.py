import json
import time
import threading
import requests
import docker

from autoheal.utils.redis_client import publish_event, set_cooldown, is_on_cooldown

# Map service names to their health check URLs
SERVICES = {
    "auth-service": "http://auth-service:5000/health",
    "db-client": "http://db-client:5000/health",
    "nginx-victim": "http://nginx-victim:5000/health",
    "payments-api": "http://payments-api:5000/health",
    "worker": "http://worker:5000/health",
}


def detect_issues() -> list[dict]:
    issues = []
    for name, url in SERVICES.items():
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code != 200:
                issues.append({"Names": name, "Status": "unhealthy"})
            else:
                print(f"[MONITOR] {name} — healthy")
        except Exception as e:
            issues.append({"Names": name, "Status": "unreachable"})
            print(f"[MONITOR] {name} — unreachable: {e}")
    return issues


def run_monitor_loop(interval: int = 10):
    print(f"[MONITOR] Starting polling loop (every {interval}s)")
    while True:
        try:
            issues = detect_issues()
            if not issues:
                print("[MONITOR] All containers healthy.")
            for container in issues:
                name = container["Names"]
                status = container["Status"]
                if is_on_cooldown(name):
                    print(f"[MONITOR] {name} on cooldown, skipping.")
                    continue
                print(f"[MONITOR] Issue detected: {name} — {status}")
                event = {
                    "type": "incident_detected",
                    "container_id": name,
                    "service": name,
                    "status": status,
                    "message": f"{name} is {status}",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                publish_event(event)
                set_cooldown(name)
        except Exception as e:
            print(f"[MONITOR] Error during poll: {e}")
        time.sleep(interval)


def start_monitor_thread(interval: int = 10) -> threading.Thread:
    t = threading.Thread(target=run_monitor_loop, args=(interval,), daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    run_monitor_loop()
