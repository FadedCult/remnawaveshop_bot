#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/remnashop"
BACKUP_DIR="${BACKUP_DIR:-/opt/remnashop/backups}"
DB_FILE="${DB_FILE:-/opt/remnashop/data/remnashop.db}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"
cp "$DB_FILE" "$BACKUP_DIR/remnashop_${STAMP}.db"
find "$BACKUP_DIR" -type f -name "remnashop_*.db" -mtime +14 -delete

echo "Backup completed: $BACKUP_DIR/remnashop_${STAMP}.db"
