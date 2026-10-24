FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY benchmark ./benchmark
RUN pip install '.[lifesci-platform]' && useradd --uid 10001 --create-home platform
USER 10001:10001
EXPOSE 8100
CMD ["python", "-m", "src.lifesci", "serve", "--host", "0.0.0.0", "--port", "8100"]
