#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# inject_all.sh
# Fires a sequence of failure scenarios against payments-api and watches
# autoheal respond. Run this while the stack is up.
# ---------------------------------------------------------------------------

API="http://localhost:8000"
AUTOHEAL="http://localhost:8080"
CONTAINER="payments-api"

RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
CYN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYN}[inject]${NC} $*"; }
ok()   { echo -e "${GRN}[ok]${NC}    $*"; }
warn() { echo -e "${YLW}[warn]${NC}  $*"; }
fail() { echo -e "${RED}[fail]${NC}  $*"; }

wait_for_restart() {
  local name=$1
  log "Waiting for autoheal to detect and restart ${name}..."
  for i in $(seq 1 20); do
    sleep 3
    STATUS=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
    if [ "$STATUS" = "running" ]; then
      ok "${name} is running again (attempt ${i})"
      return 0
    fi
    echo "  → status: ${STATUS} (${i}/20)"
  done
  fail "${name} did not recover in time."
  return 1
}

separator() {
  echo ""
  echo -e "${YLW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YLW}  $*${NC}"
  echo -e "${YLW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

separator "Preflight checks"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  fail "${CONTAINER} is not running. Start the stack first: ./scripts/start.sh"
  exit 1
fi

ok "Stack is up. Starting injection sequence."
echo ""

# ---------------------------------------------------------------------------
# Scenario 1: Hard stop (docker stop)
# ---------------------------------------------------------------------------

separator "Scenario 1 — Hard stop via docker stop"
log "Stopping ${CONTAINER}..."
docker stop "$CONTAINER"
ok "Container stopped. Waiting for autoheal..."
wait_for_restart "$CONTAINER"
sleep 2

# ---------------------------------------------------------------------------
# Scenario 2: Process crash via /chaos endpoint
# ---------------------------------------------------------------------------

separator "Scenario 2 — Process crash via GET /chaos"
log "Hitting ${API}/chaos ..."
curl -sf "${API}/chaos" && echo "" || warn "/chaos returned non-2xx (container may already be flapping)"
wait_for_restart "$CONTAINER"
sleep 2

# ---------------------------------------------------------------------------
# Scenario 3: Repeated hits to /health to trigger random failure modes
# ---------------------------------------------------------------------------

separator "Scenario 3 — Hammering /health to induce random failures"
log "Sending 30 rapid requests to ${API}/health ..."
for i in $(seq 1 30); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API}/health" || echo "000")
  printf "  req %02d → HTTP %s\n" "$i" "$CODE"
  sleep 0.3
done

# ---------------------------------------------------------------------------
# Scenario 4: Manual scan trigger
# ---------------------------------------------------------------------------

separator "Scenario 4 — Manual scan via AutoHeal API"
log "POST ${AUTOHEAL}/scan ..."
SCAN=$(curl -sf -X POST "${AUTOHEAL}/scan" | python3 -m json.tool 2>/dev/null || echo "{}")
echo "$SCAN"

# ---------------------------------------------------------------------------
# Final status
# ---------------------------------------------------------------------------

separator "Final status"
log "AutoHeal incident history:"
curl -sf "${AUTOHEAL}/incidents/" | python3 -m json.tool 2>/dev/null || warn "Could not reach autoheal API"

echo ""
log "AutoHeal container summary:"
curl -sf "${AUTOHEAL}/status" | python3 -m json.tool 2>/dev/null || true

echo ""
ok "Injection sequence complete."
