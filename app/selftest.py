#!/usr/bin/env python3
import subprocess
import tempfile
import time
import sys
import types
from pathlib import Path

# Allow parser/matcher/remux construction tests to run in a source checkout that does not
# have faster-whisper installed. The real Docker image always installs it from requirements.txt.
try:
    import faster_whisper  # noqa: F401
except ModuleNotFoundError:
    fw = types.ModuleType('faster_whisper')
    class _WhisperModelStub:
        pass
    fw.WhisperModel = _WhisperModelStub
    sys.modules['faster_whisper'] = fw

import censorarr as pc
import subtitle_assist as sa
import integrations as integrations


def profanity_tests(matcher):
    cases = [
        ([{'start':0,'end':.3,'word':'asshole','probability':.9}], 'arsehole'),
        ([{'start':0,'end':.2,'word':'ass','probability':.9},{'start':.2,'end':.5,'word':'hole','probability':.9}], 'arsehole'),
        ([{'start':0,'end':.3,'word':'assholes','probability':.9}], 'arsehole'),
        ([{'start':0,'end':.3,'word':'shits','probability':.9}], 'shit'),
        ([{'start':0,'end':.3,'word':'shitting','probability':.9}], 'shit'),
    ]
    for words, expected in cases:
        got = matcher.match_words(words)
        assert got and got[0].matched_id == expected, (words, got)
    fuzzy = matcher.fuzzy_targets('hassle', .72)
    assert any(x[0] == 'arsehole' for x in fuzzy), fuzzy
    print('Matcher/family/fuzzy tests: PASS')
    print('Active severity>=3 entries:', len(matcher.active))
    print('hassle fuzzy target:', fuzzy[0])


def mute_filter_tests():
    ranges = [(i * .10, i * .10 + .05) for i in range(183)]
    filt = pc.build_mute_filter(ranges)
    pieces = filt.split(',volume=')
    assert len(pieces) == 3, len(pieces)
    assert filt.count('between(') == 183
    # Actual FFmpeg parser check; this catches the >100-term expression regression.
    cmd = [
        'ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','anullsrc=r=8000:cl=mono',
        '-t','0.2','-af',filt,'-f','null','-'
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print('Large-mute FFmpeg batching test (183 ranges): PASS')


def subtitle_tests(matcher):
    with tempfile.TemporaryDirectory(prefix='censorarr-selftest-') as td:
        p = Path(td) / 'sample.srt'
        p.write_text(
            '1\n00:00:40,000 --> 00:00:44,000\n'
            "Don't go out a total asshole. Cooperate for once.\n\n",
            encoding='utf-8'
        )
        cues = sa.parse_srt(p)
        assert len(cues) == 1 and 'asshole' in cues[0]['text'].lower()
        # Simulate the known class of ASR miss: subtitle says asshole, ASR says hassle.
        words_text = ["Don't", 'go', 'out', 'a', 'total', 'hassle', 'Cooperate', 'for', 'once']
        tw = []
        t = 10.05
        for word in words_text:
            tw.append({'start': t, 'end': t + .32, 'word': word, 'probability': .85})
            t += .38
        cfg = {'subtitle_assist': {'enabled': True, 'alignment_tolerance_seconds': 2.0,
                                   'minimum_alignment_ratio': .45}}
        cand = sa.build_candidates(cues, tw, matcher, cfg)
        hit = next((x for x in cand if x['matched_id'] == 'arsehole'), None)
        assert hit, cand
        assert 'hassle' in hit.get('baseline_text', '').lower(), hit
        assert hit.get('strong_alignment') is True, hit
        assert hit.get('alignment_method') == 'global-text', hit
        assert hit.get('start',99) < 20, hit  # proves text alignment ignored the subtitle's +30s timestamp error
        print('Global subtitle/transcript alignment test (+30s bad timing, asshole vs hassle): PASS')




def mp4_clean_track_metadata_tests():
    """Regression test for MP4 CLEAN-track naming/validation."""
    with tempfile.TemporaryDirectory(prefix='censorarr-mp4-meta-') as td:
        td = Path(td)
        src = td / 'source.mp4'
        out = td / 'output.mp4'
        subprocess.run([
            'ffmpeg','-hide_banner','-loglevel','error','-y',
            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','0.5','-c:a','aac',str(src)
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cfg = {
            'clean_track': {
                'title': 'English - CLEAN', 'language': 'eng',
                'replace_existing_clean': True, 'codec': 'auto', 'place_clean_first': True, 'make_default': True,
            },
            'safety': {'duration_tolerance_seconds': 2.0},
        }
        src_probe = pc.ffprobe(src)
        seen_progress = []
        pc.remux_with_clean_track(src, out, 0, src_probe, [], cfg, progress_callback=seen_progress.append)
        assert seen_progress and seen_progress[-1] == 100.0, seen_progress
        out_probe = pc.ffprobe(out)
        pc.validate_output(src_probe, out_probe, cfg)
        clean = pc.find_clean_audio_streams(out_probe, 'English - CLEAN')
        assert len(clean) == 1, clean
        clean_stream, clean_rel = clean[0]
        assert clean_rel == 0, clean
        assert bool((clean_stream.get('disposition') or {}).get('default')), clean_stream
        audio = [st for st in out_probe.get('streams', []) if st.get('codec_type') == 'audio']
        assert len(audio) == 2, audio
        assert not bool((audio[1].get('disposition') or {}).get('default')), audio
        tags = clean_stream.get('tags', {}) or {}
        assert str(tags.get('handler_name', '')).strip() == 'English - CLEAN', tags
        print('MP4 CLEAN-first + default + handler_name validation test: PASS')


def overall_progress_tests():
    assert pc._overall_progress('preparing', 0) == 0.0
    assert pc._overall_progress('preparing', 100) == 8.0
    assert pc._overall_progress('transcribing', 0) == 8.0
    assert pc._overall_progress('transcribing', 100) == 55.0
    assert pc._overall_progress('rescue', 50) == 67.0
    assert pc._overall_progress('subtitle-assist', 100) == 85.0
    assert pc._overall_progress('remuxing', 100) == 98.0
    assert pc._overall_progress('validating', 100) == 100.0
    assert pc._overall_progress('completed', 0) == 100.0
    print('Dual overall/stage progress mapping tests: PASS')



def precision_alignment_tests():
    cfg = {
        'profanity': {'padding_before_ms': 120, 'padding_after_ms': 160},
        'precision_alignment': {
            'enabled': True, 'padding_before_ms': 100, 'padding_after_ms': 100,
            'edge_search_ms': 0, 'neighbor_guard_ms': 10,
            'energy_threshold_ratio': .22, 'frame_ms': 5,
        },
    }
    det = pc.Detection(start=1.00, end=1.40, text='test', matched_id='test', severity=3, source='normal')
    words = [
        {'start': .60, 'end': .95, 'word': 'previous', 'probability': .9},
        {'start': 1.00, 'end': 1.40, 'word': 'test', 'probability': .9},
        {'start': 1.45, 'end': 1.80, 'word': 'next', 'probability': .9},
    ]
    ranges = pc.merge_mute_ranges([det], cfg, words=words)
    assert len(ranges) == 1, ranges
    # 100 ms padding would normally reach .90 and 1.50. Neighbor guards keep it out of adjacent words.
    assert ranges[0][0] >= .96 - 1e-6, ranges
    assert ranges[0][1] <= 1.44 + 1e-6, ranges
    legacy = {'profanity': {'padding_before_ms': 120, 'padding_after_ms': 160}, 'precision_alignment': {'enabled': False}}
    lr = pc.merge_mute_ranges([det], legacy)
    assert abs(lr[0][0] - .88) < .001 and abs(lr[0][1] - 1.56) < .001, lr
    print('Precision mute neighbor-protection + legacy fallback tests: PASS')


def schedule_tests():
    cfg = {'processing_schedule': {'enabled': True, 'start': '23:00', 'end': '06:00', 'days': [0]}}
    # Monday 23:30 should be in; Tuesday 01:00 belongs to Monday's overnight window; Tuesday 07:00 is out.
    mon = time.struct_time((2026,8,17,23,30,0,0,229,-1))
    tue_early = time.struct_time((2026,8,18,1,0,0,1,230,-1))
    tue_late = time.struct_time((2026,8,18,7,0,0,1,230,-1))
    assert integrations.schedule_allows_now(cfg, mon)[0]
    assert integrations.schedule_allows_now(cfg, tue_early)[0]
    assert not integrations.schedule_allows_now(cfg, tue_late)[0]
    print('Overnight processing-schedule test: PASS')



def media_file_readability_tests():
    with tempfile.TemporaryDirectory() as td:
        media = Path(td) / "sample.mkv"
        media.write_bytes(b"x")
        ok, detail = pc.media_file_readable(media)
        assert ok is True and detail == "", (ok, detail)
        sig = pc.runtime_identity_signature()
        assert isinstance(sig, str) and sig, sig


def media_preflight_tests():
    with tempfile.TemporaryDirectory() as td:
        movies = Path(td) / "movies"
        movies.mkdir()
        cfg = pc.deep_merge(pc.DEFAULT_CONFIG, {
            "media_roots": [str(movies)],
            "tv": {"enabled": False},
            "dry_run": True,
        })
        result = pc.media_access_preflight(cfg)
        assert result["ok"], result
        assert result["roots"][0]["readable"] is True, result


def tv_tests():
    cfg = {
        'media_roots': ['/media'],
        'rating_filter': {'enabled': True, 'minimum': 'PG-13'},
        'tv': {'enabled': True, 'media_roots': ['/tv'], 'rating_filter': {'enabled': True, 'minimum': 'TV-14'}},
    }
    assert pc.media_type_for(Path('/tv/Example/Season 01/Example.S01E01.mkv'), cfg) == 'episode'
    assert pc.media_type_for(Path('/media/Example (2026)/Example.mkv'), cfg) == 'movie'
    old = pc.plex_rating_for
    try:
        pc.plex_rating_for = lambda media, _cfg: ('TV-PG', 'test') if str(media).startswith('/tv/') else ('PG-13', 'test')
        assert pc.rating_decision(Path('/tv/Example/Season 01/E01.mkv'), cfg)[0] == 'skip'
        pc.plex_rating_for = lambda media, _cfg: ('TV-14', 'test') if str(media).startswith('/tv/') else ('PG-13', 'test')
        assert pc.rating_decision(Path('/tv/Example/Season 01/E01.mkv'), cfg)[0] == 'process'
        assert pc.rating_decision(Path('/media/Example.mkv'), cfg)[0] == 'process'
    finally:
        pc.plex_rating_for = old
    old_series = integrations.bazarr_series
    try:
        integrations.bazarr_series = lambda _cfg, force=False: [{'_mapped_path':'/tv/Example','sonarrSeriesId':42,'title':'Example'}]
        hit = integrations.bazarr_series_for_episode(Path('/tv/Example/Season 01/E01.mkv'), cfg)
        assert hit and hit['sonarrSeriesId'] == 42
    finally:
        integrations.bazarr_series = old_series
    print('TV library/rating/Bazarr-series mapping tests: PASS')


def sonarr_episode_join_tests():
    cfg = {'arr_integrations': {'sonarr': {'enabled': True, 'url': 'http://sonarr', 'api_key': 'x',
            'path_mappings': [{'from': '/volume1/TV Shows', 'to': '/tv'}]}}}
    old_req = integrations._arr_request
    old_series = integrations.sonarr_series
    try:
        def fake_req(_cfg, name, path, timeout=30):
            assert name == 'sonarr'
            if path.startswith('/api/v3/episode?'):
                return [{'id': 1, 'seasonNumber': 1, 'episodeNumber': 2, 'title': 'Test Episode',
                         'hasFile': True, 'episodeFileId': 10}]
            if path.startswith('/api/v3/episodefile?'):
                return [{'id': 10, 'path': '/volume1/TV Shows/Test Show/Season 01/Test.S01E02.mkv',
                         'size': 1234, 'quality': {'quality': {'name': 'WEBDL-1080p'}}}]
            raise AssertionError(path)
        integrations._arr_request = fake_req
        integrations.sonarr_series = lambda _cfg, force=False: [{'id': 42, 'path': '/volume1/TV Shows/Test Show'}]
        eps = integrations.sonarr_episodes(cfg, 42)
        assert len(eps) == 1, eps
        ef = eps[0].get('episodeFile') or {}
        assert ef.get('_mapped_file') == '/tv/Test Show/Season 01/Test.S01E02.mkv', ef
        assert ef.get('quality', {}).get('quality', {}).get('name') == 'WEBDL-1080p', ef
        print('Sonarr episode/episode-file path join test: PASS')
    finally:
        integrations._arr_request = old_req
        integrations.sonarr_series = old_series


def main():
    data_path = Path('/config/en.json') if Path('/config/en.json').exists() else (Path('/app/en.json') if Path('/app/en.json').exists() else Path(__file__).resolve().parent.parent / 'en.json')
    matcher = pc.ProfanityMatcher(data_path, 3, 4)
    profanity_tests(matcher)
    mute_filter_tests()
    subtitle_tests(matcher)
    mp4_clean_track_metadata_tests()
    overall_progress_tests()
    precision_alignment_tests()
    schedule_tests()
    media_file_readability_tests()
    media_preflight_tests()
    tv_tests()
    sonarr_episode_join_tests()
    print('Censorarr v%s self-test: ALL PASS' % pc.VERSION)


if __name__ == '__main__':
    main()
