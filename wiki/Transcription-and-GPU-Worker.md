# Transcription & GPU Worker

Censorarr supports local CPU transcription or an optional remote NVIDIA GPU Worker.

## Local CPU

Default-style configuration:

```yaml
whisper:
  backend: local
  model: small
  device: cpu
  compute_type: int8
  language: en
```

This is the simplest backend for a first-run test.

## Remote GPU Worker

The worker receives extracted audio from the main Censorarr instance, runs Faster-Whisper on an NVIDIA GPU, and returns word timestamps. Detection, review logic, and final media remuxing remain on the main Censorarr server.

You can run the worker three ways:

- **Native Windows 11 x64 installer**
- **Native Debian/Ubuntu x86_64 `.deb`**
- **Docker** using the existing `gpu-worker/` compose project

All three use the same API and `X-Censorarr-Token` protocol.

## Native Windows GPU Worker

Download from GitHub Releases:

```text
Censorarr-GPU-Worker-Setup-X.Y.Z.exe
```

The installer automatically:

1. installs the worker
2. generates a strong worker token
3. downloads the pinned NVIDIA CUDA 12 / cuBLAS / cuDNN runtime files
4. verifies their SHA-256 hashes
5. stores the NVIDIA runtime privately under Censorarr GPU Worker data
6. creates an automatic startup task
7. starts the API on TCP `9000`

The NVIDIA display/compute driver is the one prerequisite that is **not** installed automatically.

Configuration is stored at:

```text
C:\ProgramData\CensorarrGPUWorker\worker.env
```

The installer opens this file at the end so you can copy `ASR_WORKER_TOKEN`.

If the NVIDIA driver is installed later, run:

```powershell
& "C:\Program Files\Censorarr GPU Worker\CensorarrGPUWorker.exe" --install-runtime
& "C:\Program Files\Censorarr GPU Worker\CensorarrGPUWorker.exe" --start-service
```

## Native Debian / Ubuntu GPU Worker

Download:

```text
Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb
```

Install:

```bash
sudo apt install ./Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb
```

Locations:

| Item | Location |
|---|---|
| Application | `/opt/censorarr-gpu-worker` |
| Configuration/token | `/etc/censorarr-gpu-worker.env` |
| Models | `/var/lib/censorarr-gpu-worker/models` |
| Private NVIDIA runtime | `/var/lib/censorarr-gpu-worker/runtime` |
| Service | `censorarr-gpu-worker.service` |
| API | `http://HOST:9000` |

Show the token:

```bash
sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --show-token
```

Service commands:

```bash
sudo systemctl restart censorarr-gpu-worker
systemctl status censorarr-gpu-worker
journalctl -u censorarr-gpu-worker -f
```

If the driver is installed after the package:

```bash
sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --install-runtime
sudo systemctl restart censorarr-gpu-worker
```

## What the native installer downloads

The native installer does **not** install the full CUDA development toolkit and does not modify an existing global CUDA setup.

At build time Censorarr creates a platform-specific manifest containing exact NVIDIA package versions, file URLs, sizes, and SHA-256 hashes. During installation it downloads those exact NVIDIA-maintained PyPI wheels and verifies the hashes before extracting the runtime libraries locally.

The pinned root runtime components are:

- CUDA 12 runtime
- cuBLAS for CUDA 12
- cuDNN 9 for CUDA 12

Any NVIDIA package dependencies are resolved into the manifest at build time as well.

A working NVIDIA driver is still required.

## Docker GPU Worker

Docker remains supported:

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr/gpu-worker
```

Set a long random token in `docker-compose.yml`:

```yaml
ASR_WORKER_TOKEN: "CHANGE_ME_TO_THE_SAME_LONG_RANDOM_TOKEN_AS_MAIN_CENSORARR"
```

Then:

```bash
docker compose up -d --build
```

## Test the worker

From the worker host:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://127.0.0.1:9000/health
```

From the main Censorarr host:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://GPU-WORKER-IP:9000/health
```

A healthy worker should report one or more CUDA devices.

## Configure the main Censorarr instance

In **Settings → Setup Wizard** or Transcription settings:

```text
URL:   http://GPU-WORKER-IP:9000
Token: exactly the same ASR_WORKER_TOKEN used by the worker
```

Backend choices:

- `remote` — GPU worker only
- `auto` — GPU worker with local CPU fallback

## Default GPU settings

```text
Model:          small.en
Compute type:   int8_float32
Chunk size:     600 seconds
Chunk overlap:  2 seconds
```

These defaults remain suitable for GTX 10-series / Pascal cards. Long WAV files are processed in bounded chunks to avoid large host-RAM spikes.

## Troubleshooting

### `Invalid worker token`

The main Censorarr token and worker `ASR_WORKER_TOKEN` must match exactly. Current Censorarr uses:

```text
X-Censorarr-Token
```

### No CUDA device visible

Check:

```bash
nvidia-smi
```

For native installs, also verify the private runtime was installed:

Windows:

```powershell
& "C:\Program Files\Censorarr GPU Worker\CensorarrGPUWorker.exe" --runtime-plan
```

Linux:

```bash
sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --runtime-plan
```

Then rerun `--install-runtime` if needed.

### Cannot connect to port 9000

Verify:

- worker process/service is running
- TCP `9000` is allowed through the host firewall
- the IP/hostname is correct
- Censorarr can route to the worker host
