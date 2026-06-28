FROM python:3.11-slim

WORKDIR /app

# CJK font so rendered daily images show Chinese text correctly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/base-requirements.txt
COPY apps/api/requirements.txt /tmp/api-requirements.txt
RUN pip install --no-cache-dir -r /tmp/base-requirements.txt -r /tmp/api-requirements.txt

COPY . /app

ENV PYTHONPATH=/app:/app/apps/api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/apps/api"]
