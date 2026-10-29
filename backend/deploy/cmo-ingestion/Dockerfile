FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/pyproject.toml backend/README.md ./
COPY backend/src ./src
COPY backend/benchmark ./benchmark
COPY backend/docs ./docs
COPY backend/benchmarks/cmo_ingestion/*.py ./benchmarks/cmo_ingestion/
# Public CHO demo deliveries (CC BY 4.0) served as sample packages.
COPY backend/benchmarks/cmo_ingestion/demo ./benchmarks/cmo_ingestion/demo
RUN pip install --no-cache-dir '.[app,manufacturing-data,benchmarks,manufacturing-documents]'
RUN useradd --uid 10001 --create-home cmo && mkdir -p /data /app/.prime && chown -R cmo:cmo /data /app/.prime
USER cmo
EXPOSE 8000
CMD ["python","-m","uvicorn","benchmark.application.api:create_app","--factory","--host","0.0.0.0","--port","8000"]

FROM nginx:1.27-alpine AS web
COPY --from=frontend /frontend/dist /usr/share/nginx/html
COPY backend/deploy/cmo-ingestion/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
