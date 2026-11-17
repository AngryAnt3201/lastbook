# The library server version (server.py) in a container, for a home server or NAS.
# Build from the top of the repository:  docker build -f packaging/docker/Dockerfile -t lastbook .
# See packaging/docker/README.md.
FROM python:3.12-slim-bookworm

# poppler-utils: pdftotext, which engine/library.py uses for PDF text. curl: the health check, and /api/setup/*
# from `docker exec` (setup answers this computer only). socat: the loopback model forwarder in entrypoint.sh.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils curl socat ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# The same wheels as the Linux package: keyword search, no onnxruntime.
COPY packaging/linux/requirements_linux.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

WORKDIR /opt/lastbook
COPY . /opt/lastbook/
RUN rm -rf .git website website-next derived/app-build derived/release

# /data holds LastbookData/ and setup's work folder LastbookData.setup/ beside it. Switching to a new library is one
# rename between the two, so mount /data, not LastbookData itself.
ENV LASTBOOK_DATA=/data/LastbookData \
    XDG_CONFIG_HOME=/data/config \
    HOME=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8890
HEALTHCHECK --interval=60s --timeout=10s --start-period=24h CMD curl -sf -o /dev/null http://127.0.0.1:8890/api/health || exit 1
ENTRYPOINT ["/opt/lastbook/packaging/docker/entrypoint.sh"]
