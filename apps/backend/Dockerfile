# OmniTrade backend — Python 3.11 + uv
FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency manifests first (layer cache)
COPY pyproject.toml ./

# Install production dependencies
RUN uv pip install --system --no-cache .

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create data directory (volume mount will overlay this)
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "-m", "omnitrade.main"]
