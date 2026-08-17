# Censorarr 1.6.4 — Source Installation

## Main application

1. Clone or extract the repository onto the Docker host.
2. Edit `docker-compose.yml`.
3. Change the host-side Movies and TV Shows paths to match your system.
4. Set `PUID`, `PGID`, `TZ`, and any optional integration credentials.
5. Start Censorarr:

```bash
docker compose up -d --build
```

6. Open `http://YOUR-SERVER-IP:8087` (or the host port you selected).
7. Complete the guided Setup Wizard.
8. Start in **Dry Run** while validating your environment.

## GPU Worker

See [`gpu-worker/README.md`](gpu-worker/README.md). The GPU Worker can be installed on a completely separate NVIDIA-equipped server.


Synology permission compatibility (v1.6.4):
- CENSORARR_SYNOLOGY_COMPAT_MODE=auto is recommended for DSM Container Manager.
- auto uses PUID/PGID normally and falls back to container root only if DSM ACLs block that identity from a media mount while root can access it.
- false forbids root fallback; true always uses container root.
- Censorarr checks media access before loading Whisper and waits with a clear permission error instead of crash-looping.
