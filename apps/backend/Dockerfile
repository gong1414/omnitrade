# OmniTrade backend — Python 3.11 + uv
FROM python:3.11-slim@sha256:6d85378d88a19cd4d76079817532d62232be95757cb45945a99fec8e8084b9c2

WORKDIR /app

# Install uv for fast dependency resolution. Pinned for reproducibility;
# Dependabot's pip ecosystem will bump this when a new uv lands.
RUN pip install --no-cache-dir uv==0.11.7

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
