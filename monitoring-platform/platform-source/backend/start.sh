#!/bin/bash
cd "$(dirname "$0")"
fuser -k 3001/tcp 2>/dev/null
sleep 1
nohup node index.js > /tmp/md-backend.log 2>&1 &
echo "Backend PID: $!"
sleep 2
cat /tmp/md-backend.log
