FROM python:3.11-slim-bullseye

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    chmod +x /usr/local/bin/uv && \
    rm /uv-installer.sh

# Copy project files
COPY . /app

# Install dependencies from pyproject.toml using uv
RUN uv sync --locked

# Create and switch to a non-root user
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# FastAPI environment setup
ENV FASTAPI_HOST=0.0.0.0
ENV FASTAPI_PORT=7860
EXPOSE 7860

# Healthcheck for FastAPI app
HEALTHCHECK --interval=5s --timeout=30s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:7860/health || exit 1

# Entry point: first run set_vector_store.py to initialize ChromaDB, then run FastAPI app
CMD ["sh", "-c", "python set_vector_store.py && uv run uvicorn main:app --host 0.0.0.0 --port 7860 --reload"]
