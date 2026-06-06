# backend/Dockerfile
# Multi-stage build for the InsightHub FastAPI backend.
# Final image is slim — only production dependencies included.
# Deployed to Azure App Service (Linux, Python 3.11).

# ── Stage 1: Build dependencies ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system dependencies needed to compile pyodbc
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    unixodbc-dev \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver 18 for SQL Server (required by pyodbc)
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Production image ──────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy ODBC driver from builder
COPY --from=builder /usr/lib/x86_64-linux-gnu/libmsodbcsql*.so* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /opt/microsoft /opt/microsoft

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Install minimal runtime system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    && rm -rf /var/lib/apt/lists/*

# Copy application source
COPY app/ ./app/

# Create non-root user (OWASP: never run as root in production)
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port (Azure App Service maps port 8000 by default)
EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Start Uvicorn — Azure App Service sets PORT env var automatically
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log"]
