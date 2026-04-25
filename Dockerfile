FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright Chromium on Debian Bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 \
    libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libdbus-1-3 libexpat1 \
    libgbm1 libglib2.0-0t64 \
    libpango-1.0-0 libcairo2 \
    libasound2t64 \
    libx11-6 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxrandr2 libxcb1 libxkbcommon0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY backend/requirements.txt backend/requirements.txt
COPY scrapers/requirements.txt scrapers/requirements.txt
RUN pip install --no-cache-dir \
    -r backend/requirements.txt \
    -r scrapers/requirements.txt

# Install Playwright Chromium browser
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Copy application source
COPY backend/ backend/
COPY scrapers/ scrapers/
COPY frontend/ frontend/

# SQLite lives on /data so a volume can persist it across restarts
RUN mkdir -p /data
ENV DB_PATH=/data/scholarships.db
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
