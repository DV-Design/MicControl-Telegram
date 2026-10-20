# Review: independent speaker verification diagnostic

Date: 2026-10-20. Scope: host-only research helper, pinned public models, public LibriSpeech fixtures, enrollment design. No app Java/JNI/Gradle integration, microphone capture, auth, production thresholds or Android verification-model performance claims.

Verdict: **research control completed; owner-only product integration remains blocked**. Existing tracking: `miccontrol-m1b` (model quality) and `miccontrol-ulk` (isolated native prototype); parent owns issue updates. The review follows the existing microphone architecture introduced in commits `88e1822` and `c1b8f1a`, without changing those product paths.

## Findings and corrections

1. **P1, unresolved integration blocker: successful separation can select an impostor.** The actual precision control records C0 enrollment on B+C: INT8-full gain B=0.928655 / C=0.111738; FP32 gain B=0.928261 / C=0.111966 (`artifacts/qa/target-voice/precision-control.json`, FP32 mixture case beginning line 47). B-only output is approximately +0.649 dB with either precision. This is not fixed by removing quantization. Keep the feature unintegrated; a verification gate may reject the wrong output but cannot recover removed owner speech. Existing mode-0/1 behavior is outside this research change.

2. **P2, corrected in research: the downloaded WeSpeaker model's sherpa metadata does not reproduce its vendor preprocessing.** Actual metadata has `normalize_samples=0` and lacks `feature_normalize_type`. Sherpa applies utterance mean subtraction only when that key is `global-mean`; its feature defaults also use Povey, high cutoff -400 Hz and `snip_edges=false`. The [official WeSpeaker reference](https://github.com/wenet-e2e/wespeaker/blob/master/wespeaker/bin/infer_onnx.py#L28) uses Hamming, Kaldi's high cutoff 0, complete windows and utterance CMN. Its [exported network](https://github.com/wenet-e2e/wespeaker/blob/master/wespeaker/bin/export_onnx.py#L64) expects those prepared features. The helper now has an explicit compatible vendor path at `tests/miccontrol/speaker_verification_probe.py:130`, using `kaldi-native-fbank` and ONNX Runtime; no hand-written fbank or altered model weights. Torch parity was not tested.

3. **P2, corrected fixture assumption: generated mixture segments are shorter than requested.** The source utterance limit makes the existing WAV 318,240 samples: six segments of 53,040 samples (3.315 seconds), not six four-second segments. The initial failure log is preserved as `artifacts/research/speaker-verification/probe-initial-fixture-length-error.log`. The helper derives segment length from the actual mixture, checks divisibility and output length, then excludes 4,000 samples at each end, matching the existing TSE metrics. JSON is checkpointed before fixture-specific output processing; embedding caches bind model hash, SDK version, preprocessing and exact waveform bytes.

These are evidence-based corrections to the experiment. The poor initial SDK result does **not** establish that speaker verification cannot help.

## Actual results

All runs used fixed 3-second references from each speaker's utterance 0. Evaluation used utterances 1 and 2: six independent queries. The three same-clip controls are explicitly excluded from independent statistics. Model selection, source audio hashes, every score and output WAV hashes are retained in the ignored JSON artifacts.

| Pipeline | Independent query | Min genuine cosine | Max impostor cosine | Closed-set top-1 |
| --- | --- | ---: | ---: | ---: |
| CAMPPlus, downloaded sherpa metadata | raw full utterance | 0.33134 | 0.75567 | 4/6 |
| CAMPPlus, downloaded sherpa metadata | matched normalized 3s | 0.83277 | 0.83196 | 6/6 |
| WeSpeaker, downloaded sherpa metadata | matched normalized 3s | 0.70899 | 0.58330 | 6/6 |
| WeSpeaker, vendor-compatible preprocessing | raw full utterance | 0.72798 | 0.26439 | 6/6 |
| WeSpeaker, vendor-compatible preprocessing | matched normalized 3s | 0.67469 | 0.27192 | 6/6 |

The WeSpeaker amplitude control compares **identical crops** before/after RMS normalization, avoiding a duration-selection confound. With downloaded SDK metadata its maximum cosine-score change is 0.08945. With vendor-compatible preprocessing it is at most 5.47e-7; same-crop embedding cosine is at least 0.999999999992. Same-clip reference controls are 0.999997 / 0.999983 / 0.999930. This supports a preprocessing mismatch, not a change of identity or model weights.

For the actual wrongly separated C-profile output, the compatible verifier scores B-only as C=0.07696 / B=0.64467; equal-overlap output as C=0.08588 / B=0.52271; B after overlap as C=0.07905 / B=0.65501. It distinguishes the selected impostor on these fixtures. No decision threshold is selected.

One bounded follow-up performed **exactly 126 new embeddings**: non-overlapping windows from the six matched normalized 3-second evaluation clips. Those clips were selected using their future energy and are **noncausal evaluation samples, not a live gate algorithm**. All raw window scores remain; the extra RMS > -45 dBFS stratum is an arbitrary diagnostic grouping, not a calibrated VAD or verification threshold.

| Window | All queries | Min genuine | Max impostor | Top-1 | Active-energy queries | Active min genuine / max impostor |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 250ms | 72 | -0.02774 | 0.25818 | 66/72 | 68 | 0.04747 / 0.25818 |
| 500ms | 36 | -0.03496 | 0.36924 | 33/36 | 35 | 0.07018 / 0.36924 |
| 1s | 18 | 0.44157 | 0.29637 | 18/18 | 18 | 0.44157 / 0.29637 |

The two shorter durations still overlap. The observed one-second gap is limited to these three speakers, correlated windows and one corpus/channel. It is not a population false-accept estimate or a production operating threshold. A pre-transmission gate would have to retain an entire decision window plus processing time; undecided samples cannot already have been forwarded. Overlapping owner/impostor speech, unfamiliar people, language/channel changes, replay and Android latency still need separate validation.

## Reproduction, provenance and limitations

The tracked helper is `tests/miccontrol/speaker_verification_probe.py`; dependencies and model provenance are beside it. No model weights, profile data or audio are committed. Runtime versions: sherpa-onnx 1.13.8, ONNX Runtime 1.31.0, kaldi-native-fbank 1.22.3, NumPy 2.5.4, SoundFile 0.14.0.

- CAMPPlus: 29,596,978 bytes, SHA256 `357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b`; official ModelScope card revision v1.0.2 declares Apache 2.0.
- WeSpeaker ResNet34: 26,534,365 bytes, SHA256 `5ef208a9da1453335308a6b6f4e6dfbd7e183a38b604de0a57664f45d257fe94`; **unresolved license conflict**: the official [pretrained-model documentation](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md#model-license) says CC-BY-4.0, while its [specific official model card](https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34/raw/main/README.md) says Apache 2.0. Clarify before app redistribution. Sherpa/kaldi-native-fbank code uses Apache 2.0; that does not resolve the weights' license.

Both downloads match the [official sherpa release checksum](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models). Official Android speaker-identification examples show platform feasibility, not performance of this app. Original SDK baselines, raw short-window results, active-energy supplements, metadata logs, primary source snapshots and corrected results remain under `artifacts/research/speaker-verification/`.

Fresh focused control, with public fixtures already prepared:

```sh
.local/tse-venv/bin/python -m pip install -r tests/miccontrol/speaker_verification_requirements.txt
.local/tse-venv/bin/python tests/miccontrol/speaker_verification_probe.py --candidate wespeaker_resnet34 --preprocessing wespeaker_reference --amplitude-check
```

To reuse the completed run/cache and add only the bounded 126 windows:

```sh
.local/tse-venv/bin/python tests/miccontrol/speaker_verification_probe.py --candidate wespeaker_resnet34 --preprocessing wespeaker_reference --supplement-existing --amplitude-check --short-windows --window-source matched_3s
```

Actual executions additionally used macOS `sandbox-exec` with `(deny network*)` and `--require-egress-block`; the helper verified OS denial before inference. Library/model download happened earlier. No host microphone or accounts were used. The final cache has 159 normalized public-audio embeddings. Syntax checks, dependency validation and focused functional runs passed; no Android app build or broad test suite was run by this review.
