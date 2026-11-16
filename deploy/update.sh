#!/usr/bin/env bash
# Keeps the live portal on the newest commit of main. Run by cron on the server every 15 minutes
# (see deploy/crash-portal.cron), so the Monday retrieval job and every push reach the live site unattended.
# Does nothing when main has not moved.
set -euo pipefail

cd "$(dirname "$0")/.."
exec 9> /tmp/crash-portal-update.lock
flock -n 9 || exit 0   # an earlier run is still building

git fetch --quiet origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0

git merge --quiet --ff-only origin/main
docker compose -f deploy/compose.yaml up -d --build --quiet-pull
docker image prune -f > /dev/null
echo "$(date -u +%FT%TZ) updated to $(git rev-parse --short HEAD)"
