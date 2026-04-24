# Imagen lista para Railway, Fly.io, Google Cloud Run, etc.
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST=0.0.0.0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Cloud suele inyectar PORT; local por defecto 8000
CMD ["sh", "-c", "exec uvicorn main:app --host ${UVICORN_HOST:-0.0.0.0} --port ${PORT:-8000}"]
