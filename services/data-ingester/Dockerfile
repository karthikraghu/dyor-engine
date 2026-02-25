FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared modules
COPY shared/ ./shared/

# Copy data-ingester service
COPY services/data-ingester/ ./services/data-ingester/

# Install Python dependencies
RUN pip install --no-cache-dir -r services/data-ingester/requirements.txt

# Create data directory
RUN mkdir -p /app/data

CMD ["python", "-m", "services.data-ingester.fetcher"]
