#!/bin/bash
# Legacy start script — kept for backwards compatibility.
# The Dockerfile now uses a single uvicorn process directly.
# FastAPI serves both the API and the frontend on port 8080.
set -e
exec uvicorn main:app --host 0.0.0.0 --port 8080
