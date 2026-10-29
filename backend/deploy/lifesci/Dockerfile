FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
# CMO delivery verification runs inside the platform API (OCR fallback needs tesseract).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY benchmark ./benchmark
COPY benchmarks/cmo_ingestion/*.py ./benchmarks/cmo_ingestion/
# Public CHO demo deliveries (CC BY 4.0) served as sample packages.
COPY benchmarks/cmo_ingestion/demo ./benchmarks/cmo_ingestion/demo
RUN pip install '.[lifesci-platform,manufacturing-data,manufacturing-documents]' && useradd --uid 10001 --create-home platform \
    && mkdir -p /data/cmo && chown -R 10001:10001 /data
USER 10001:10001
EXPOSE 8100
CMD ["python", "-m", "src.lifesci", "serve", "--host", "0.0.0.0", "--port", "8100"]
