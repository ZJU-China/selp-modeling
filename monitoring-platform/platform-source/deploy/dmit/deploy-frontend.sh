#!/bin/bash
# ⚠ 目前不允许部署
# dmit 部署已停用：前端与后端均部署在 iGEM 服务器（127.0.0.1）上，
# 由 systemd 用户服务 md-frontend（vite :5173）与 md-server（API :3001）
# 托管。请勿再部署到 dmit。
# 方案A：MD 前端部署到 dmit（静态 dist + nginx /api 反向代理）。
# 幂等，可重复执行。默认从本机构建并 rsync，随后安装 nginx 配置并 reload。
# 用法：
#   ./deploy-frontend.sh            # 构建 + 推送 + 装 nginx 配置
#   ./deploy-frontend.sh --no-build # 只推送现有 dist
set -euo pipefail

TARGET=dmit
REMOTE_ROOT=/var/www/md-frontend
NGINX_SITE=md-frontend
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$REPO_ROOT/frontend/dist"
LOCAL_CONF="$(dirname "$0")/md-frontend.conf"

echo "==> 0. 预检：dmit 上后端隧道可达性（经 127.0.0.1:3001）"
if ! ssh "$TARGET" 'curl -s -m 10 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3001/api/tasks' 2>/dev/null | grep -q 200; then
    echo "WARN: dmit 127.0.0.1:3001 未返回 200（后端隧道未就绪）。"
    echo "      先按 backend-tunnel.service 在 iGEM 服务器上建好反向隧道，否则 /api 会 502。"
    read -r -p "仍要继续部署静态文件吗？[y/N] " ans || exit 1
    [[ "$ans" == y || "$ans" == Y ]] || exit 1
fi

if [[ "${1:-}" != "--no-build" ]]; then
    echo "==> 1. 构建前端"
    (cd "$REPO_ROOT/frontend" && npm run build)
fi

echo "==> 2. 推送 dist 到 ${TARGET}:${REMOTE_ROOT}"
ssh "$TARGET" "mkdir -p $REMOTE_ROOT"
rsync -az --delete "$DIST/" "$TARGET:$REMOTE_ROOT/"

echo "==> 3. 安装 nginx 站点配置"
ssh "$TARGET" "apt-get install -y nginx >/dev/null 2>&1 || true; mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled"
scp "$LOCAL_CONF" "$TARGET:/etc/nginx/sites-available/$NGINX_SITE"
ssh "$TARGET" "ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/$NGINX_SITE; rm -f /etc/nginx/sites-enabled/default; nginx -t && nginx -s reload"

echo "==> 4. 验证"
ssh "$TARGET" 'curl -s -o /dev/null -w "static:   %{http_code}\n" http://127.0.0.1/ ; curl -s -m 10 -o /dev/null -w "api/tasks:%{http_code}\n" http://127.0.0.1/api/tasks'

echo "完成。浏览器访问 http://192.0.2.30/"
