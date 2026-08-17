# Changelog

## 1.6.4

- Added Synology DSM ACL compatibility mode (`CENSORARR_SYNOLOGY_COMPAT_MODE=auto|true|false`).
- `auto` keeps the configured PUID/PGID when possible and falls back to container root only when DSM ACLs block the media mount for that identity but root can read it.
- Added media-root preflight before Whisper/model loading. Permission problems now keep the worker alive in a clear `permissions-error` state instead of causing a restart loop.
- The first-run Setup Wizard now checks media access before setup can complete.
- Dashboard status now identifies media permission failures.
- ffprobe/read failures on an individual media file are recorded as a file error and no longer terminate the whole worker.
- Main app and GPU worker now both report version `1.6.4`.

## 1.6.3

- Completed Censorarr naming cleanup across main app, Docker examples, documentation, marker/log/temp defaults, and GPU-worker protocol names.
- Renamed the main engine module to `censorarr.py`.
- Renamed Docker service/container examples to `censorarr` and `censorarr-gpu-worker`.
- Main app and GPU worker now both report version `1.6.3`.
- Added a standalone GPU-worker README and install flow.
- Retains the v1.6.x Setup Wizard, optional integrations, Media fallback catalogs, dashboard count fixes, UI branding updates, and bounded GPU audio chunking.

### Packaging correction (2026-08-16)
- Preserve empty `config/` and `work/` directories in Git/GitHub with `.gitkeep` files.
- Use relative project-local bind mounts (`./app`, `./config`, `./work`, etc.) so Synology Container Manager projects can be created in any folder without editing internal Censorarr paths.
- No application code/version change; remains Censorarr 1.6.3.
