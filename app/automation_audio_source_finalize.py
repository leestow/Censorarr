"""Final marker guard for automation audio-source decisions."""
from __future__ import annotations


def install(pc, sources) -> None:
    original_process = pc.process_file

    def process_with_source_marker_finalize(path, cfg, model, matcher):
        result = original_process(path, cfg, model, matcher)
        status = str((result or {}).get("status") or "")
        skipped = bool((result or {}).get("dialogue_skipped_source")) or status == "dialogue-source-skipped"
        if skipped:
            key = str(path)
            sources._LAST_DIALOGUE_SOURCE.setdefault(key, {
                "kind": "skipped",
                "requested": "clean_only",
                "reason": "clean-track-unavailable",
                "fallback_used": False,
            })
            try:
                pc.marker_write(
                    path,
                    cfg,
                    status or "dialogue-source-skipped",
                    report=(result or {}).get("report"),
                    completed_features={"dialogue_enhancement"},
                )
            except Exception as exc:
                pc.logging.warning("Could not finalize Dialogue Enhancement source skip marker for %s: %s", path, exc)
        return result

    pc.process_file = process_with_source_marker_finalize
