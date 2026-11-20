# Container image for the API and the built interface.
# Build the interface first:  cd frontend && npm ci && npm run build && cd ..
# Then:                        docker build -t labmeter .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./
COPY models ./models
COPY frontend/dist ./frontend/dist

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
# DATABASE_URL must be set at run time (for example with docker run -e DATABASE_URL=...).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
