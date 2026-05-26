# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base
WORKDIR /app

# Layer 1: system build deps (rarely changes — cached separately)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends gcc

# Layer 2: Python deps (cached until requirements.txt changes)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Layer 3: source code (invalidated on every code change; layers 1+2 stay warm)
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "main.py"]
