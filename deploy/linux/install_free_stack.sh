#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/ag-baby
DATA_DIR=/var/lib/ag-baby/observations
SERVICE_NAME=ag-baby-free-stack

sudo useradd --system --home "$APP_DIR" --shell /sbin/nologin agbaby 2>/dev/null || true
sudo install -d -o agbaby -g agbaby "$APP_DIR" "$DATA_DIR" /etc/ag-baby

sudo cp -r apps packages configs "$APP_DIR"/
sudo cp deploy/linux/ag-baby-free-stack.service /etc/systemd/system/
sudo chown -R agbaby:agbaby "$APP_DIR" "$DATA_DIR"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager status "$SERVICE_NAME"
