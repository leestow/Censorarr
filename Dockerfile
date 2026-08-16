FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/config/models \
    XDG_CACHE_HOME=/config/models

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/
COPY en.json /app/en.json
COPY config.example.yaml /app/config.example.yaml
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /config /work

EXPOSE 8787
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "webapp:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1", "--log-level", "info"]
