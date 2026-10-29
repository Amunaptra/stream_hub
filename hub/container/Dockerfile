FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAM_HUB_DATABASE=/data/hub.sqlite3 \
    STREAM_HUB_UI_DIR=/opt/stream-hub/ui \
    STREAM_HUB_PORT=8788 \
    STREAM_HUB_MDNS=0

WORKDIR /opt/stream-hub

RUN apt-get update && \
    apt-get install -y --no-install-recommends avahi-utils && \
    rm -rf /var/lib/apt/lists/*

COPY hub/backend /opt/stream-hub/backend
RUN python -m pip install --upgrade pip && \
    python -m pip install /opt/stream-hub/backend

COPY hub/ui /opt/stream-hub/ui
COPY hub/installer/backup_sqlite.py /opt/stream-hub/backup_sqlite.py

USER 568:568
EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/healthz', timeout=3).read()"]

CMD ["stream-hub"]
