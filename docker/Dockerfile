# Multi-stage Dockerfile
FROM python:3.14-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for rapid package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Sync project dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Production stage
FROM base AS production
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
RUN uv sync --frozen --no-dev
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

# Development stage
FROM base AS development
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --frozen
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
