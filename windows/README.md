# Censorarr native Windows installer

Censorarr can run directly on **Windows 11 x64** without Docker.

## Download

Download the latest installer from the project Releases page:

**https://github.com/leestow/Censorarr/releases/latest**

The installer is named:

```text
Censorarr-Setup-X.Y.Z.exe
```

## Installed locations

- Application: `C:\Program Files\Censorarr`
- Persistent configuration/data: `C:\ProgramData\Censorarr`
- Web UI: `http://127.0.0.1:8087`
- Local transcription: CPU via faster-whisper
- Optional remote transcription: Censorarr NVIDIA GPU Worker

The installer can create an optional per-user startup shortcut so Censorarr runs under the signed-in Windows account. This is intentional: it gives Censorarr the same access to local folders, mapped drives, and authenticated network shares as that user instead of running as LocalSystem.

## First run

1. Install Censorarr.
2. Leave **Start Censorarr** checked at the end of Setup.
3. Your browser opens to `http://127.0.0.1:8087`.
4. Complete the Setup Wizard.
5. Use **Browse...** to select Movies and TV folders. Local drives, mapped drives, and reachable UNC paths are supported.
6. Start in **Dry Run** and test a small media set before switching to Apply mode.

## What the installer contains

GitHub Actions builds the installer using PyInstaller and Inno Setup. It bundles the Python runtime, Censorarr, required Python dependencies, FFmpeg/FFprobe, and the Microsoft Visual C++ runtime bootstrapper.

The native launcher maps Censorarr's logical Linux/container paths (`/config`, `/work`, `/app`) to Windows locations at runtime. Docker/Synology behavior is unchanged.

## Updating

Install a newer `Censorarr-Setup-X.Y.Z.exe` over the existing installation. Persistent configuration and state under `C:\ProgramData\Censorarr` are retained.
