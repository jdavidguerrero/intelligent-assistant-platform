#!/usr/bin/env bash
# Convenience script to run search evaluation
#
# Usage:
#   ./scripts/run_eval.sh
#
# This script:
# 1. Starts the API server in background
# 2. Waits for it to be ready
# 3. Runs the evaluation harness
# 4. Stops the server

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🚀 Starting API server..."
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/eval_server.log 2>&1 &
SERVER_PID=$!

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
for i in {1..15}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Server ready (PID: $SERVER_PID)"
        break
    fi
    if [ $i -eq 15 ]; then
        echo "❌ Server failed to start. Check /tmp/eval_server.log"
        kill $SERVER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# Run evaluation
echo ""
echo "📊 Running evaluation..."
PYTHONPATH=. python scripts/eval_search.py

# Stop server
echo ""
echo "🛑 Stopping server..."
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true

echo "✅ Done! Check scripts/eval_results.{json,md} for results."
