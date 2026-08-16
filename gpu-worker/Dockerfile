FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models XDG_CACHE_HOME=/models
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates tini && rm -rf /var/lib/apt/lists/*
WORKDIR /worker
COPY requirements.txt /worker/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /worker/requirements.txt
COPY app/ /worker/
EXPOSE 9000
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python3","-m","uvicorn","worker:app","--host","0.0.0.0","--port","9000","--workers","1"]
