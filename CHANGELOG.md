# Changelog

## 1.6.6

- Fixed processed media retaining restrictive source permissions such as `0700`/`0600`, which could make a movie disappear from Plex after Censorarr replaced the original file.
- Added `safety.ensure_readable_output` (default `true`). Censorarr now preserves existing owner/group and broader mode bits while guaranteeing read access for owner, group, and other on processed replacements.
- Permission-setting failures are now logged instead of being silently ignored.
- Main app runtime now reports version `1.6.6`.

## 1.6.5

- Synology `auto` compatibility mode now scans nested Movies/TV folders (to depth 4) instead of checking only `/media` and `/tv`, so mixed DSM ACLs are detected before privileges are dropped.
- `auto` also checks for media files that are individually unreadable by the requested PUID/PGID and falls back to container root when root can access the same tree.
- Permission-denied media failures remain visible as normal failures, but now carry retryable permission metadata instead of being treated as deterministic ffprobe failures.
- A permission failure retries automatically when the runtime identity changes or when the file later becomes readable, without repeatedly invoking ffprobe while access is still blocked.
- Main app and GPU worker now report version `1.6.5`.

### Native installer packaging (2026-08-17)

- Added a native Windows 11 x64 installer built and smoke-tested by GitHub Actions.
- Added a native Debian/Ubuntu-family x86_64 `.deb` package built and smoke-tested on Ubuntu 22.04.
- Native Linux installs Censorarr under `/opt/censorarr`, keeps persistent data under `/var/lib/censorarr`, and runs through a dedicated `censorarr` system user and `systemd` service.
- Native Linux binds to localhost by default; LAN binding and web authentication are configured in `/etc/default/censorarr`.
- Windows and Linux native installer assets are published to the matching version on GitHub Releases without overwriting an already-published versioned asset.

### Cross-platform folder picker hotfix (2026-08-16)

- Added **Browse…** buttons for the Movies and TV folder fields in both the Setup Wizard and normal Settings.
- Docker/Synology browsing is constrained to configured/mounted media roots rather than exposing the container filesystem.
- Native Windows browsing lists available drives and supports local drives, mapped drives, and manually entered UNC network paths.
- Manual media browsing/processing now uses the configured media roots as its security boundary, allowing native Windows library paths to work instead of assuming `/media` and `/tv`.
- Settings saves keep Plex, Radarr, Sonarr, and Bazarr mapping destinations synchronized with the selected local Movies/TV roots, including Windows paths.

### Log viewer compatibility hotfix (2026-08-16)

- The container entrypoint now keeps `/config/censorarr.log` as a dashboard compatibility alias to the active `logging.file` target from `config.yaml`.
- Existing upgrades that still use `/config/plexclean.log` now show the correct live Censorarr log without requiring the user to rewrite the persistent configuration first.
- Custom log paths are also supported at container startup, and Tail / Live Stream / Download / Clear continue to operate through the dashboard alias.
- If a non-empty standalone `/config/censorarr.log` already exists while another log target is configured, it is preserved as `/config/censorarr.log.before-alias` before the alias is created.

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
