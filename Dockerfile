# Home Lab Monitor — Ubuntu 24.04 image for mcp-01 (and any Docker host).
# Python comes from this image; do not use a Windows .venv inside the container.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY run.py .
COPY monitor/ ./monitor/
COPY static/ ./static/
COPY public/ ./public/

# Live config is mounted at runtime (never baked into the image).
RUN mkdir -p /app/private

EXPOSE 8000

CMD ["python", "run.py"]
