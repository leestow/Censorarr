# HLS blur-injection proof of concept

Experimental only. Does not alter existing movie files or Censorarr playback.

## Purpose
Validate seamless switching between unmodified and blurred portions using a static HLS VOD playlist. This first prototype **does not** integrate with Plex or run NudeNet. It creates HLS segments for the entire test input (temporary additional storage), to establish a baseline before attempting sparse segment reuse.

## Requirements
FFmpeg with libx264, Python 3, a local HTTP server, a short test movie you have rights to process.

## Run
```bash
python3 experiments/hls_blur_poc.py /path/to/test.mp4 --start 20 --end 28 --out /tmp/censorarr-hls-test
cd /tmp/censorarr-hls-test && python3 -m http.server 8099
```
Open http://SERVER:8099/movie.m3u8 in an HLS-compatible player (e.g. VLC). Do not expect Plex to index this playlist as a movie.

## Evaluation
- Watch and seek across both transitions.
- Confirm no audio gap and consistent duration.
- Check segment count and total size.
- Verify that only the requested rectangle is blurred during the interval.
- Compare start-up time to original.
- Test Plex compatibility separately; no claims of Direct Play integration.

## Limitations
This baseline re-encodes the entire test clip to create aligned segments. A later sparse-cache architecture must solve compressed GOP boundaries, source container compatibility, time bases, and seeking. A playlist cannot byte-range arbitrary MKV data into playable TS segments. Preserve the original movie, and do not expose unblurred content as a fallback in a future censorship-enabled playback path.
