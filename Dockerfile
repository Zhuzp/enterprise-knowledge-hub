FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

COPY . .

CMD ["arq", "app.workers.settings.WorkerSettings"]
