FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared modules
COPY shared/ ./shared/

# Copy sandbox service
COPY services/sandbox/ ./services/sandbox/

# Install Python dependencies
RUN pip install --no-cache-dir -r services/sandbox/requirements.txt \
    && pip install --no-cache-dir python-dotenv

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Run the sandbox
CMD ["python", "-m", "uvicorn", "services.sandbox.app:app", "--host", "0.0.0.0", "--port", "8000"]
