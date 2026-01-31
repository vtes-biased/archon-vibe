# Backend Dockerfile

FROM python:3.13-slim
WORKDIR /app

# Install system dependencies for healthcheck, build tools, and Rust
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (for building the engine)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install uv for faster Python dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install maturin for building Python extension
RUN uv tool install maturin

# Copy and build the Rust engine
COPY engine/ ./engine/
RUN cd engine && /root/.local/bin/maturin build --release

# Copy Python dependency files
COPY pyproject.toml uv.lock ./
RUN test -f README.md || echo "# Archon" > README.md

# Install dependencies
RUN uv sync --frozen --no-dev

# Install the engine wheel (use find-links for single wheel)
RUN WHEEL=$(ls engine/target/wheels/*.whl | head -1) && uv pip install "$WHEEL"

# Copy backend source
COPY backend/ ./backend/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "backend.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
