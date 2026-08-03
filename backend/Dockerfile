# syntax=docker/dockerfile:1

# --- Stage 1: builder — instala dependencias en un venv aislado ---
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# --- Stage 2: runtime — imagen final, sin toolchain de build ---
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src ./src

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Se respeta $PORT si el entorno lo define (Railway y la mayoría de PaaS
# asignan uno dinámico y enrutan solo a ese puerto). Sin él, 8000, que es lo
# que espera docker-compose y el healthcheck de arriba.
CMD ["sh", "-c", "exec uvicorn src.presentation.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
