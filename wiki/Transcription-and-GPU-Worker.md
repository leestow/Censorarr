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

The worker is a separate Docker project under:

```text
gpu-worker/
```

The main Censorarr host sends extracted 16 kHz audio to the worker. The worker runs Faster-Whisper and returns word timestamps. Detection, review logic, and final remuxing remain on the main Censorarr server.

### GPU worker requirements

- Linux host/VM/LXC with Docker
- NVIDIA GPU
- working NVIDIA driver
- NVIDIA Container Toolkit
- network reachability from Censorarr to worker TCP `9000`

## Install the worker

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr/gpu-worker
```

Edit:

```yaml
ASR_WORKER_TOKEN: "CHANGE_ME_TO_THE_SAME_LONG_RANDOM_TOKEN_AS_MAIN_CENSORARR"
```

Use a long random token.

Start:

```bash
docker compose up -d --build
```

Check:

```bash
docker compose ps
docker compose logs --tail=50
```

## Test the worker locally

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://127.0.0.1:9000/health
```

A healthy worker returns JSON and reports CUDA availability.

## Configure the main Censorarr instance

In the UI, configure the remote GPU worker with:

```text
URL:   http://GPU-WORKER-IP:9000
Token: exactly the same token used by the worker
```

Backend choices:

- `remote` — remote worker only
- `auto` — remote worker with local CPU fallback

## Token protocol

Current Censorarr uses:

```text
X-Censorarr-Token
```

An old pre-rename worker that still expects the legacy header will return:

```text
Invalid worker token
```

even when the literal token value is correct.

If upgrading an older worker, make sure its `worker.py` is from the current Censorarr release.

## Default GPU settings

The shipped worker defaults are tuned for GTX 10-series / Pascal compatibility:

```text
Model:          small.en
Compute type:   int8_float32
Chunk size:     600 seconds
Chunk overlap:  2 seconds
```

Long WAVs are processed in bounded chunks to avoid large host-RAM spikes.

## Network troubleshooting

From the main Censorarr host:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://GPU-WORKER-IP:9000/health
```

If this cannot connect:

- verify worker container is running
- verify port `9000:9000`
- verify firewall/routing
- verify correct IP
- verify token

## No CUDA device visible

If the worker says no CUDA device is visible, verify NVIDIA Container Toolkit and Docker GPU passthrough before troubleshooting Censorarr itself.
