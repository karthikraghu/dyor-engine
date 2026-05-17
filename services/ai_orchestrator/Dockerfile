FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ ./shared/
COPY services/ai_orchestrator/ ./services/ai_orchestrator/

RUN pip install --no-cache-dir -r services/ai_orchestrator/requirements.txt \
    && pip install --no-cache-dir python-dotenv

RUN mkdir -p /app/data

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "services.ai_orchestrator.app:app", "--host", "0.0.0.0", "--port", "8010"]
