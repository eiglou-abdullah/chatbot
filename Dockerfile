FROM python:3.11-slim-bullseye

# Set working directory
WORKDIR /app

# Install system dependencies and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    ca-certificates \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade SQLite (ChromaDB requires >= 3.35.0)
RUN wget https://www.sqlite.org/2023/sqlite-autoconf-3410100.tar.gz && \
    tar -xvzf sqlite-autoconf-3410100.tar.gz && \
    cd sqlite-autoconf-3410100 && \
    ./configure && make && make install && \
    cd .. && rm -rf sqlite-autoconf-3410100* && \
    ldconfig

ENV LD_LIBRARY_PATH="/usr/local/lib"
ENV PATH="/usr/local/bin:$PATH"

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
CMD ["sh", "-c", "uv run set_vector_store.py && uv run uvicorn main:app --host 0.0.0.0 --port 7860 --reload"]
