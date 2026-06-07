#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# backend/startup.sh
#
# Azure App Service startup script for the InsightHub FastAPI backend.
#
# How it is used:
#   Set the App Service "Startup Command" to: startup.sh
#   Azure runs this script from /home/site/wwwroot after each deployment.
#
# App Service environment:
#   - Python 3.11 on Linux
#   - Working directory: /home/site/wwwroot (contents of the deployed zip)
#   - All environment variables set in App Service Configuration are available
#   - Port 8000 is exposed via WEBSITES_PORT app setting
#
# Gunicorn vs uvicorn:
#   Azure App Service defaults to Gunicorn for Python apps, but FastAPI is
#   an ASGI application — it requires an ASGI server. We run uvicorn directly.
#   For production, use --workers 2 (2× vCPUs on B2 SKU). Increase on P-series.
# ─────────────────────────────────────────────────────────────────────────────

set -e  # Exit immediately if any command fails

echo "[startup.sh] InsightHub FastAPI backend starting..."
echo "[startup.sh] Python version: $(python --version)"
echo "[startup.sh] Working directory: $(pwd)"

# Install / upgrade dependencies on each deployment.
# SCM_DO_BUILD_DURING_DEPLOYMENT=true handles this for zip deploys,
# but the explicit install here ensures fresh dependencies on restart.
if [ -f "requirements.txt" ]; then
    echo "[startup.sh] Installing Python dependencies..."
    pip install -r requirements.txt --quiet --no-cache-dir
    echo "[startup.sh] Dependencies installed."
fi

# Start uvicorn ASGI server
# --host 0.0.0.0  : Accept connections on all interfaces (required for App Service)
# --port 8000     : Must match WEBSITES_PORT app setting
# --workers 2     : One worker per vCPU on B2; increase for P-series SKUs
# --proxy-headers : Trust X-Forwarded-For from Azure's front-end proxy
# --forwarded-allow-ips "*" : Accept forwarded headers from Azure infrastructure
echo "[startup.sh] Starting uvicorn..."

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --log-level info
