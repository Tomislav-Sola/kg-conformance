# Walking-skeleton image. Phase 1: build the app and serve it with uvicorn.
# Runtime dependencies only (no .[dev]); tests run on the host, not in the image.
FROM python:3.12-slim

# Do not buffer stdout/stderr, do not write .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install runtime dependencies. Copy the metadata and the package, then install.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
