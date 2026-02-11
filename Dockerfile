# ---------- builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Only build tools here
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Build wheels once
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --no-deps -r requirements.txt -w /wheels


# ---------- runtime ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install only wheels (no compilers) and runtime libs required by some extensions
COPY --from=builder /wheels /wheels
COPY requirements.txt .

# Provide libpq runtime library required by psycopg (installed from wheels).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

COPY . .

# Non-root user (Cloud Run friendly)
RUN useradd -m appuser
USER appuser

CMD ["sh", "-c", "gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8080} \
  --workers 2 \
  --threads 4 \
  --timeout 0"]
