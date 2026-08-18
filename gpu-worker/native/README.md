# Native Censorarr GPU Worker packaging

This directory contains the cross-platform native GPU Worker launcher and packaging files.

- `gpu_worker_launcher.py` — native launcher, token/config bootstrap, local NVIDIA runtime activation, Windows startup task support.
- `runtime_manifest.py` — build-time resolver for pinned NVIDIA PyPI wheel URLs and SHA-256 hashes.
- `windows/` — Inno Setup installer.
- `linux/` — Debian package service and maintainer scripts.

The native installers do not install or replace the NVIDIA display driver. They download the CUDA 12 runtime libraries required by Faster-Whisper/CTranslate2 into the worker's own data directory.

Docker packaging under `gpu-worker/` is unchanged.
