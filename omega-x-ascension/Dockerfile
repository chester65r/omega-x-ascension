FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --system omega && useradd --system --gid omega --home /app omega
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN pip install --no-cache-dir .
USER omega
EXPOSE 8000
CMD ["uvicorn", "omega.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
