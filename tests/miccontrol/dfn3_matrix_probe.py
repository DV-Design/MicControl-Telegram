#!/usr/bin/env python3
"""Research-only DFN3 inference on the exact existing 43-case GTCRN PCM matrix.

Run with .local/tse-baseline-venv/bin/python. No input preparation, normalization,
training, Android, UI, model export or product changes. Source/model/PCM stay ignored.
"""
import argparse
import configparser
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SHA256 = "c4bca5c8a8bf23b654dd96ca180660aaae3fe5f3f19a85c90e0c4ba198a48877"
MODEL_SHA256 = "c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616"
BINARY_SHA256 = "4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081"
MODEL_SOURCE = "https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/models/DeepFilterNet3_onnx.tar.gz"
BINARY_SOURCE = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-aarch64-apple-darwin"
RESAMPLE = dict(lowpass_filter_width=64, rolloff=.9475937167399596,
                resampling_method="sinc_interp_kaiser", beta=14.769656459379492)
DELAY_48K = 1440


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ignored(path):
    relative = Path(path).resolve().relative_to(ROOT)
    if subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=ROOT).returncode:
        raise ValueError(f"Research inputs, binaries and outputs must stay Git-ignored: {relative}")


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/qa/gtcrn/matrix-43/inputs.json")
    parser.add_argument("--binary", type=Path, default=ROOT / ".tmp/current/deep-filter-0.5.6-aarch64-apple-darwin")
    parser.add_argument("--model", type=Path, default=ROOT / ".tmp/current/deepfilternet-audit/models/DeepFilterNet3_onnx.tar.gz")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__ or sys.byteorder != "little":
        parser.error("Use little-endian host Python without -O")
    for path in [args.manifest, args.binary, args.model, args.output_dir]:
        ignored(path)
    for path, expected in [(args.manifest, MANIFEST_SHA256), (args.binary, BINARY_SHA256), (args.model, MODEL_SHA256)]:
        if sha(path) != expected:
            raise ValueError(f"Pinned research artifact changed: {path}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError("Use a new output directory; do not overwrite evidence")
    inputs = json.loads(args.manifest.read_text())
    if inputs["sampleRate"] != 16000 or len(inputs["cases"]) != 43:
        raise ValueError("Expected the unchanged common 16kHz 43-case matrix")
    with tarfile.open(args.model) as archive:
        configs = [item for item in archive.getmembers() if item.name.endswith("/config.ini")]
        if len(configs) != 1:
            raise ValueError("Expected one pinned DFN3 config")
        config = configparser.ConfigParser()
        config.read_string(archive.extractfile(configs[0]).read().decode())
    contract = {"sampleRate": config.getint("df", "sr"), "fftSize": config.getint("df", "fft_size"),
                "hopSize": config.getint("df", "hop_size"), "dfLookahead": config.getint("df", "df_lookahead"),
                "convLookahead": config.getint("deepfilternet", "conv_lookahead")}
    if contract != {"sampleRate": 48000, "fftSize": 960, "hopSize": 480, "dfLookahead": 2, "convLookahead": 2}:
        raise ValueError("DFN3 delay/streaming contract changed")
    version = subprocess.check_output([str(args.binary.resolve()), "--version"], text=True).strip()
    if version != "deep_filter 0.5.6":
        raise ValueError("Unexpected official CLI version")

    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.functional as audio
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    out = args.output_dir.resolve()
    for directory in [out, out / "input-wav", out / "official-output", out / "logs"]:
        directory.mkdir(parents=True, exist_ok=True)
    report = {"complete": False, "scope": "Host DFN3 PCM inference only; common scoring is separate, no Android/UI.",
              "inputManifest": str(args.manifest.resolve()), "inputManifestSha256": MANIFEST_SHA256,
              "binary": {"version": version, "url": BINARY_SOURCE, "sha256": BINARY_SHA256},
              "model": {"url": MODEL_SOURCE, "sha256": MODEL_SHA256, "bytes": args.model.stat().st_size},
              "modelContract": contract, "fixedDelay48kSamples": DELAY_48K,
              "inputPreparation": "Read existing <case>-input48.f32 FloatS16 / 32768; no new 16-to-48 interpolation.",
              "outputResample": {"sourceHz": 48000, "targetHz": 16000, **RESAMPLE},
              "versions": {name: importlib.metadata.version(name) for name in ["numpy", "soundfile", "torch", "torchaudio"]},
              "outputNormalization": False, "postfilter": False, "attenuationLimitDb": 100,
              "lsnrThresholdsDb": [-15, 35, 35], "cliOutputFormat": "PCM16 WAV (official writer)",
              "cases": []}
    save(out / "manifest.json", report)
    for index, case in enumerate(inputs["cases"], 1):
        name = case["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Unsafe case filename")
        input16 = args.manifest.parent / (name + "-input16.f32")
        input48 = args.manifest.parent / (name + "-input48.f32")
        if sha(input16) != case["inputSha256"]:
            raise ValueError(f"Changed common input16: {name}")
        count16 = case["inputSamples16k"]
        samples = np.fromfile(input48, dtype="<f4") / 32768
        if len(samples) != 3 * count16 or not np.isfinite(samples).all():
            raise ValueError(f"Invalid common input48: {name}")
        tail = DELAY_48K + (-len(samples)) % 480
        wav = out / "input-wav" / (name + ".wav")
        sf.write(wav, np.pad(samples, (0, tail)), 48000, subtype="FLOAT")
        command = [str(args.binary.resolve()), "-m", str(args.model.resolve()), "-D",
                   "-o", str(out / "official-output"), str(wav)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (out / "logs" / (name + ".log")).write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(f"Official DFN3 CLI failed: {name}; see its log")
        output_wav = out / "official-output" / wav.name
        values, rate = sf.read(output_wav, dtype="float32")
        if (rate != 48000 or values.ndim != 1 or len(values) != len(samples) + tail - DELAY_48K or
                not np.isfinite(values).all()):
            raise ValueError(f"Unexpected DFN3 output48: {name}")
        # -D has already removed exactly 1440 samples. Trim only the explicit terminal hop padding.
        values = values[:len(samples)]
        result = audio.resample(torch.from_numpy(np.ascontiguousarray(values)),
                                48000, 16000, **RESAMPLE).numpy().astype(np.float32)
        if len(result) != count16 or not np.isfinite(result).all():
            raise ValueError(f"Unexpected downsampled DFN3 output16: {name}")
        target = out / (name + "-dfn3.f32")
        result.astype("<f4").tofile(target)
        row = {"name": name, "kind": case["kind"], "input16Sha256": case["inputSha256"],
               "input48Sha256": sha(input48), "inputSamples16k": count16, "inputWavSha256": sha(wav),
               "inputWavSamples48k": len(samples) + tail, "appendedZeroSamples48k": tail,
               "commonInputScale": case["commonInputScale"], "command": command,
               "outputWavSha256": sha(output_wav), "outputSamples16k": len(result),
               "outputSha256": sha(target), "allFinite": True,
               "maxAbs": float(np.max(np.abs(result))), "outputPath": str(target)}
        report["cases"].append(row)
        save(out / "manifest.json", report)
        print(json.dumps({"case": name, "completed": index, "total": 43, "allFinite": True}), flush=True)
    if sha(args.manifest) != MANIFEST_SHA256:
        raise ValueError("Input manifest changed during inference")
    report["complete"] = True
    save(out / "manifest.json", report)
    print("DFN3 exact-input matrix complete: 43 outputs; ready for the independent common scorer.", flush=True)


if __name__ == "__main__":
    main()
