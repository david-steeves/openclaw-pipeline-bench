# Shared Dockerfile for all 4 bench variants.
# The variant is selected at runtime via $BENCH_VARIANT_ID; the image is identical.

FROM python:3.13-slim-bookworm

WORKDIR /app

# Install harness deps.
RUN pip install --no-cache-dir psutil pyyaml

# Copy harness + manifest.
COPY bench/harness /app/harness
COPY manifest /app/manifest

# Volume mount points for substrate state (set per-variant in compose).
VOLUME ["/workspace", "/data"]

ENTRYPOINT ["python", "-m", "harness.runner"]
