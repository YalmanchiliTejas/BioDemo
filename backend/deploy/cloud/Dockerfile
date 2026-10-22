FROM python:3.12-slim-bookworm AS control
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY benchmark ./benchmark
RUN pip install '.[cloud-backend]'
USER 10001:10001
CMD ["python", "-m", "src.cloud_backend.entrypoint", "api"]

# Supply a Linux image with the built Prime SDK and Linux node_modules at
# /opt/prime-agent using --build-context prime_runtime=docker-image://...@sha256:...
FROM prime_runtime AS prime
FROM node:22-bookworm-slim AS node
FROM control AS agent
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install '.[manufacturing-data]' ipython ipykernel
COPY --from=prime /opt/prime-agent /opt/prime-agent
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY prime_skills ./prime_skills
ENV PRIME_AGENT_BUNDLE_ROOT=/opt/prime-agent HOME=/tmp
USER 10001:10001
CMD ["python", "-m", "src.cloud_backend.agent"]
