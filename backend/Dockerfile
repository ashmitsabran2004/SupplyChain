FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY graph /app/graph
COPY backend /app/backend

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend
ENV MODEL_DIR=/app/backend/models
ENV DATA_DIR=/app/backend/data

COPY backend/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
