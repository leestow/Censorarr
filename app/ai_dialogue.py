"""AI dialogue isolation/remix for Censorarr.

The heavy separator runs on the optional Censorarr GPU worker. Censorarr sends only
one selected audio track as compressed stereo FLAC, receives an isolated dialogue
stem, then uses that stem both as the enhanced speech layer and as a sidechain key
that smoothly ducks the original movie mix while dialogue is active.
"""
from __future__ import annotations

import http.client
import os
import tempfile
import threading
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Callable

import remote_asr


class AIDialogueError(RuntimeError):
    pass


AI_MODELS = {"mdx_q", "htdemucs"}
DEFAULT_MODEL = "mdx_q"
DEFAULT_SEGMENT_SECONDS = 4


def _dialogue_cfg(cfg: dict) -> dict:
    return cfg.get("dialogue_enhancement", {}) or {}


def _remote_cfg(cfg: dict) -> dict:
    return (cfg.get("whisper", {}) or {}).get("remote", {}) or {}


def _worker_base(cfg: dict) -> str:
    return str(_remote_cfg(cfg).get("url") or "").strip().rstrip("/")


def _worker_token(cfg: dict) -> str:
    try:
        return remote_asr._token(cfg)  # Same worker/token as remote Whisper.
    except Exception:
        return str(_remote_cfg(cfg).get("token") or "")


def worker_capabilities(cfg: dict, timeout: float = 5.0) -> dict:
    base = _worker_base(cfg)
    if not base:
        return {"ok": False, "dialogue_ai": False, "reason": "remote-worker-not-configured"}
    try:
        data = remote_asr.health(cfg, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "dialogue_ai": False, "reason": str(exc)}
    features = data.get("features") if isinstance(data, dict) else {}
    supported = bool(isinstance(features, dict) and features.get("dialogue_ai"))
    return {**(data if isinstance(data, dict) else {}), "dialogue_ai": supported}


def _extract_source_flac(pc, src: Path, audio_rel: int, dest: Path, progress_callback=None) -> None:
    probe = pc.ffprobe(src)
    duration = pc.duration_of(probe)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-i", str(src), "-map", f"0:a:{audio_rel}", "-vn",
        "-ac", "2", "-ar", "44100", "-c:a", "flac", "-compression_level", "5", str(dest),
    ]
    if progress_callback:
        pc.run_ffmpeg_progress(cmd, duration, lambda pct: progress_callback(min(15.0, pct * 0.15)))
    else:
        pc.run(cmd)


def _remote_isolate(
    source_flac: Path,
    dest_flac: Path,
    cfg: dict,
    progress_callback: Callable[[float], None] | None = None,
) -> dict:
    base = _worker_base(cfg)
    if not base:
        raise AIDialogueError("AI Dialogue Isolation needs a configured GPU worker URL")

    dcfg = _dialogue_cfg(cfg)
    model = str(dcfg.get("ai_model") or DEFAULT_MODEL).strip().lower()
    if model not in AI_MODELS:
        model = DEFAULT_MODEL
    segment = max(2, min(8, int(dcfg.get("ai_segment_seconds", DEFAULT_SEGMENT_SECONDS) or DEFAULT_SEGMENT_SECONDS)))
    allow_cpu = bool(dcfg.get("ai_worker_cpu_fallback", True))
    timeout = max(300.0, float(dcfg.get("ai_timeout_seconds", 7200) or 7200))
    job_id = uuid.uuid4().hex

    try:
        conn, parsed = remote_asr._connection(base, timeout)
    except Exception as exc:
        raise AIDialogueError(str(exc)) from exc

    prefix = parsed.path.rstrip("/") if parsed.path else ""
    params = urllib.parse.urlencode({
        "job_id": job_id,
        "model": model,
        "segment": str(segment),
        "allow_cpu_fallback": "1" if allow_cpu else "0",
    })
    endpoint = prefix + "/dialogue/isolate?" + params
    size = source_flac.stat().st_size
    headers = {
        "Content-Type": "audio/flac",
        "Content-Length": str(size),
        "Accept": "audio/flac",
        "X-Censorarr-Client": "Censorarr",
        "X-Censorarr-Job-ID": job_id,
    }
    token = _worker_token(cfg)
    if token:
        headers["X-Censorarr-Token"] = token

    stop = threading.Event()
    poller: threading.Thread | None = None
    started = time.time()
    try:
        remote_asr._write_active({
            "job_id": job_id,
            "kind": "dialogue-ai",
            "started": started,
            "model": model,
            "audio": str(source_flac),
            "worker_url": base,
        })
    except Exception:
        pass

    def poll() -> None:
        while not stop.wait(1.0):
            try:
                payload = remote_asr.status(cfg, timeout=2.5)
                cur = payload.get("current_job") if isinstance(payload, dict) else None
                if not isinstance(cur, dict) or str(cur.get("job_id") or "") != job_id:
                    continue
                raw = cur.get("progress")
                if raw is not None:
                    try:
                        # Reserve 15% for extraction and 20% for final remix/remux.
                        pct = 15.0 + max(0.0, min(100.0, float(raw))) * 0.65
                    except (TypeError, ValueError):
                        pct = 45.0
                else:
                    stage = str(cur.get("stage") or "")
                    pct = 20.0 if "load" in stage else 45.0
                if progress_callback:
                    progress_callback(pct)
            except Exception:
                continue

    try:
        conn.putrequest("POST", endpoint)
        for key, value in headers.items():
            conn.putheader(key, value)
        conn.endheaders()
        with source_flac.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                conn.send(chunk)
        if progress_callback:
            poller = threading.Thread(target=poll, daemon=True, name=f"dialogue-ai-{job_id[:8]}")
            poller.start()

        response = conn.getresponse()
        if response.status == 499:
            raise AIDialogueError("AI dialogue isolation was cancelled")
        if response.status >= 300:
            message = response.read(8192).decode("utf-8", errors="replace")
            raise AIDialogueError(f"GPU worker AI dialogue HTTP {response.status}: {message[-1500:]}")
        with dest_flac.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if not dest_flac.exists() or dest_flac.stat().st_size < 1024:
            raise AIDialogueError("GPU worker returned an empty dialogue stem")
        if progress_callback:
            progress_callback(80.0)
        return {
            "job_id": job_id,
            "model": response.getheader("X-Censorarr-Dialogue-Model") or model,
            "device": response.getheader("X-Censorarr-Dialogue-Device") or "unknown",
            "elapsed_seconds": round(time.time() - started, 2),
        }
    except (OSError, http.client.HTTPException) as exc:
        raise AIDialogueError(str(exc)) from exc
    finally:
        stop.set()
        if poller is not None and poller.is_alive():
            poller.join(timeout=1.5)
        try:
            remote_asr._clear_active(job_id)
        except Exception:
            pass
        conn.close()


def _mix_profile(strength: str) -> dict:
    """Return speech lift and sidechain settings for the three user strengths.

    The compressor is keyed only by the AI-isolated dialogue stem. That means the
    soundtrack is left alone when nobody is speaking and smoothly ducks only while
    detected speech is present. The values intentionally favor long, transparent
    release times over aggressive broadcast-style pumping.
    """
    level = str(strength or "medium").lower().strip()
    if level == "light":
        return {
            "voice_gain_db": -10.0,
            "threshold": 0.040,
            "ratio": 2.2,
            "attack_ms": 22,
            "release_ms": 420,
            "sidechain_level": 1.45,
            "target_duck_db": 2,
        }
    if level == "strong":
        return {
            "voice_gain_db": -4.5,
            "threshold": 0.018,
            "ratio": 7.0,
            "attack_ms": 10,
            "release_ms": 650,
            "sidechain_level": 2.40,
            "target_duck_db": 6,
        }
    return {
        "voice_gain_db": -7.0,
        "threshold": 0.026,
        "ratio": 4.0,
        "attack_ms": 15,
        "release_ms": 520,
        "sidechain_level": 1.90,
        "target_duck_db": 4,
    }


def _build_enhanced_flac(pc, source_flac: Path, dialogue_flac: Path, dest: Path, cfg: dict, progress_callback=None) -> dict:
    dcfg = _dialogue_cfg(cfg)
    strength = str(dcfg.get("strength", "medium"))
    mix = _mix_profile(strength)

    # Prepare the AI dialogue once, split it into a sidechain key and the audible
    # speech layer, then duck the original movie mix only while that key is active.
    # This preserves full-impact music/effects in non-dialogue moments while reducing
    # masking during speech. The limiter catches only final peaks after remixing.
    filt = (
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[base];"
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        "highpass=f=80,lowpass=f=12000,"
        "acompressor=threshold=0.085:ratio=2.4:attack=8:release=150:makeup=1.10,"
        "asplit=2[voicekey][voiceaud];"
        f"[base][voicekey]sidechaincompress=threshold={mix['threshold']:.3f}:"
        f"ratio={mix['ratio']:.2f}:attack={mix['attack_ms']}:release={mix['release_ms']}:"
        f"knee=3:level_sc={mix['sidechain_level']:.2f}:mix=1[ducked];"
        f"[voiceaud]volume={mix['voice_gain_db']:.1f}dB[voice];"
        "[ducked][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.95[enh]"
    )
    probe = pc.ffprobe(source_flac)
    pc.logging.info(
        "AI Dialogue remix: strength=%s dialogue-aware duck≈%sdB voice_layer=%+.1fdB attack=%sms release=%sms",
        strength,
        mix["target_duck_db"],
        mix["voice_gain_db"],
        mix["attack_ms"],
        mix["release_ms"],
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-i", str(source_flac), "-i", str(dialogue_flac),
        "-filter_complex", filt, "-map", "[enh]",
        "-c:a", "flac", "-compression_level", "5", str(dest),
    ]
    if progress_callback:
        pc.run_ffmpeg_progress(
            cmd,
            pc.duration_of(probe),
            lambda pct: progress_callback(80.0 + min(8.0, pct * 0.08)),
        )
    else:
        pc.run(cmd)
    return {
        "ducking": True,
        "strength": strength,
        "target_duck_db": mix["target_duck_db"],
        "voice_gain_db": mix["voice_gain_db"],
        "attack_ms": mix["attack_ms"],
        "release_ms": mix["release_ms"],
    }


def add_ai_dialogue_track(
    pc,
    src: Path,
    out: Path,
    audio_rel: int,
    cfg: dict,
    find_named_audio,
    progress_callback=None,
) -> dict:
    dcfg = _dialogue_cfg(cfg)
    title = str(dcfg.get("title") or "English - DIALOGUE ENHANCED").strip()
    if not title:
        raise AIDialogueError("Dialogue enhancement title cannot be blank")

    current_probe = pc.ffprobe(out)
    existing = find_named_audio(current_probe, title)
    replace = bool(dcfg.get("replace_existing", True))
    if existing and not replace:
        pc.logging.info("AI Dialogue track already exists; leaving it unchanged: %s", title)
        return {"method": "ai", "status": "exists"}

    workroot = Path("/work")
    workroot.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="censorarr-dialogue-ai-", dir=str(workroot)))
    source_flac = workdir / "source.flac"
    stem_flac = workdir / "dialogue.flac"
    enhanced_flac = workdir / "enhanced.flac"
    try:
        pc.logging.info("AI Dialogue: extracting selected source audio as stereo FLAC")
        _extract_source_flac(pc, src, audio_rel, source_flac, progress_callback)
        caps = worker_capabilities(cfg)
        if not caps.get("dialogue_ai"):
            reason = caps.get("reason") or "GPU worker does not advertise dialogue_ai"
            raise AIDialogueError(str(reason))

        pc.logging.info(
            "AI Dialogue: isolating dialogue on GPU worker (model=%s)",
            dcfg.get("ai_model") or DEFAULT_MODEL,
        )
        remote_meta = _remote_isolate(source_flac, stem_flac, cfg, progress_callback)
        pc.logging.info(
            "AI Dialogue: isolated stem complete (model=%s device=%s elapsed=%ss)",
            remote_meta.get("model"), remote_meta.get("device"), remote_meta.get("elapsed_seconds"),
        )
        mix_meta = _build_enhanced_flac(pc, source_flac, stem_flac, enhanced_flac, cfg, progress_callback)

        current_probe = pc.ffprobe(out)
        existing = find_named_audio(current_probe, title)
        excluded = {int(stream.get("index", -1)) for stream, _rel in existing} if replace else set()
        retained_audio_count = sum(
            1 for stream in current_probe.get("streams", []) or []
            if stream.get("codec_type") == "audio" and int(stream.get("index", -1)) not in excluded
        )
        temp = out.with_name(out.stem + ".dialogue-ai.tmp" + out.suffix)
        if temp.exists():
            temp.unlink()
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-i", str(out), "-i", str(enhanced_flac),
            ]
            for stream in sorted(current_probe.get("streams", []) or [], key=lambda x: int(x.get("index", 0))):
                gi = int(stream.get("index", 0))
                if gi in excluded:
                    continue
                cmd += ["-map", f"0:{gi}"]
            cmd += ["-map", "1:a:0", "-map_metadata", "0", "-map_chapters", "0", "-c", "copy"]

            new_rel = retained_audio_count
            codec = str(dcfg.get("codec") or "aac").strip().lower()
            bitrate = str(dcfg.get("bitrate") or "192k").strip()
            cmd += [f"-c:a:{new_rel}", codec, f"-ac:a:{new_rel}", "2"]
            if bitrate:
                cmd += [f"-b:a:{new_rel}", bitrate]
            cmd += [
                f"-metadata:s:a:{new_rel}", f"title={title}",
                f"-metadata:s:a:{new_rel}", f"language={dcfg.get('language', 'eng')}",
            ]
            if out.suffix.lower() in {".mp4", ".m4v"}:
                cmd += [f"-metadata:s:a:{new_rel}", f"handler_name={title}"]
            if bool(dcfg.get("make_default", False)):
                for i in range(retained_audio_count + 1):
                    cmd += [f"-disposition:a:{i}", "0"]
                cmd += [f"-disposition:a:{new_rel}", "default"]
            else:
                cmd += [f"-disposition:a:{new_rel}", "0"]
            cmd += [str(temp)]

            duration = pc.duration_of(current_probe)
            if progress_callback:
                pc.run_ffmpeg_progress(cmd, duration, lambda pct: progress_callback(88.0 + min(12.0, pct * 0.12)))
            else:
                pc.run(cmd)
            check = pc.ffprobe(temp)
            found = find_named_audio(check, title)
            if len(found) != 1:
                raise AIDialogueError(
                    f"AI Dialogue validation failed: expected one track titled {title!r}, found {len(found)}"
                )
            os.replace(temp, out)
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
        if progress_callback:
            progress_callback(100.0)
        return {"method": "ai", **remote_meta, **mix_meta}
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
