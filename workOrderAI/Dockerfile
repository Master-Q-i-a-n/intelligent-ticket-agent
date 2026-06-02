FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

COPY workOrderAI/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY workOrderAI /app/workOrderAI

EXPOSE 8003

CMD ["python", "-m", "workOrderAI.main"]
