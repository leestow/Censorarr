# Profanity & Detection

Censorarr combines Whisper transcription, profanity matching, rescue passes, and optional subtitle evidence.

## Profanity dictionary

The default configured profanity file is:

```text
/config/en.json
```

Default minimum severity:

```yaml
profanity:
  min_severity: 3
```

Lowering the threshold can make filtering more aggressive.

## Matching

Censorarr supports:

- direct dictionary matches
- word-family aliases
- fuzzy matching
- multi-word windows
- rescue passes around uncertain regions

Example:

```yaml
profanity:
  max_word_window: 4
```

## Rescue mode

Default example:

```yaml
rescue:
  enabled: true
  confidence_trigger: 0.18
  fuzzy_confidence_ceiling: 0.70
  fuzzy_similarity: 0.72
  prefer_center_channel: true
```

The rescue prompt intentionally asks Whisper to transcribe profanity verbatim rather than euphemize it.

## Precision mute alignment

Enabled by default in the example configuration:

```yaml
precision_alignment:
  enabled: true
  padding_before_ms: 25
  padding_after_ms: 40
```

It tightens mute timing by protecting neighboring words and looking for nearby low-energy waveform boundaries.

If disabled, Censorarr falls back to the broader legacy padding:

```yaml
padding_before_ms: 120
padding_after_ms: 160
```

## Subtitle evidence

Subtitle Assist can clarify uncertain dialogue and shifted timing, but Whisper remains part of the detection pipeline.

## Custom profanity and exceptions

Runtime customization files are stored under `/config`, including:

```text
/config/custom_profanity.json
/config/profanity_overrides.json
/config/user_exceptions.json
```

Keep `/config` persistent across updates.

## Accuracy expectations

No ASR system can guarantee perfect detection. Use Dry Run and Review Mode on representative media before applying settings across an entire library.
