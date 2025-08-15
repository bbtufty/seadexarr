# Multi-stage build for smaller, more secure images
FROM python:3.12-slim as builder

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies using uv
RUN uv pip install --system --no-cache-dir -e .

# Production stage
FROM python:3.12-slim

# Create non-root user for security
RUN groupadd -r seadexarr && useradd -r -g seadexarr seadexarr

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . /app

# Install the package in production mode
RUN pip install --no-deps -e .

# Create config directory and set permissions
RUN mkdir -p /config && chown -R seadexarr:seadexarr /config /app

# Environment variables for containerized deployment
ENV CONFIG_DIR=/config
ENV DOCKER_ENV=true
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check using the new CLI status command
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD seadexarr status || exit 1

# Switch to non-root user
USER seadexarr

# Expose any necessary ports (if web interface is added later)
# EXPOSE 8080

# Use the new CLI as entry point
ENTRYPOINT ["seadexarr"]

# Default command shows help
CMD ["--help"]
