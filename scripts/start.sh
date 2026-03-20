#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting AutoHeal stack..."

# Copy example env if .env doesn't exist
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📋 Created .env from .env.example — review before running in prod."
fi

docker compose up --build -d

echo ""
echo "✅ Stack is up."
echo "   AutoHeal API  → http://localhost:8000/docs"
echo "   Dashboard     → http://localhost:5173"
echo "   Victims       → http://localhost:5001-5005/health"
echo ""
echo "Tail logs with:  docker compose logs -f autoheal"
