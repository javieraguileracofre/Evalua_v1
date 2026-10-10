# Imagen lista para Railway, Fly.io, Google Cloud Run, Render, etc.
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST=0.0.0.0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/scripts/docker_entrypoint.sh \
    && adduser --disabled-password --gecos "" --uid 10001 evalua \
    && mkdir -p /app/logs \
    && chown -R evalua:evalua /app

USER evalua

EXPOSE 8000
# Migración explícita (legacy) en entrypoint; company DBs vía tool/admin.
# AUTO_MIGRATE_ON_STARTUP debe permanecer false en producción.
ENV AUTO_MIGRATE_ON_STARTUP=false
CMD ["sh", "/app/scripts/docker_entrypoint.sh"]
