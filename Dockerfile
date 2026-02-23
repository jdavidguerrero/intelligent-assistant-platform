# Musical Intelligence Platform — API container
#
# Build:   docker build -t musical-intelligence .
# Run:     docker run -p 8000:8000 --env-file .env musical-intelligence
# Compose: docker compose -f compose.yml -f compose.api.yml up --build

FROM python:3.12-slim

# System dependencies for librosa (audio analysis) and psycopg (postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package itself (for module imports)
RUN pip install --no-cache-dir -e .

# Create data directory for SQLite memory store
RUN mkdir -p /app/data

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Healthcheck — liveness probe every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
