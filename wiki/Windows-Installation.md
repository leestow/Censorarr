# Windows Installation

Censorarr can run natively on **Windows 11 x64**. Docker is not required for the Windows build.

## Download the installer

Go to the Censorarr **Releases** page and download:

```text
Censorarr-Setup-X.Y.Z.exe
```

The latest release is available at:

```text
https://github.com/leestow/Censorarr/releases/latest
```

The Windows installer is built automatically from the same Censorarr source as the Docker/Synology version and is smoke-tested by GitHub Actions before it is attached to the release.

## What gets installed

| Item | Location |
|---|---|
| Censorarr application | `C:\Program Files\Censorarr` |
| Configuration and state | `C:\ProgramData\Censorarr\config` |
| Work files | `C:\ProgramData\Censorarr\work` |
| Whisper model cache | `C:\ProgramData\Censorarr\config\models` |
| Windows launcher log | `C:\ProgramData\Censorarr\logs\windows-launcher.log` |
| Web interface | `http://127.0.0.1:8087` |

FFmpeg and FFprobe are bundled with the application.

## Install

1. Run `Censorarr-Setup-X.Y.Z.exe`.
2. Windows may ask for administrator approval because the application is installed under Program Files.
3. Choose whether you want a desktop shortcut.
4. Leave **Start Censorarr automatically when I sign in** enabled if you want Censorarr to run after Windows sign-in.
5. Finish Setup and leave **Open Censorarr** checked.

Censorarr opens in your browser at:

```text
http://127.0.0.1:8087
```

## First-run Setup Wizard

Complete the Setup Wizard just like Docker/Synology users, with one important difference: use real Windows paths instead of `/media` and `/tv`.

Examples:

```text
D:\Movies
E:\TV Shows
M:\Movies
\\NAS\Media\Movies
```

Use the **Browse...** button beside the Movies and TV folder fields. Native Windows browsing supports local drives, mapped drives, and reachable UNC network paths.

Start with:

- **Dry Run** enabled
- a small test folder or small media set
- local CPU transcription first, or configure the remote GPU Worker if desired
- optional Plex/Radarr/Sonarr/Bazarr integrations only after the core scan works

## Network shares

Censorarr normally runs as the signed-in Windows user, not as LocalSystem. This lets it use the same mapped drives and authenticated network shares that the user can access.

If a network path works in File Explorer but not in Censorarr:

1. Confirm Censorarr is running under the same Windows account.
2. Prefer a UNC path such as `\\SERVER\Share\Movies` if a mapped drive is unavailable after sign-in.
3. Confirm the Windows account has read/write permission if Apply mode will modify media.
4. Restart Censorarr after changing credentials or mappings.

## Local CPU and remote GPU

The Windows installer supports:

- **Local CPU** faster-whisper transcription.
- **Remote GPU** transcription through the optional Censorarr GPU Worker.
- **Auto** mode when configured to fall back to local CPU.

Local Whisper models are cached under:

```text
C:\ProgramData\Censorarr\config\models
```

## Updating Windows Censorarr

Download the newer installer from GitHub Releases and run it over the existing installation.

The application files under Program Files are replaced, while persistent Censorarr data under `C:\ProgramData\Censorarr` remains in place.

After updating, open the Dashboard and confirm the displayed Censorarr version and normal processing status.

## Uninstalling

Use **Settings -> Apps -> Installed apps** in Windows and uninstall Censorarr.

The installer removes the application. Persistent configuration/data under `C:\ProgramData\Censorarr` may be kept so it is not accidentally destroyed. If you want a completely clean removal, back up anything you need and remove that directory manually after uninstalling.
