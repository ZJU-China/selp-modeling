#!/bin/bash
# ⚠ 目前不允许部署
# dmit 部署已停用：前端与后端均部署在 iGEM 服务器（127.0.0.1）上，
# 由 systemd 用户服务 md-frontend（vite :5173）与 md-server（API :3001）
# 托管。请勿再部署到 dmit。
# 在 iGEM 服务器上安装并启动到 dmit 的后端反向隧道。
set -euo pipefail
UNIT=backend-tunnel.service
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
DST=/etc/systemd/system/$UNIT
install -m 644 "$SELF_DIR/$UNIT" "$DST"
systemctl daemon-reload
systemctl enable --now "$UNIT"
systemctl status --no-pager "$UNIT"
