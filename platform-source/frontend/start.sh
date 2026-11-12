#!/usr/bin/env bash
# Flow-centric frontend on port 5174.
set -e
cd "$(dirname "$0")"
fuser -k 5174/tcp 2>/dev/null || true
sleep 1
nohup npx vite --host 0.0.0.0 --port 5174 > /tmp/flow-frontend.log 2>&1 &
echo "flow-frontend started on :5174 (log: /tmp/flow-frontend.log)"
