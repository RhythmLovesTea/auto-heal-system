import requests
import sys

# This script flips the service into an unhealthy state
SERVICE_URL = "http://localhost:5000"

def inject_fault():
    # We signal the app to go unhealthy via an env file or internal flag
    # Simplest approach: write a flag file the app checks
    with open("/tmp/unhealthy", "w") as f:
        f.write("1")
    print("Fault injected — service will now return 500")

def recover():
    import os
    if os.path.exists("/tmp/unhealthy"):
        os.remove("/tmp/unhealthy")
    print("Recovered — service will now return 200")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "recover":
        recover()
    else:
        inject_fault()
