#!/usr/bin/env python3
"""Reproduce public TSE fixtures and Python goldens without downloading anything.

Requires NumPy, soundfile and onnxruntime 1.31.0 (the existing .local/tse-venv).
The pinned nine-file LibriSpeech test-clean corpus is CC BY4.0 / OpenSLR12.
Two held-out utterances form the mixture; three other utterances enroll A/B/C.
C is absent from the mixture. Remaining corpus clips are reserved controls.

Unlike the initial host quality benchmark's unquantized Float32 arrays, these
goldens intentionally reproduce its WAV PCM16 write/read roundtrip before LEf32
export. --inputs-only plus --check-against validates exact original input hashes
without loading a model or repeating inference. Default mode runs the reviewed
upstream Stream implementation, imported directly from its pinned core.py.
"""

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import time
import types


SOURCE_URL = "https://www.openslr.org/resources/12/test-clean.tar.gz"
SOURCE_PAGE = "https://www.openslr.org/12/"
VOXLOCK_COMMIT = "08ed37cbb79f449ca6b499bc23fb14138b207bfd"
CORE_SHA256 = "28049a0904482472a7892e1a357350d31418c3009fd2209f78007f73dc2afaca"
MODEL_SHA256 = {
    "enroll.onnx": "86645cba23f207def0b31a6e74a615d3b7a813b4fdf957c53b3af2905ba2ffd3",
    "chunk_int8_full.onnx": "7b57c1bfd5acd5b33768a9dff09d9af487d45374b3ba0b991e541ff121eaa337",
}
SPEAKERS = {
    "6930": ["6930-75918-0000.flac", "6930-75918-0007.flac", "6930-75918-0006.flac"],
    "1320": ["1320-122617-0003.flac", "1320-122617-0012.flac", "1320-122617-0026.flac"],
    "5639": ["5639-40744-0032.flac", "5639-40744-0002.flac", "5639-40744-0030.flac"],
}
SPEECH_SHA256 = {
    "6930-75918-0000.flac": "9ce35224156f071ab58eb7feb8a5ceae600f6f9f353da2a6cbf797b6b1ac8a23",
    "6930-75918-0007.flac": "059969de8f6b780e1a4982805e977c3e73e40d3759c8fa8cb0cb8fabd9eb5b27",
    "6930-75918-0006.flac": "4bed112ebfdba58ec061abd3fe013f89946863e9c51e8a83b50a5eb7afb9ce65",
    "1320-122617-0003.flac": "bbe9ef85bbe228c73a414f064c9bd992c94135d73f9900b33104ad93c07d0594",
    "1320-122617-0012.flac": "6b5cd2c31ee61665ea0d81f2c76a1f2c32cb4f46e5ec5861bd9157e262785252",
    "1320-122617-0026.flac": "8e46137d386c181c23a97932fb560a1fffa0b8e635bfe38c81c6f0791dbbe9ed",
    "5639-40744-0032.flac": "ecba1c65406f3d2fdfe383a22385dfe19cc117b71b126817f5e20df791f22a50",
    "5639-40744-0002.flac": "111c6b8b19d093736570bced344035b48f75c770aacc60103da9d9a20f904fb2",
    "5639-40744-0030.flac": "c7f95b2f012ab8f4629d15c8c78e78bf17b3445c96e5a9b0c525b0743e50d9c5",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path, expected):
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Missing or changed pinned input: {path}")


def file_record(path):
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech-dir", type=Path, default=root / "artifacts/qa/target-voice/speech")
    parser.add_argument("--voxlock-source", type=Path, default=root / ".tmp/current/voxlock")
    parser.add_argument("--model-dir", type=Path, required=True,
                        help="existing directory with the exact pinned enroll/int8-full models")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inputs-only", action="store_true", help="generate four input files; no model inference")
    parser.add_argument("--check-against", type=Path,
                        help="original golden manifest; fail on differing input/output SHA256")
    args = parser.parse_args()
    if args.check_against and args.out.resolve() == args.check_against.resolve().parent:
        parser.error("Use a separate output directory to preserve the original goldens")
    core_path = args.voxlock_source / "voxlock/core.py"
    revision = subprocess.run(["git", "-C", str(args.voxlock_source), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    if revision != VOXLOCK_COMMIT:
        parser.error(f"VoxLock source must remain at {VOXLOCK_COMMIT}")
    require_hash(core_path, CORE_SHA256)
    for filename, digest in SPEECH_SHA256.items():
        require_hash(args.speech_dir / filename, digest)
    for filename, digest in MODEL_SHA256.items():
        require_hash(args.model_dir / filename, digest)
    # Import the reviewed single upstream module, without executing package init
    # or installing/downloading its package or model dependencies.
    import numpy as np
    import soundfile as sf
    import onnxruntime as ort
    if ort.__version__ != "1.31.0":
        parser.error("Use the pinned onnxruntime 1.31.0 Python environment")
    ort.disable_telemetry_events()
    spec = importlib.util.spec_from_file_location("danygramm_reviewed_voxlock_core", core_path)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    frames = {}
    for identity, filenames in SPEAKERS.items():
        frames[identity] = []
        for filename in filenames:
            samples, sample_rate = sf.read(args.speech_dir / filename, dtype="float32")
            if sample_rate != 16000 or samples.ndim != 1 or not np.isfinite(samples).all():
                raise ValueError(f"Expected finite mono 16kHz LibriSpeech: {filename}")
            frames[identity].append(samples)

    def normalize(samples):
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64))) + 1e-14))
        return (samples * (.06 / max(rms, 1e-8))).astype(np.float32)

    def pcm16_roundtrip(samples):
        with io.BytesIO() as memory:
            sf.write(memory, samples, 16000, format="WAV", subtype="PCM_16")
            memory.seek(0)
            result, sample_rate = sf.read(memory, dtype="float32")
        if sample_rate != 16000:
            raise ValueError("PCM16 roundtrip changed the sample rate")
        return result

    references = {identity: normalize(core.loud_sample(clips[0], sec=3.0, within=30))
                  for identity, clips in frames.items()}
    a = normalize(core.loud_sample(frames["6930"][1], sec=4.0, within=30))
    b = normalize(core.loud_sample(frames["1320"][1], sec=4.0, within=30))
    count = min(len(a), len(b), 64000)
    a, b = a[:count], b[:count]
    silence = np.zeros(count, np.float32)
    source_a = np.concatenate((a, silence, a, a, silence, silence))
    source_b = np.concatenate((silence, b, b, 2 * b, b, silence))
    mixture = source_a + source_b
    mixture *= min(1., .85 / max(float(np.max(np.abs(mixture))), 1e-5))
    mixture = pcm16_roundtrip(mixture)
    mixture = np.pad(mixture, (0, (-len(mixture)) % 640))
    references = {identity: pcm16_roundtrip(samples) for identity, samples in references.items()}
    if any(len(samples) != 48000 for samples in references.values()):
        raise ValueError("Enrollment must contain exactly 48000 samples")
    args.out.mkdir(parents=True, exist_ok=True)
    files = []

    def write(name, samples):
        path = args.out / name
        samples.astype("<f4").tofile(path)
        record = file_record(path)
        files.append(record)
        return path

    mixture_path = write("mix.f32", mixture)
    reference_paths = {identity: write(f"reference-{identity}.f32", samples)
                       for identity, samples in references.items()}
    baseline = {}
    if args.check_against:
        baseline = {Path(row["path"]).name: row for row in json.loads(args.check_against.read_text())["files"]}

    def check_files():
        for row in files:
            name = Path(row["path"]).name
            if args.check_against and (name not in baseline or row["sha256"] != baseline[name]["sha256"]):
                raise ValueError(f"Golden SHA256 mismatch: {name}")

    # Fail before expensive inference if the rebuilt Float32 inputs differ.
    check_files()
    models = {"enroll": str((args.model_dir / "enroll.onnx").resolve()),
              "chunk": str((args.model_dir / "chunk_int8_full.onnx").resolve())}
    report = {"sampleRate": 16000, "chunkSamples": 640, "dtype": "little-endian-float32",
              "models": models, "input": str(mixture_path.resolve()), "samples": len(mixture),
              "cases": [], "provenance": {
                  "sourceUrl": SOURCE_URL, "sourcePage": SOURCE_PAGE, "sourceLicense": "CC-BY-4.0",
                  "voxlockCommit": VOXLOCK_COMMIT, "coreSha256": CORE_SHA256,
                  "models": [file_record(args.model_dir / name) for name in MODEL_SHA256],
                  "speech": [file_record(args.speech_dir / name) for name in SPEECH_SHA256],
                  "numpy": np.__version__, "soundfile": sf.__version__, "onnxruntime": ort.__version__,
                  "threads": 4, "rmsBeforeQuantization": .06, "profileSeconds": 3,
                  "inputPrecision": "PCM16 WAV roundtrip then Float32; initial host quality arrays were unquantized",
                  "mixtureSegments": ["A", "B", "A+B", "A+2B", "B", "silence"],
                  "inputsOnly": args.inputs_only,
              }}
    if not args.inputs_only:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        enroll = ort.InferenceSession(models["enroll"], options, providers=["CPUExecutionProvider"])
        chunk = ort.InferenceSession(models["chunk"], options, providers=["CPUExecutionProvider"])
        report["metadata"] = {"inputs": [(x.name, x.shape, x.type) for x in chunk.get_inputs()],
                              "outputs": [(x.name, x.shape, x.type) for x in chunk.get_outputs()]}
        for identity, reference in references.items():
            stream = core.Stream(types.SimpleNamespace(enroll=enroll, chunk=chunk), reference)
            parts, produced = [], []
            start = time.perf_counter()
            for offset in range(0, len(mixture), 640):
                output = stream.push(mixture[offset:offset + 640])
                parts.append(output)
                produced.append(len(output))
            tail = stream.flush()
            parts.append(tail)
            output = np.concatenate(parts)[:len(mixture)]
            if (len(output) != len(mixture) or not np.isfinite(output).all() or
                    produced[0] != 256 or set(produced[1:]) != {640}):
                raise ValueError("Unexpected upstream stream output contract")
            expected_path = write(f"expected-{identity}.f32", output)
            report["cases"].append({"speaker": identity,
                                    "reference": str(reference_paths[identity].resolve()),
                                    "expected": str(expected_path.resolve()),
                                    "magnitudeShape": list(stream.mag.shape), "contextShape": list(stream.ctx.shape),
                                    "firstPushSamples": produced[0], "subsequentPushSamples": sorted(set(produced[1:])),
                                    "pythonFlushSamplesBeforeTrimming": len(tail),
                                    "seconds": time.perf_counter() - start})
            check_files()
    report["files"] = sorted(files, key=lambda row: row["path"])
    manifest = args.out / ("inputs-manifest.json" if args.inputs_only else "manifest.json")
    manifest.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {len(files)} pinned fixture files: {manifest}")
    if args.check_against:
        print("All generated Float32 SHA256 values match the original manifest.")


if __name__ == "__main__":
    main()
