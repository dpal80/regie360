#!/bin/sh
set -e
# Aggiorna lo schema del database prima di avviare il backend.
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --workers "${WEB_WORKERS:-4}" --proxy-headers --forwarded-allow-ips "*"
