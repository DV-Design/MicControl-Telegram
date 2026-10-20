"""Offline diagnostic only: public LibriSpeech + existing VoxLock outputs.

Uses sherpa-onnx or the vendor's Kaldi-compatible preprocessing with ONNX Runtime.
No microphone, network requests, integration, or production decision threshold.
"""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import socket
import time

import numpy as np
import sherpa_onnx
import soundfile as sf


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    assert sr == 16000 and x.shape[1] == 1, (str(path), sr, x.shape)
    assert np.isfinite(x).all()
    return np.ascontiguousarray(x[:, 0])


def rms_dbfs(x):
    return float(20 * np.log10(max(np.sqrt(np.mean(x.astype(np.float64) ** 2)), 1e-12)))


def three_seconds(x, normalize=True):
    """Match the TSE fixture: most energetic 3s in the first 30s, 10ms grid."""
    x = x[:30 * 16000]
    assert len(x) >= 48000
    blocks = len(x) // 160
    energy = np.square(x[:blocks * 160]).reshape(blocks, 160).mean(axis=1)
    sums = np.pad(np.cumsum(energy, dtype=np.float64), (1, 0))
    offset = int(np.argmax(sums[300:] - sums[:-300])) * 160
    crop = x[offset:offset + 48000]
    if not normalize:
        return crop, offset / 16000
    level = np.sqrt(np.mean(np.square(crop.astype(np.float64))) + 1e-14)
    return (crop * (.06 / max(level, 1e-8))).astype(np.float32), offset / 16000


def summary(rows):
    good = [r for r in rows if "scores" in r]
    genuine = [r["scores"][r["speaker"]] for r in good]
    impostor = [s for r in good for k, s in r["scores"].items() if k != r["speaker"]]
    def stats(v):
        return {k: float(np.quantile(v, q)) for k, q in
                (("min", 0), ("p05", .05), ("median", .5), ("p95", .95), ("max", 1))} if v else None
    return {"queries": len(rows), "valid": len(good), "errors": len(rows) - len(good),
            "genuine": stats(genuine), "impostor": stats(impostor),
            "closedSetTop1Correct": sum(max(r["scores"], key=r["scores"].get) == r["speaker"] for r in good),
            "observedGapMinGenuineMinusMaxImpostor": min(genuine) - max(impostor) if genuine else None}


def owner_summary(rows, owners):
    ans = {}
    for owner in owners:
        genuine = [r["scores"][owner] for r in rows if "scores" in r and r["speaker"] == owner]
        impostor = [r["scores"][owner] for r in rows if "scores" in r and r["speaker"] != owner]
        ans[owner] = {"genuineCount": len(genuine), "impostorCount": len(impostor),
                      "minGenuine": min(genuine) if genuine else None,
                      "maxImpostor": max(impostor) if impostor else None,
                      "observedGap": min(genuine) - max(impostor) if genuine and impostor else None}
        if owner == "5639":
            b = [r["scores"][owner] for r in rows if "scores" in r and r["speaker"] == "1320"]
            ans[owner]["speakerBToC"] = {"count": len(b), "min": min(b), "median": float(np.median(b)), "max": max(b)} if b else None
    return ans


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    manifest = json.loads(Path(__file__).with_name("speaker_verification_model.json").read_text())
    ap.add_argument("--candidate", choices=manifest["models"], default="campplus")
    ap.add_argument("--preprocessing", choices=("sherpa_sdk", "wespeaker_reference"), default="sherpa_sdk")
    ap.add_argument("--model", type=Path, help="Override cache path; pinned checksum still required")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--max-windows", type=int, default=16)
    ap.add_argument("--require-egress-block", action="store_true")
    ap.add_argument("--supplement-existing", action="store_true",
                    help="Reuse completed JSON/cache; add 3s/energy checks and explicitly requested windows")
    ap.add_argument("--amplitude-check", action="store_true", help="Compare identical 3s crops before/after RMS0.06 normalization")
    ap.add_argument("--short-windows", action="store_true", help="Explicit opt-in to the larger .25/.5/1s diagnostic")
    ap.add_argument("--window-source", choices=("raw_utterance", "matched_3s"), default="raw_utterance",
                    help="matched_3s is a noncausal energy-selected evaluation sample, not a live gate algorithm")
    ap.add_argument("--debug-metadata", action="store_true", help="Print the official SDK's actual model metadata")
    args = ap.parse_args()
    pinned = manifest["models"][args.candidate]
    assert args.preprocessing != "wespeaker_reference" or args.candidate == "wespeaker_resnet34"
    if args.output is None:
        filename = "probe.json" if args.candidate == "campplus" else "wespeaker-resnet34.json"
        if args.preprocessing == "wespeaker_reference":
            filename = "wespeaker-reference-preprocessing.json"
        args.output = Path("artifacts/research/speaker-verification") / filename
    if args.model is None:
        args.model = Path(".local/target-voice/sv") / pinned["modelUrl"].rsplit("/", 1)[-1]
    assert args.max_windows > 0
    if args.require_egress_block:
        with socket.socket() as test:
            test.settimeout(1)
            assert test.connect_ex(("192.0.2.1", 443)) in (errno.EPERM, errno.EACCES), "OS network block is not active"
    assert sha(args.model) == pinned["sha256"]
    assert args.model.stat().st_size == pinned["bytes"]
    base = Path("artifacts/qa/target-voice")
    source = json.loads((base / "speech/source.json").read_text())
    config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(args.model),
            num_threads=1, debug=args.debug_metadata, provider="cpu")
    assert config.validate()
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
    reference_session = None
    if args.preprocessing == "wespeaker_reference":
        import kaldi_native_fbank as knf
        import onnxruntime as ort
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        reference_session = ort.InferenceSession(str(args.model), options, providers=["CPUExecutionProvider"])

    def compute_vector(x):
        if reference_session is not None:
            # Match official WeSpeaker infer_onnx.py: Kaldi fbank + utterance CMN.
            options = knf.FbankOptions()
            options.frame_opts.samp_freq = 16000
            options.frame_opts.frame_length_ms = 25
            options.frame_opts.frame_shift_ms = 10
            options.frame_opts.dither = 0
            options.frame_opts.snip_edges = True
            options.frame_opts.window_type = "hamming"
            options.mel_opts.num_bins = 80
            options.mel_opts.low_freq = 20
            options.mel_opts.high_freq = 0
            options.use_energy = False
            bank = knf.OnlineFbank(options)
            bank.accept_waveform(16000, (x * 32768).tolist())
            bank.input_finished()
            features = np.stack([bank.get_frame(i) for i in range(bank.num_frames_ready)])
            features -= features.mean(axis=0, keepdims=True)
            return reference_session.run(None, {"feats": features[None]})[0][0]
        stream = extractor.create_stream()
        stream.accept_waveform(sample_rate=16000, waveform=x)
        stream.input_finished()
        if not extractor.is_ready(stream):
            raise ValueError("extractor_not_ready")
        return extractor.compute(stream)
    timings = []
    cache_path = args.output.with_suffix(".embeddings.npz")
    cache = {}
    if cache_path.exists():
        with np.load(cache_path, allow_pickle=False) as saved:
            assert str(saved["modelSha256"]) == sha(args.model)
            assert str(saved["sdkVersion"]) == sherpa_onnx.__version__
            cached_preprocessing = str(saved["preprocessing"]) if "preprocessing" in saved.files else "sherpa_sdk"
            assert cached_preprocessing == args.preprocessing
            cache = {k: saved[k] for k in saved.files if k not in ("modelSha256", "sdkVersion", "preprocessing")}

    def checkpoint_cache():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache_path, modelSha256=sha(args.model), sdkVersion=sherpa_onnx.__version__, preprocessing=args.preprocessing, **cache)

    def checkpoint(result):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        partial = args.output.with_suffix(".json.part")
        partial.write_text(json.dumps(result, indent=2) + "\n")
        partial.replace(args.output)
        checkpoint_cache()

    def embed(x):
        key = "audio_" + hashlib.sha256(x.tobytes()).hexdigest()
        if key in cache:
            value = cache[key]
            assert value.shape == (extractor.dim,) and np.isfinite(value).all()
            assert abs(np.linalg.norm(value) - 1) < 1e-6
            return value
        start = time.perf_counter()
        v = np.asarray(compute_vector(x), dtype=np.float64)
        timings.append({"audioSeconds": len(x) / 16000, "computeMs": (time.perf_counter() - start) * 1000})
        assert v.shape == (extractor.dim,) and np.isfinite(v).all()
        norm = float(np.linalg.norm(v))
        if norm <= 1e-12:
            raise ValueError("zero_embedding")
        cache[key] = v / norm
        return cache[key]

    references = {speaker: embed(read(base / f"reference_{speaker}.wav"))
                  for speaker in source["speakers"]}
    def score(x):
        v = embed(x)
        return {k: float(np.dot(v, r)) for k, r in references.items()}

    def supplement(result):
        for window in result["windows"].values():
            active = [r for r in window["rows"] if r["rmsDbfs"] > -45]
            window["activeEnergySupplement"] = {
                "rmsDbfsGreaterThan": -45,
                "thresholdPurpose": "arbitrary diagnostic energy stratum, not VAD or verification calibration",
                "summary": summary(active), "ownerVerification": owner_summary(active, references)}
        rows = []
        for speaker, names in source["speakers"].items():
            reference = read(base / f"reference_{speaker}.wav")
            for index, name in enumerate(names):
                crop, offset = three_seconds(read(base / "speech" / name))
                row = {"file": name, "speaker": speaker, "seconds": 3, "startSeconds": offset,
                       "rmsDbfs": rms_dbfs(crop), "independentOfReference": index != 0,
                       "scores": score(crop)}
                if args.amplitude_check:
                    raw, raw_offset = three_seconds(read(base / "speech" / name), normalize=False)
                    assert offset == raw_offset
                    raw_scores = score(raw)
                    row["amplitudeControl"] = {"rawRmsDbfs": rms_dbfs(raw),
                            "cosineRawVsNormalizedSameCrop": float(np.dot(embed(raw), embed(crop))),
                            "rawScores": raw_scores,
                            "maxAbsScoreDifference": max(abs(raw_scores[k] - row["scores"][k]) for k in references)}
                if index == 0:
                    row["sameClipControlMaxAbsDifferenceFromPcm16Reference"] = float(np.max(np.abs(crop - reference)))
                rows.append(row)
        independent = [r for r in rows if r["independentOfReference"]]
        result["threeSecondQueries"] = {"summaryIndependent": summary(independent),
                "ownerVerification": owner_summary(independent, references), "rows": rows,
                "selection": "most energetic 3s in first30s, 10ms grid, RMS normalized0.06 to match TSE matrix; index0 same-clip controls excluded"}
        result["embeddingCache"] = {"file": str(cache_path), "entries": len(cache), "sampleKey": "SHA256 float32 waveform bytes"}
        packages = ("sherpa-onnx", "numpy", "soundfile")
        if reference_session is not None:
            packages += ("kaldi-native-fbank", "onnxruntime")
        result["dependencyVersions"] = {k: importlib.metadata.version(k) for k in packages}
        print("3s independent", json.dumps(result["threeSecondQueries"]["summaryIndependent"]), flush=True)

    def calculate_windows(files, result=None):
        windows = {} if result is None else result["windows"]
        for seconds in ((.25, .5, 1.0) if args.short_windows else ()):
            n = round(seconds * 16000)
            rows = []
            for file in files:
                if file["index"] == 0:
                    continue
                x = read(Path(file["file"]))
                source_offset = 0.0
                if args.window_source == "matched_3s":
                    x, source_offset = three_seconds(x)
                for j in range(min(len(x) // n, args.max_windows)):
                    crop = x[j * n:(j + 1) * n]
                    row = {"file": Path(file["file"]).name, "speaker": file["speaker"],
                           "startSeconds": source_offset + j * seconds, "seconds": seconds,
                           "withinSelectedClipSeconds": j * seconds, "rmsDbfs": rms_dbfs(crop)}
                    try:
                        row["scores"] = score(crop)
                    except Exception as error:
                        row["error"] = type(error).__name__ + ":" + str(error)
                    rows.append(row)
            windows[str(seconds)] = {"summary": summary(rows),
                    "ownerVerification": owner_summary(rows, references), "rows": rows,
                    "sourceSelection": args.window_source,
                    "noncausalEvaluationSample": args.window_source == "matched_3s"}
            checkpoint_cache()
            if result is not None:
                checkpoint(result)
            print("window", seconds, json.dumps(windows[str(seconds)]["summary"]), flush=True)
        return windows

    if args.supplement_existing:
        result = json.loads(args.output.read_text())
        assert result.get("complete", True), "cannot supplement an incomplete run"
        assert result["model"]["sha256"] == sha(args.model)
        assert result["library"]["version"] == sherpa_onnx.__version__
        recorded_preprocessing = result["library"]["preprocessing"]
        if recorded_preprocessing == "official SDK model-metadata preprocessing":
            recorded_preprocessing = "sherpa_sdk"  # Earlier diagnostic schema.
        assert recorded_preprocessing == args.preprocessing
        if args.short_windows:
            result["shortWindowsComplete"] = False
            result["windows"] = {}
            calculate_windows(result["inputFiles"], result)
            result["shortWindowsComplete"] = True
        supplement(result)
        result["complete"] = True
        result["supplementTimingDiagnosticOnly"] = timings
        checkpoint(result)
        print("supplemented", args.output, flush=True)
        return

    files, full = [], []
    raw_embeddings = {}
    for speaker, names in source["speakers"].items():
        for index, name in enumerate(names):
            path = base / "speech" / name
            x = read(path)
            v = embed(x)
            raw_embeddings[name] = (speaker, v)
            files.append({"file": str(path), "sha256": sha(path), "speaker": speaker,
                          "seconds": len(x) / 16000, "index": index})
            full.append({"file": name, "speaker": speaker, "independentOfReference": index != 0,
                         "rmsDbfs": rms_dbfs(x),
                         "scores": {k: float(np.dot(v, r)) for k, r in references.items()}})
    pairwise = []
    names = list(raw_embeddings)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            who, a = raw_embeddings[left]
            other, b = raw_embeddings[right]
            pairwise.append({"left": left, "right": right, "sameSpeaker": who == other,
                             "cosine": float(np.dot(a, b))})

    windows = calculate_windows(files)

    # The existing diagnostic is six equal segments: A / B / A+B / A+2B / B / silence.
    # Its source utterances can be shorter than the requested four seconds.
    # Scores identify leakage; no threshold-based gating is simulated here.
    outputs = []
    segments = ("a_only", "b_only", "equal_overlap", "b_louder_overlap", "b_after_overlap", "silence")
    mixture_samples = len(read(base / "mix.wav"))
    assert mixture_samples % len(segments) == 0
    segment_samples = mixture_samples // len(segments)
    assert segment_samples > 8000
    references_metadata = [{"speaker": k, "file": str(base / f"reference_{k}.wav"),
                            "sha256": sha(base / f"reference_{k}.wav"), "seconds": 3}
                           for k in references]
    result = {"complete": False, "dateUtc": datetime.now(timezone.utc).isoformat(), "host": platform.platform(),
              "library": {"name": "sherpa-onnx", "version": sherpa_onnx.__version__, "threads": 1,
                          "api": "SpeakerEmbeddingExtractor" if reference_session is None else "kaldi-native-fbank + ONNX Runtime",
                          "preprocessing": args.preprocessing},
              "model": {"file": str(args.model), "sha256": sha(args.model), "bytes": args.model.stat().st_size,
                        "dimension": extractor.dim, "licenseCard": pinned["modelLicense"], "provenance": pinned},
              "protocol": {"microphone": False, "networkEgressDeniedByOs": args.require_egress_block,
                           "networkInferenceRequests": False, "threshold": None,
                           "windowSelection": "first consecutive complete non-overlapping windows, no silence removal or padding" if args.short_windows else "short windows not requested",
                           "outputSegmentSeconds": segment_samples / 16000,
                           "maxWindowsPerUtterancePerDuration": args.max_windows,
                           "caveat": "3 speakers, same corpus/channel; diagnostic only, no held-out production calibration"},
              "references": references_metadata, "inputFiles": files,
              "fullUtterances": {"summaryIndependent": summary([r for r in full if r["independentOfReference"]]),
                                 "ownerVerification": owner_summary([r for r in full if r["independentOfReference"]], references), "rows": full},
              "pairwiseIndependentUtterances": pairwise, "windows": windows, "voxlockOutputs": outputs,
              "timingDiagnosticOnlyNotAndroidBenchmark": timings}
    # Save complete earlier phases before touching fixture-specific output files.
    checkpoint(result)
    output_paths = sorted(base.glob("*-target-*.wav")) if args.short_windows else [base / "int8_full-target-5639.wav"]
    for path in output_paths:
        x = read(path)
        assert len(x) == mixture_samples, (str(path), len(x), mixture_samples)
        profile = path.stem.rsplit("-", 1)[1]
        output_sha256 = sha(path)
        for i, segment in enumerate(segments):
            if not args.short_windows and segment not in ("b_only", "equal_overlap", "b_after_overlap"):
                continue
            crop = x[i * segment_samples + 4000:(i + 1) * segment_samples - 4000]
            outputs.append({"file": path.name, "sha256": output_sha256, "profile": profile, "segment": segment,
                            "rmsDbfs": rms_dbfs(crop), "scores": score(crop)})
        checkpoint(result)
    supplement(result)
    result["complete"] = True
    checkpoint(result)
    print("full independent", json.dumps(result["fullUtterances"]["summaryIndependent"]), flush=True)
    for row in outputs:
        if row["profile"] == "5639" and row["file"].startswith("int8_full"):
            print("absent-C-output", json.dumps(row), flush=True)
    print("saved", args.output, flush=True)


if __name__ == "__main__":
    main()
