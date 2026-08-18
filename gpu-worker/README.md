# Censorarr GPU Worker 1.6.5

The Censorarr GPU Worker is an optional standalone transcription service for Censorarr. It accepts extracted audio from the main Censorarr server, runs Faster-Whisper on an NVIDIA GPU, and returns word timestamps. Detection, review logic, and final media remuxing remain on the main Censorarr server.

## Installation choices

| Platform | Recommended install |
|---|---|
| Windows 11 x64 | `Censorarr-GPU-Worker-Setup-X.Y.Z.exe` from GitHub Releases |
| Debian/Ubuntu x86_64 | `Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb` from GitHub Releases |
| Docker / LXC / server | Existing `docker-compose.yml` project |

The native installers are intentionally smaller than a full CUDA bundle. They download the pinned NVIDIA CUDA 12 runtime libraries needed by the worker during installation, verify each wheel with SHA-256, and keep those libraries local to the Censorarr GPU Worker. They do **not** replace or modify a machine-wide CUDA Toolkit installation.

A working NVIDIA driver is still required.

## Native Windows GPU Worker

Download the latest release asset:

```text
Censorarr-GPU-Worker-Setup-X.Y.Z.exe
```

Setup:

1. Installs the worker under `C:\Program Files\Censorarr GPU Worker`.
2. Creates persistent data under `C:\ProgramData\CensorarrGPUWorker`.
3. Generates a strong `ASR_WORKER_TOKEN`.
4. Downloads the pinned CUDA 12 / cuBLAS / cuDNN runtime packages from NVIDIA-maintained packages on PyPI.
5. Verifies SHA-256 before extraction.
6. Creates an automatic Windows startup task.
7. Starts the worker on TCP port `9000`.

The installer opens the generated configuration file at the end so the token can be copied into the main Censorarr instance.

If the NVIDIA driver is not installed yet, install/update the driver first and then run:

```powershell
& "C:\Program Files\Censorarr GPU Worker\CensorarrGPUWorker.exe" --install-runtime
& "C:\Program Files\Censorarr GPU Worker\CensorarrGPUWorker.exe" --start-service
```

## Native Debian / Ubuntu GPU Worker

Install the release package:

```bash
sudo apt install ./Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb
```

The package:

- installs the app under `/opt/censorarr-gpu-worker`
- stores models/runtime data under `/var/lib/censorarr-gpu-worker`
- stores configuration and the token in `/etc/censorarr-gpu-worker.env`
- creates a dedicated `censorarr-gpu-worker` system user
- creates and enables `censorarr-gpu-worker.service`
- downloads and verifies the pinned NVIDIA runtime when a working driver is already present

Show the generated token:

```bash
sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --show-token
```

If the driver is installed later:

```bash
sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --install-runtime
sudo systemctl restart censorarr-gpu-worker
```

Check status:

```bash
systemctl status censorarr-gpu-worker
journalctl -u censorarr-gpu-worker -f
```

## Native NVIDIA runtime behavior

The current native builds use CTranslate2 4.8.1 / Faster-Whisper 1.2.1 and a build-generated runtime manifest. The manifest pins exact NVIDIA wheel URLs and SHA-256 hashes for the platform.

The installer resolves the NVIDIA dependency closure at build time, including the CUDA runtime components required by cuBLAS/cuDNN. At install time it downloads only those exact files from `files.pythonhosted.org`, verifies each hash, and extracts them into the worker's private runtime directory.

This keeps the native worker isolated from other CUDA applications on the machine.

## Docker GPU Worker

Docker remains fully supported and continues to use the NVIDIA CUDA runtime image.

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr/gpu-worker
```

Edit `docker-compose.yml` and set a long random `ASR_WORKER_TOKEN`, then:

```bash
docker compose up -d --build
```

## Configure main Censorarr

Use the worker host/IP and the same token:

```text
URL:   http://GPU-WORKER-IP:9000
Token: the ASR_WORKER_TOKEN generated/configured on the worker
```

Test locally on the worker:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://127.0.0.1:9000/health
```

A healthy GPU worker reports at least one CUDA device.

## Defaults

The shipped defaults remain tuned for GTX 10-series / Pascal compatibility:

```text
Model:          small.en
Compute type:   int8_float32
Chunk size:     600 seconds
Chunk overlap:  2 seconds
Port:           9000
```

Long files are processed in bounded chunks to avoid large host-RAM spikes.
