# auto-heal-system
# ⚡ AutoHeal — AI-Powered Container Self-Healing

AutoHeal monitors your Docker containers, detects incidents, uses Claude AI to diagnose root causes, and automatically applies healing actions — all in real time.

## Quick Start

```bash
# 1. Clone and enter the repo
git clone <your-repo> && cd autoheal

# 2. Set your Anthropic API key
cp .env.example .env
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# 3. Launch everything
bash scripts/start.sh
```

| Service   | URL                          |
|-----------|------------------------------|
| Dashboard | http://localhost:3000        |
| API       | http://localhost:8000        |
| API Docs  | http://localhost:8000/docs   |

## Demo — Inject a Fault

```bash
# Crash one container
curl -X POST http://localhost:8000/api/inject/payments-api/crash

# CPU stress
curl -X POST http://localhost:8000/api/inject/worker/cpu

# Chaos mode — crash everything
bash scripts/inject_all.sh
```

Watch the dashboard at **http://localhost:3000** — AutoHeal will detect, diagnose with Claude, and restart the container within ~15 seconds.

## Architecture

```
Monitor ──▶ Redis pub/sub ──▶ Healer
   │                             │
   ▼                             ▼
SQLite DB              Claude AI Analyzer
   │                             │
   └──────────▶ FastAPI ◀────────┘
                   │
               Dashboard (React)
```

## How It Works

1. **Monitor** polls Docker every 10s for CPU, memory, restart count, and container status
2. When a threshold is breached, an **Incident** is created in SQLite
3. **Healer** picks up open incidents and calls **Claude AI** to diagnose root cause
4. Claude returns a structured action: `RESTART`, `STOP`, `KILL`, `INVESTIGATE`, etc.
5. Healer executes the action via Docker API
6. Incident is marked resolved; optional **Slack alert** is sent

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required** |
| `MONITOR_INTERVAL` | `10` | Seconds between checks |
| `CPU_THRESHOLD` | `80` | % CPU to trigger incident |
| `MEMORY_THRESHOLD` | `85` | % memory to trigger incident |
| `RESTART_THRESHOLD` | `3` | Restart count to trigger |
| `MAX_HEAL_ATTEMPTS` | `3` | Max auto-heal tries |
| `HEAL_COOLDOWN` | `60` | Seconds between heals per container |
| `SLACK_WEBHOOK_URL` | — | Optional Slack alerts |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```
