# ── Stage 1: Build Next.js Frontend (static export) ──────────────
FROM node:20-slim AS frontend-build

WORKDIR /frontend

# Install dependencies
COPY reverie-frontend/package.json reverie-frontend/package-lock.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY reverie-frontend/ ./

# Empty string = same-origin (FastAPI serves both API and frontend on :8080)
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build


# ── Stage 2: Python Backend + Static Frontend ───────────────────
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files to disc and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application source code
COPY . .

# Copy static export from stage 1 into frontend-out/
# FastAPI's main.py mounts this directory as StaticFiles and serves index.html
# for all non-API paths (client-side routing via trailingSlash: true).
COPY --from=frontend-build /frontend/out ./frontend-out/

# Expose port 8080 — the ONLY port Cloud Run exposes
EXPOSE 8080

# Single-process: FastAPI serves both API and frontend on :8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
