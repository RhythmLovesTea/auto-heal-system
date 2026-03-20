#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting AutoHeal stack..."

# Copy example env if .env doesn't exist
if [ ! -f .env ]; then
  cp .env .env
  echo "📋 Created .env from .env — review before running in prod."
fi

docker compose up --build -d

echo ""
echo "✅ Stack is up."
echo "   AutoHeal API  → http://localhost:8080/docs"
echo "   Payments API  → http://localhost:8000/health"
echo ""
echo "Tail logs with:  docker compose logs -f autoheal"
