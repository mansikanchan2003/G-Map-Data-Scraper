# =============================================================================
# G-Map Data Scraper 2.0 — Backend Dockerfile
# Python 3.12 slim + Playwright Chromium
# Runs as non-root user (appuser) for security.
# =============================================================================

FROM python:3.12-slim AS base

# ---------------------------------------------------------------------------
# System dependencies required by Playwright Chromium on Debian/Ubuntu
# These are the standard Chromium runtime dependencies.
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    wget \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Create non-root user
# ---------------------------------------------------------------------------
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --shell /bin/false --create-home appuser

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser and its OS-level dependencies.
# PLAYWRIGHT_BROWSERS_PATH is set so the browser lives in /app/.playwright
# rather than the user home, making it accessible to the appuser.
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright
RUN python -m playwright install chromium && \
    python -m playwright install-deps chromium

# ---------------------------------------------------------------------------
# Copy application source
# ---------------------------------------------------------------------------
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Copy data files needed for config sync (xlsx files)
# These can alternatively be mounted as a volume at runtime.
COPY "Geocoded_Ad_Targeting_Locations_FINAL.xlsx" .
COPY "G-Map Scraper Categories.xlsx" .

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
# Create the data directory for SQLite fallback (if DATABASE_URL is sqlite:)
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser

# Expose the FastAPI port
EXPOSE 8000

# ---------------------------------------------------------------------------
# Health check — validates the API is alive every 30s
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
# Uses uvicorn directly.
# For production, set workers=1 because Playwright jobs are resource-intensive.
# Scale by running multiple containers, not multiple workers per container.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
