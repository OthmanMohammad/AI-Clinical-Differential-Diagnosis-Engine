FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.in .
RUN pip install --no-cache-dir pip-tools && \
    pip-compile requirements.in -o requirements.txt && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime ---
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY services/api/app ./app
COPY prompts ./prompts
COPY data ./data

# Create non-root user
RUN useradd -m -r appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
