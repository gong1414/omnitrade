# OmniTrade backend — Python 3.11 + uv
FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency manifests + README (hatchling reads project.readme)
COPY pyproject.toml README.md ./

# Install production dependencies
RUN uv pip install --system --no-cache .

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Make the package importable without re-running the install step when only
# src/ changes (layer-cache friendly).
ENV PYTHONPATH=/app/src

# Create data directory (volume mount will overlay this)
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "-m", "omnitrade.main"]
