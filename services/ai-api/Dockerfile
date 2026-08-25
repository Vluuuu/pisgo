FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY ml /app/ml
COPY services/ai-api /app/services/ai-api
COPY shared /app/shared

RUN pip install --no-cache-dir -e /app/ml \
    && pip install --no-cache-dir -r /app/services/ai-api/requirements.txt

ENV PYTHONPATH="/app/ml/src:/app/services/ai-api" \
    PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "/app/services/ai-api", "--host", "0.0.0.0", "--port", "8001"]
