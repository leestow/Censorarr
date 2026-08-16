from __future__ import annotations

import html
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

TEXT_CODECS = {
    "subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "microdvd", "subviewer", "subviewer1",
}
IMAGE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
EXTERNAL_EXTS = {".srt", ".ass", ".ssa", ".vtt"}
EN_TAGS = {"en", "eng", "english", "en-us", "en-gb"}
FORCED_WORDS = {"forced", "foreign", "signs", "songs"}

ALIGN_STOPWORDS = {
    "the","a","an","and","or","but","to","of","in","on","at","for","from","with","is","it","i","you","he","she","we","they",
    "this","that","these","those","my","your","his","her","our","their","be","am","are","was","were","do","did","does","have","has",
    "had","not","no","yes","so","if","as","me","him","them","what","who","why","how","when","where"
}


def norm_word(text: str) -> str:
    text = html.unescape(text or "").lower().replace("’", "'").strip()
    return re.sub(r"^[^a-z0-9']+|[^a-z0-9']+$", "", text)


def subtitle_cfg(cfg: dict) -> dict:
    return cfg.get("subtitle_assist", {})


def _external_language_kind(media: Path, p: Path) -> tuple[bool, bool, int]:
    """Return (english_or_untagged, forced, preference_score)."""
    mstem = media.stem.lower()
    stem = p.stem.lower()
    if not stem.startswith(mstem):
        return False, False, -1
    suffix = stem[len(mstem):].strip(" ._-[]()")
    toks = {x for x in re.split(r"[. _\-\[\]()]+", suffix) if x}
    forced = bool(toks & FORCED_WORDS)
    if not suffix:
        return True, forced, 50
    if toks & EN_TAGS:
        return True, forced, 100
    # Common explicit foreign language tags: if a short alphabetic language-looking token exists and it isn't English,
    # do not accidentally treat the subtitle as English.
    explicit = [x for x in toks if 2 <= len(x) <= 3 and x.isalpha()]
    if explicit:
        return False, forced, -1
    return True, forced, 40


def list_sources(media: Path, probe: dict, cfg: dict) -> list[dict]:
    scfg = subtitle_cfg(cfg)
    if not scfg.get("enabled", True):
        return []
    ignore_forced = bool(scfg.get("ignore_forced_only", True))
    accept_untagged = bool(scfg.get("accept_untagged_english", True))
    sources: list[dict] = []

    if scfg.get("use_external", True):
        try:
            for p in media.parent.iterdir():
                if not p.is_file() or p.suffix.lower() not in EXTERNAL_EXTS:
                    continue
                ok, forced, score = _external_language_kind(media, p)
                if not ok:
                    continue
                if not accept_untagged and score < 100:
                    continue
                if ignore_forced and forced:
                    continue
                sources.append({"type": "external", "path": str(p), "codec": p.suffix.lower().lstrip("."),
                                "language": "eng" if score >= 100 else "und", "forced": forced,
                                "score": score + 30})
        except OSError:
            pass

    if scfg.get("use_embedded", True):
        rel = 0
        for s in probe.get("streams", []):
            if s.get("codec_type") != "subtitle":
                continue
            codec = str(s.get("codec_name", "")).lower()
            tags = s.get("tags", {}) or {}
            lang = str(tags.get("language", "")).lower()
            title = str(tags.get("title", "")).lower()
            disp = s.get("disposition", {}) or {}
            forced = bool(disp.get("forced")) or "forced" in title
            usable = codec in TEXT_CODECS or (codec and codec not in IMAGE_CODECS)
            # Unknown subtitle codecs are worth trying only when tagged English; FFmpeg conversion is the final arbiter.
            english = lang in EN_TAGS or (not lang and accept_untagged)
            if usable and english and not (ignore_forced and forced):
                score = 90 if lang in EN_TAGS else 35
                if not forced:
                    score += 10
                sources.append({"type": "embedded", "relative_index": rel, "global_index": s.get("index"),
                                "codec": codec, "language": lang or "und", "forced": forced,
                                "title": tags.get("title"), "score": score})
            rel += 1

    # Prefer explicit English full-dialogue text sources. External gets a slight preference because Bazarr-managed files
    # are easy to refresh/replace and their language is explicit in the filename.
    sources.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    return sources


def image_subtitle_summary(probe: dict) -> list[dict]:
    out = []
    rel = 0
    for s in probe.get("streams", []):
        if s.get("codec_type") != "subtitle":
            continue
        codec = str(s.get("codec_name", "")).lower()
        if codec in IMAGE_CODECS:
            tags = s.get("tags", {}) or {}
            out.append({"relative_index": rel, "codec": codec, "language": tags.get("language"), "title": tags.get("title")})
        rel += 1
    return out


def has_usable_source(media: Path, probe: dict, cfg: dict) -> bool:
    return bool(list_sources(media, probe, cfg))


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def materialize_best(media: Path, probe: dict, cfg: dict, workdir: Path) -> tuple[Path | None, dict | None, list[dict]]:
    sources = list_sources(media, probe, cfg)
    errors: list[dict] = []
    for i, src in enumerate(sources):
        out = workdir / f"subtitle-{i:02d}.srt"
        try:
            if src["type"] == "external" and Path(src["path"]).suffix.lower() == ".srt":
                # Copy rather than parse in-place so the report never depends on a file Bazarr may later replace.
                out.write_bytes(Path(src["path"]).read_bytes())
            elif src["type"] == "external":
                _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src["path"]),
                      "-c:s", "srt", str(out)])
            else:
                _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(media),
                      "-map", f"0:s:{int(src['relative_index'])}", "-c:s", "srt", str(out)])
            if out.exists() and out.stat().st_size:
                cues = parse_srt(out)
                if cues:
                    chosen = dict(src)
                    chosen["cue_count"] = len(cues)
                    return out, chosen, errors
                errors.append({"source": src, "error": "converted subtitle contained no parseable cues"})
        except Exception as e:
            err = str(e)
            if isinstance(e, subprocess.CalledProcessError) and e.stderr:
                err = e.stderr.strip()[-1000:]
            errors.append({"source": src, "error": err})
            try:
                out.unlink()
            except OSError:
                pass
    return None, None, errors


def _parse_ts(v: str) -> float:
    v = v.strip().replace(".", ",")
    parts = v.split(":")
    if len(parts) != 3:
        raise ValueError(v)
    h = int(parts[0]); m = int(parts[1])
    sec, ms = (parts[2].split(",", 1) + ["0"])[:2]
    return h * 3600 + m * 60 + int(sec) + int(ms.ljust(3, "0")[:3]) / 1000.0


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{\\[^}]+\}", " ", text)  # ASS override tags
    text = re.sub(r"\\N|\\n", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_srt(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", raw)
    cues: list[dict] = []
    time_re = re.compile(r"(?P<a>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(?P<b>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})")
    for b in blocks:
        lines = [x.strip("\ufeff") for x in b.splitlines() if x.strip()]
        if not lines:
            continue
        ti = next((i for i, x in enumerate(lines) if "-->" in x), -1)
        if ti < 0:
            continue
        m = time_re.search(lines[ti])
        if not m:
            continue
        try:
            start = _parse_ts(m.group("a")); end = _parse_ts(m.group("b"))
        except Exception:
            continue
        text = clean_text(" ".join(lines[ti + 1:]))
        if text and end > start:
            cues.append({"start": start, "end": end, "text": text})
    return cues


def cue_tokens(text: str) -> list[str]:
    # Keep apostrophes and contractions together. The profanity matcher performs its own normalization afterward.
    return re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?", clean_text(text))


def _alignment_maps(sub_tokens: list[str], transcript_words: list[dict]) -> tuple[dict[int, list[int]], float, list[str]]:
    a = [norm_word(x) for x in sub_tokens]
    b = [norm_word(x.get("word", "")) for x in transcript_words]
    a = [x for x in a if x]
    # transcript indexes must remain stable; blank words are represented as unique placeholders rather than removed.
    bb = [x if x else f"__blank_{i}" for i, x in enumerate(b)]
    sm = SequenceMatcher(None, a, bb, autojunk=False)
    maps: dict[int, list[int]] = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                maps[i1 + k] = [j1 + k]
        elif tag == "replace":
            # Associate the whole replacement block. This is the key case for subtitle "asshole" vs ASR "hassle".
            js = list(range(j1, j2))
            for i in range(i1, i2):
                maps[i] = js
        elif tag == "delete":
            for i in range(i1, i2):
                maps[i] = []
    return maps, float(sm.ratio()), a


def _context_tokens(cues: list[dict], cue_index: int, radius: int) -> tuple[list[str], int, int]:
    lo=max(0,cue_index-radius); hi=min(len(cues),cue_index+radius+1)
    out=[]; target_start=target_end=0
    for ci in range(lo,hi):
        if ci == cue_index: target_start=len(out)
        out.extend(cue_tokens(cues[ci]["text"]))
        if ci == cue_index: target_end=len(out)
    return out,target_start,target_end


def _global_align(context: list[str], target0: int, target1: int, transcript_words: list[dict],
                  transcript_norm: list[str], positions: dict[str,list[int]], cfg: dict) -> dict | None:
    scfg=subtitle_cfg(cfg); s=[norm_word(x) for x in context]
    if not s or not transcript_norm: return None
    # Candidate offsets come from rare, distinctive words around the profanity. This intentionally ignores subtitle
    # timestamps so globally shifted or gradually drifting subtitles can still clarify Whisper.
    anchors=[]
    for i,tok in enumerate(s):
        if target0 <= i < target1 or not tok or tok in ALIGN_STOPWORDS or len(tok)<3: continue
        occ=positions.get(tok,[])
        if occ and len(occ) <= 300: anchors.append((len(occ),abs(i-(target0+target1)/2),i,tok,occ))
    anchors.sort(key=lambda x:(x[0],x[1]))
    candidate_starts=set()
    for _n,_dist,i,_tok,occ in anchors[:8]:
        for pos in occ[:160]:
            base=pos-i
            for delta in (-3,-2,-1,0,1,2,3): candidate_starts.add(base+delta)
    if not candidate_starts: return None
    best=None; min_ratio=float(scfg.get("global_minimum_ratio",.58)); min_anchors=int(scfg.get("global_minimum_anchor_words",3))
    # Bound work for pathological repetitive dialogue/subtitles.
    for base in list(candidate_starts)[:1800]:
        w0=max(0,base-5); w1=min(len(transcript_norm),base+len(s)+5)
        if w1-w0 < max(3,len(s)//3): continue
        bb=transcript_norm[w0:w1]
        maps,ratio,_=_alignment_maps(context,[transcript_words[j] for j in range(w0,w1)])
        exact=0
        for i in range(len(s)):
            if target0 <= i < target1: continue
            if any(0 <= j < len(bb) and s[i] == bb[j] for j in maps.get(i,[])): exact += 1
        score=ratio + min(exact,10)*.012
        if best is None or score > best[0]: best=(score,ratio,exact,w0,maps)
    if not best: return None
    _score,ratio,exact,w0,maps=best
    if ratio < min_ratio or exact < min_anchors: return None
    js=[]
    for i in range(target0,target1): js.extend(maps.get(i,[]))
    js=sorted(set(w0+j for j in js if 0 <= w0+j < len(transcript_words)))
    if js:
        st=min(float(transcript_words[j]["start"]) for j in js); en=max(float(transcript_words[j]["end"]) for j in js)
        baseline=" ".join(str(transcript_words[j].get("word","")).strip() for j in js)
    else:
        # Whisper may have omitted the subtitle word completely. Infer a narrow span between the closest aligned
        # words on either side, but only when both anchors exist.
        prev=[]; nxt=[]
        for i in range(target0-1,-1,-1):
            if maps.get(i): prev=[w0+j for j in maps[i]]; break
        for i in range(target1,len(context)):
            if maps.get(i): nxt=[w0+j for j in maps[i]]; break
        if not prev or not nxt: return None
        pj=max(j for j in prev if 0<=j<len(transcript_words)); nj=min(j for j in nxt if 0<=j<len(transcript_words))
        st=float(transcript_words[pj]["end"]); en=float(transcript_words[nj]["start"])
        if en <= st: en=st+.25
        if en-st > 2.0: return None
        baseline="[ASR omitted word]"
    return {"start":st,"end":max(en,st+.15),"baseline":baseline,"ratio":ratio,"anchors":exact,"method":"global-text"}


def build_candidates(cues: list[dict], transcript_words: list[dict], matcher: Any, cfg: dict) -> list[dict]:
    scfg = subtitle_cfg(cfg)
    tol = float(scfg.get("alignment_tolerance_seconds", 2.0))
    min_ratio = float(scfg.get("minimum_alignment_ratio", 0.45))
    use_global=bool(scfg.get("global_text_alignment",True)); radius=max(0,min(3,int(scfg.get("global_context_cues",1))))
    transcript_norm=[norm_word(w.get("word","")) or f"__blank_{i}" for i,w in enumerate(transcript_words)]
    positions:dict[str,list[int]]={}
    for i,t in enumerate(transcript_norm):
        if not t.startswith("__blank_"): positions.setdefault(t,[]).append(i)
    out: list[dict] = []
    offsets=[]
    for ci, cue in enumerate(cues):
        toks = cue_tokens(cue["text"])
        if not toks: continue
        pseudo = [{"start": float(i), "end": float(i + 1), "word": t, "probability": 1.0} for i, t in enumerate(toks)]
        matches = matcher.match_words(pseudo, source="subtitle")
        if not matches: continue
        # Timestamp-local alignment remains a fallback; global textual alignment is attempted first.
        tw = [w for w in transcript_words if float(w.get("end", 0)) >= cue["start"] - tol and float(w.get("start", 0)) <= cue["end"] + tol]
        maps, ratio, norm_sub = _alignment_maps(toks, tw)
        ctx,ctx_cue0,ctx_cue1=_context_tokens(cues,ci,radius)
        for d in matches:
            i0=max(0,int(d.start)); i1=min(len(toks),max(i0+1,int(round(d.end))))
            global_hit=None
            if use_global:
                global_hit=_global_align(ctx,ctx_cue0+i0,ctx_cue0+i1,transcript_words,transcript_norm,positions,cfg)
            if global_hit:
                start=global_hit["start"]; end=global_hit["end"]; baseline=global_hit["baseline"]
                strong=True; aratio=float(global_hit["ratio"]); method="global-text"; anchors=int(global_hit["anchors"])
            else:
                js=[]
                for i in range(i0,i1): js.extend(maps.get(i,[]))
                js=sorted(set(x for x in js if 0<=x<len(tw)))
                if js:
                    start=min(float(tw[j]["start"]) for j in js); end=max(float(tw[j]["end"]) for j in js)
                    baseline=" ".join(str(tw[j].get("word","")).strip() for j in js)
                    neighbors=[]
                    for ni in (i0-2,i0-1,i1,i1+1):
                        if 0<=ni<len(norm_sub) and maps.get(ni):
                            for j in maps[ni]:
                                if 0<=j<len(tw) and norm_sub[ni]==norm_word(tw[j].get("word","")): neighbors.append(ni); break
                    strong=ratio>=min_ratio and bool(neighbors); aratio=ratio; method="timestamp-local"; anchors=len(neighbors)
                else:
                    frac0=i0/max(1,len(toks)); frac1=i1/max(1,len(toks))
                    start=cue["start"]+(cue["end"]-cue["start"])*frac0; end=cue["start"]+(cue["end"]-cue["start"])*frac1
                    baseline=""; strong=False; aratio=ratio; method="subtitle-time-estimate"; anchors=0
            cue_target_mid=cue["start"]+(cue["end"]-cue["start"])*(((i0+i1)/2)/max(1,len(toks)))
            off=((start+end)/2)-cue_target_mid
            if strong: offsets.append((cue_target_mid,off))
            out.append({"cue_index":ci,"cue_start":cue["start"],"cue_end":cue["end"],"subtitle_text":cue["text"],
                        "start":start,"end":max(end,start+.15),"text":" ".join(toks[i0:i1]),"matched_id":d.matched_id,
                        "severity":d.severity,"alignment_ratio":aratio,"alignment_method":method,"anchor_words":anchors,
                        "subtitle_offset_seconds":round(off,3),"baseline_text":baseline,"strong_alignment":strong})
    dedup=[]
    for c in sorted(out,key=lambda x:(x["start"],x["end"],x["matched_id"])):
        if any(c["matched_id"]==x["matched_id"] and abs(c["start"]-x["start"])<.15 and abs(c["end"]-x["end"])<.3 for x in dedup): continue
        dedup.append(c)
    return dedup
