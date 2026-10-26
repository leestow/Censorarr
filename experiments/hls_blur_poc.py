#!/usr/bin/env python3
"""Standalone HLS blur experiment; does not modify Censorarr or the source movie."""
import argparse
import pathlib
import subprocess

def main():
    p = argparse.ArgumentParser()
    p.add_argument("movie")
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--out", default="./hls-blur-test")
    p.add_argument("--x", type=int, default=100)
    p.add_argument("--y", type=int, default=100)
    p.add_argument("--width", type=int, default=180)
    p.add_argument("--height", type=int, default=180)
    args = p.parse_args()
    if args.start < 0 or args.end <= args.start:
        p.error("Require 0 <= start < end")
    if min(args.x, args.y) < 0 or min(args.width, args.height) <= 0:
        p.error("Invalid blur rectangle")
    output = pathlib.Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # The source video is split into two filter branches. Only the specified
    # region is blurred, and the overlay is enabled during the chosen interval.
    filt = (
        "[0:v]split=2[base][region];"
        f"[region]crop={args.width}:{args.height}:{args.x}:{args.y},"
        "boxblur=20:2[blur];"
        f"[base][blur]overlay={args.x}:{args.y}:"
        f"enable='between(t,{args.start},{args.end})'[v]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(pathlib.Path(args.movie).resolve()),
        "-filter_complex", filt, "-map", "[v]", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-force_key_frames", "expr:gte(t,n_forced*2)",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(output / "segment_%05d.ts"),
        str(output / "movie.m3u8")
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("Playlist:", output / "movie.m3u8")
    print("NOTE: Test-only stereo AAC; surround preservation is a later milestone.")

if __name__ == "__main__":
    main()
