FROM ollama/ollama:0.40.6 AS ollama

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright IN_DOCKER=True OLLAMA_MODELS=/workspace/ollama OLLAMA_HOST=127.0.0.1:11434 LLM_PROVIDER=ollama OLLAMA_MODEL=qwen3:1.7b
WORKDIR /app
COPY --from=ollama /bin/ollama /usr/local/bin/ollama
COPY --from=ollama /usr/lib/ollama /usr/local/lib/ollama
RUN apt-get update && apt-get install -y --no-install-recommends libopenblas0 libvulkan1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && python -m playwright install --with-deps chromium
COPY agent.py mock_site.py worker.py worker_entrypoint.py /app/
VOLUME /workspace
CMD ["python", "worker_entrypoint.py"]
