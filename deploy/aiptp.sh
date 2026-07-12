#!/usr/bin/env bash
# AIPTP one-command launcher (PRD §5).
#   ./deploy/aiptp.sh up | down | logs | status | backup | update
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f "$HERE/compose.yaml")

case "${1:-help}" in
  up)
    "${COMPOSE[@]}" up -d --build
    echo "AIPTP is starting — open http://localhost:${AIPTP_PORT:-8420}"
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  logs)
    "${COMPOSE[@]}" logs -f aiptp
    ;;
  status)
    "${COMPOSE[@]}" ps
    docker inspect --format 'health: {{.State.Health.Status}}' aiptp 2>/dev/null || true
    ;;
  backup)
    docker exec aiptp python -c "
from aiptp.config import settings
from aiptp.security.backup import backup_database
print(backup_database(settings.resolved_db_url(), settings.data_dir))"
    ;;
  update)
    "${COMPOSE[@]}" build --pull aiptp
    "${COMPOSE[@]}" up -d
    ;;
  *)
    echo "Usage: $0 {up|down|logs|status|backup|update}"
    exit 1
    ;;
esac
