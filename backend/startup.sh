#!/bin/bash
# InsightHub FastAPI — Azure App Service startup
#
# Strategy: direct pip install at startup (no Oryx build).
# WEBSITES_CONTAINER_START_TIME_LIMIT=1800 gives 30 min; pip install takes ~8 min.
# Source files are at /home/site/wwwroot (deployed directly via az webapp deploy).
cd /home/site/wwwroot
pip install -r requirements.txt --quiet --no-cache-dir
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --log-level info
