# Censorarr 1.6.4 — Source Installation

## Main application

1. Clone or extract the repository onto the Docker host.
2. Edit `docker-compose.yml`.
3. Change the host-side Movies and TV Shows paths to match your system.
4. Set `PUID`, `PGID`, `TZ`, and any optional integration credentials. On Synology, leave `CENSORARR_SYNOLOGY_COMPAT_MODE: "auto"` unless you specifically want to forbid or force root fallback.
5. Start Censorarr:

```bash
docker compose up -d --build
```

6. Open `http://YOUR-SERVER-IP:8087` (or the host port you selected).
7. Complete the guided Setup Wizard.
8. Start in **Dry Run** while validating your environment.

## GPU Worker

See [`gpu-worker/README.md`](gpu-worker/README.md). The GPU Worker can be installed on a completely separate NVIDIA-equipped server.
