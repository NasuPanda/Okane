# Okane: one container, one port. The frontend is built in stage 1 and served by FastAPI.
# Confidential data is NEVER copied into the image: mount it at /data at run time.
#
#   docker build -t okane .
#   docker run -p 8000:8000 -v "$PWD/data:/data" okane
#
# /data must contain rates.csv (see backend/tests/data/rates.sample.csv) and inbox/ with the
# workbooks. The DuckDB file is created in /data. Ollama on the host is reachable with
#   -e OKANE_OLLAMA_URL=http://host.docker.internal:11434

FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# The fixtures are synthetic; the build references them for VITE_API_MODE=fixtures.
COPY fixtures/ /src/fixtures/
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OKANE_DATA_DIR=/data \
    OKANE_INBOX_DIR=/data/inbox \
    OKANE_SAMPLE_DIR=/data/sample \
    OKANE_RATES_PATH=/data/rates.csv \
    OKANE_DB_PATH=/data/okane.duckdb \
    OKANE_FRONTEND_DIST=/app/frontend/dist \
    OKANE_CORS_ORIGINS='[]'
WORKDIR /app/backend
COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app
RUN pip install --no-cache-dir . && useradd --create-home okane && mkdir -p /data && chown okane /data
COPY --from=frontend /src/frontend/dist /app/frontend/dist
USER okane
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
