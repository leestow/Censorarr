# Censorarr GPU Worker 1.6.5

The Censorarr GPU Worker is an optional standalone transcription service for Censorarr. It accepts extracted 16 kHz audio from the main Censorarr server, runs Faster-Whisper on an NVIDIA GPU, and returns word timestamps. The main Censorarr server still performs detection, review logic, and final media remuxing.

## Requirements

- Linux host or VM/LXC capable of running Docker
- NVIDIA GPU with a working NVIDIA driver
- NVIDIA Container Toolkit configured for Docker
- Network access from the main Censorarr server to TCP port `9000` on the worker

The shipped defaults are tuned for Pascal/GTX 10-series compatibility:

- Model: `small.en`
- Compute type: `int8_float32`
- Audio chunk size: 600 seconds
- Overlap: 2 seconds

Long files are transcribed in bounded chunks to avoid large host-RAM spikes.

## Install only the GPU Worker

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr/gpu-worker
```

Edit `docker-compose.yml` and set a long random `ASR_WORKER_TOKEN`.

Then build and start it:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs --tail=50
```

Test the API locally:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://127.0.0.1:9000/health
```

Then open the main Censorarr web UI and use **Settings → Setup Wizard** or the transcription settings to enter the worker URL and the same token.

## Updating

Pull or replace the worker source, then rebuild/recreate the project:

```bash
docker compose down
docker compose up -d --build
```

Downloaded models live under `./models` and do not need to be committed to GitHub.
