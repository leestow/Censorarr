# Experimental Plex fast-start (Shield first)

This branch continues the proven `family-safe-media` Plex gateway/shim prototype.
It is **not** part of the Censorarr 1.7.0 production release.

## What's changed

- **Fast report lookup:** Plex Transcoder no longer opens unrelated Censorarr
  report JSON files when finding a movie's profanity timestamps. It matches
  Censorarr's sanitized report filename prefix and parses only candidates.
  If two different reports share the same movie basename and the exact path
  doesn't match, filtering skips the ambiguous match instead of applying a
  potentially incorrect mute schedule.
- **Nonblocking Plex decision:** the gateway fetches media metadata in a
  short-lived worker instead of making the playback decision itself wait for a
  Plex metadata HTTP round-trip (previously an 8-second timeout). A first media
  request waits at most 600 ms for that lookup, then follows the existing
  unfiltered fallback if eligibility is not yet established.
- **HLS timestamps:** the gateway logs the first segment request and when its
  proxy transfer completes, including approximate time since the initial
  playback decision on the same client IP. Neither event is identical to the
  client's first displayed frame.

## Safety / current limitations

- **Experimental, opt-in.** Do not install the Plex Transcoder shim or
  iptables redirect against a live Plex deployment without a backup, console
  access, and a rollback plan. The existing installer replaces the Plex
  Transcoder executable with a wrapper and the startup script redirects
  only the explicitly specified client IP.
- The stable start script still uses the legacy `--force-all` policy for
  decisions from the redirected client; that policy is not yet scoped solely
  to movies in the allowlist. Unrelated Plex playback on that device may
  also be affected. This needs testing before enabling the Roku or other
  devices.
- **Filtering may fail open** if metadata lookup exceeds its 600 ms first-file
  wait, reports are missing, or multiple same-named reports are ambiguous.
  Do not depend on this branch for guaranteed censorship.
- Plex updates may overwrite or change the transcoder executable or flags.
  NVIDIA Shield native Plex HLS was previously tested. **Roku is not validated.**
  Surround channel layouts, subtitles, seeks, and Direct Play fallback need
  end-to-end confirmation on actual devices.
- The feature branch is descended from the older family-safe-media prototype,
  **not current Censorarr main**. Do not overwrite your existing Windows
  1.7.0 installation or Synology production app with this branch.
- No permanent media files are modified by these gateway/shim optimizations.

## Benchmarks to collect during an opted-in Shield test

Test the same allowlisted movie three times: cold playback, repeat playback,
and a seek to a censored interval. Separately test a non-allowlisted movie.
Compare against the existing gateway to avoid crediting the fast-start changes
for general Plex caching.

Gateway log: `work/plex-stream-gateway.log`

- `DECISION_CACHE ... lookup_ms=<value>` measures metadata resolution in the
  background, *not* time that Plex's decision was blocked.
- `DIRECTPLAY_REJECT` shows Plex's Direct Play fallback was intercepted.
- `HLS_FIRST_SEGMENT_REQUEST ... since_decision_ms=<value>` measures elapsed
  server-side time between decision receipt and the first segment request from
  that IP. This may be -1 if no matching recent decision was observed.
- `HLS_FIRST_SEGMENT_FINISHED ... proxy_transfer_ms=<value>` measures proxy
  transfer completion for that segment; it is *not* the TV's first frame.

Transcoder log: `work/plex-transcoder-shim.log`

- Check for `FILTERED`, `timeline=absolute-copyts`, and the expected mute
  count. If the shim logs `no-report`, `unsupported-audio-graph`, or
  `not-allowlisted`, audio is *not* guaranteed clean.
- Confirm Plex playback information reports video as Copy/Direct Stream
  while audio transcodes. Confirm the mute range audibly, preserve surround
  channels, and verify seeking.

Aim for consistent 2–5-second perceived startup, but this is a **target**,
not an achieved or measured result on the latest code. The currently available
CI tests cannot reproduce Plex device negotiation.

## Regression checks

GitHub Actions runs the standard-library tests in
`tests/test_plex_fast_start.py`. Tests cover a 1,000-report directory,
ambiguous filenames, metadata backgrounding, and the first-file wait bound.

## Reverting

Do not replace a Plex binary by hand. The historical installation includes
`tools/uninstall_synology_plex_stream_filter.sh` and
`tools/stop_synology_plex_stream_filter.sh` to restore Plex's real
transcoder and remove redirected client traffic. Verify paths, ownership,
and installed runtime configuration before invoking either script.
