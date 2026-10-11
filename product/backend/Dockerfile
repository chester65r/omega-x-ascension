FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    AUTO_CREATE_SCHEMA=false
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn omega_api.main:app --app-dir /app/src --host 0.0.0.0 --port ${PORT:-8000}"]
