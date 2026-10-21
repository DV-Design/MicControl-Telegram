#!/usr/bin/env python3
"""Research-only official RNNoise 2025 full model on the unchanged 43 PCM inputs.

Requires existing Torch venv, clang and explicitly downloaded, pinned archives.
--phase smoke runs clean A/B and A/vacuum bursts; --phase complete appends the
remaining cases after review. No download, training, UI, Android or product edits.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PIN = "70f1d256acd4b34a572f999a05c87bf00b67730d"
SOURCE_SHA = "f61ee0b3f4c4cd337303e003d333357c5eaf25ef5d75a742109ee59e9a0a3932"
MODEL_SHA = "0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37"
INPUT_SHA = "c4bca5c8a8bf23b654dd96ca180660aaae3fe5f3f19a85c90e0c4ba198a48877"
MODEL_C_SHA = "d6021b7697677c4d2274c912975e143765552b0e6f25500aa660fdb4a9849be5"
MODEL_H_SHA = "09ff880bddd0fc74a2ae0e5ec6c8d65714031b08d0c3f672493acd9e189c5855"
SMOKE = {"clean_A", "clean_B", "bursts_A_vacuum_cleaner"}
DELAY_48K = 960  # Source: one-hop OLA + one explicit delayed_X hop; clean A checks it.
RESAMPLE = dict(lowpass_filter_width=64, rolloff=.9475937167399596,
                resampling_method="sinc_interp_kaiser", beta=14.769656459379492)
SOURCES = ["denoise", "rnn", "pitch", "kiss_fft", "celt_lpc", "nnet",
           "nnet_default", "parse_lpcnet_weights", "rnnoise_data", "rnnoise_tables"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def ignored(path):
    relative = Path(path).resolve().relative_to(ROOT)
    if subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=ROOT).returncode:
        raise ValueError(f"Research inputs, archives and outputs must stay Git-ignored: {relative}")


def build(args, out):
    source = out / "build/source"
    source.mkdir(parents=True)
    with tarfile.open(args.source_archive) as archive:
        for entry in archive:
            parts = Path(entry.name).parts[1:]
            if not parts:
                continue
            target = source.joinpath(*parts)
            if (not target.resolve().is_relative_to(source.resolve()) or
                    not (entry.isfile() or entry.isdir()) or entry.size > 1024 * 1024):
                raise ValueError("Unexpected pinned source archive member")
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(entry).read())
    with tarfile.open(args.model_archive) as archive:
        for name, expected in [("src/rnnoise_data.c", MODEL_C_SHA), ("src/rnnoise_data.h", MODEL_H_SHA)]:
            member = archive.getmember(name)
            if not member.isfile() or member.size > 80 * 1024 * 1024:
                raise ValueError("Unexpected full-model archive member")
            (source / name).write_bytes(archive.extractfile(member).read())
            if sha(source / name) != expected:
                raise ValueError("Pinned full-model C/header changed")
    if (source / "model_version").read_text().strip() != MODEL_SHA:
        raise ValueError("Source/model pairing changed")
    header = (source / "src/rnnoise_data.h").read_text()
    if any(f"#define GRU{i}_OUT_SIZE 384" not in header for i in (1, 2, 3)):
        raise ValueError("Expected the official full384 model, not little/default256 training configuration")
    harness = ROOT / "tests/miccontrol/rnnoise_current_pcm.c"
    binary = out / "build/rnnoise-current-pcm"
    command = [args.compiler, "-std=c99", "-O3", "-DRNNOISE_BUILD", "-DDISABLE_DEBUG_FLOAT",
               "-I" + str(source / "include"), "-I" + str(source / "src"), str(harness),
               *[str(source / f"src/{name}.c") for name in SOURCES], "-lm", "-o", str(binary)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (out / "build/build.log").write_text(process.stdout + process.stderr)
    if process.returncode:
        raise RuntimeError("Official RNNoise compilation failed; see build/build.log")
    compiled = [harness, *[source / f"src/{name}.c" for name in SOURCES],
                *sorted((source / "src").glob("*.h")), source / "include/rnnoise.h"]
    return {"path": str(binary), "sha256": sha(binary), "bytes": binary.stat().st_size,
            "command": command, "compiler": subprocess.check_output([args.compiler, "--version"], text=True),
            "host": {"system": platform.system(), "machine": platform.machine()},
            "compiledSources": {str(path): sha(path) for path in compiled},
            "sourceLicenseSha256": sha(source / "COPYING"), "outputFormat": "FloatS16 float32 PCM"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/qa/gtcrn/matrix-43/inputs.json")
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--model-archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--compiler", default="clang")
    parser.add_argument("--phase", choices=["smoke", "complete"], default="smoke")
    args = parser.parse_args()
    if sys.byteorder != "little" or not __debug__:
        parser.error("Use little-endian Python without -O")
    for name in ("manifest", "source_archive", "model_archive", "output_dir"):
        setattr(args, name, getattr(args, name).resolve())
        ignored(getattr(args, name))
    for path, expected in [(args.manifest, INPUT_SHA), (args.source_archive, SOURCE_SHA), (args.model_archive, MODEL_SHA)]:
        if sha(path) != expected:
            raise ValueError(f"Pinned input/archive changed: {path}")
    inputs = json.loads(args.manifest.read_text())
    if inputs["sampleRate"] != 16000 or len(inputs["cases"]) != 43:
        raise ValueError("Expected the unchanged common16k 43-case matrix")
    out = args.output_dir
    code_hashes = {"python": sha(__file__), "c": sha(ROOT / "tests/miccontrol/rnnoise_current_pcm.c")}
    if args.phase == "smoke":
        if out.exists() and any(out.iterdir()):
            raise ValueError("Use a new output directory; preserve previous evidence")
        out.mkdir(parents=True, exist_ok=True)
        binary = build(args, out)
        report = {"complete": False, "caseSelection": "smoke", "scope": "Host standalone official RNNoise2025 only; no Android/APM/UI",
                  "inputManifestSha256": INPUT_SHA, "sourceCommit": SOURCE_PIN,
                  "sourceArchive": {"url": f"https://codeload.github.com/xiph/rnnoise/tar.gz/{SOURCE_PIN}", "sha256": SOURCE_SHA},
                  "model": {"url": f"https://media.xiph.org/rnnoise/models/rnnoise_data-{MODEL_SHA}.tar.gz",
                            "sha256": MODEL_SHA, "archiveBytes": args.model_archive.stat().st_size,
                            "variant": "full384, C weights/default upstream integer DNN kernels"},
                  "binary": binary, "codeSha256": code_hashes,
                  "fixedDelay48kSamples": DELAY_48K, "cliOutputFormat": "Float32 PCM, no PCM16 quantization",
                  "outputNormalization": False, "additionalGainExponent": False, "vadGating": False,
                  "outputResample": {"sourceHz": 48000, "targetHz": 16000, **RESAMPLE},
                  "versions": {name: importlib.metadata.version(name) for name in ["numpy", "torch", "torchaudio"]},
                  "cases": []}
    else:
        report = json.loads((out / "manifest.json").read_text())
        if (not report["complete"] or report["caseSelection"] != "smoke" or
                report["codeSha256"] != code_hashes or report["inputManifestSha256"] != INPUT_SHA or
                {row["name"] for row in report["cases"]} != SMOKE or
                sha(report["binary"]["path"]) != report["binary"]["sha256"]):
            raise ValueError("Complete phase requires this exact finished smoke/binary/adapter")
        for row in report["cases"]:
            if sha(row["outputPath"]) != row["outputSha256"]:
                raise ValueError("Smoke PCM changed before complete phase")
        save(out / "manifest-smoke.json", report)
        report.update(complete=False, caseSelection="all43")
    import numpy as np
    import torch
    import torchaudio.functional as audio
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    (out / "raw48").mkdir(exist_ok=True)
    done = {row["name"] for row in report["cases"]}
    save(out / "manifest.json", report)
    for case in inputs["cases"]:
        name = case["name"]
        if name in done or args.phase == "smoke" and name not in SMOKE:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Unsafe case name")
        input16 = args.manifest.parent / (name + "-input16.f32")
        input48 = args.manifest.parent / (name + "-input48.f32")
        if sha(input16) != case["inputSha256"]:
            raise ValueError("Common input16 changed")
        samples = np.fromfile(input48, dtype="<f4")
        count = case["inputSamples16k"]
        if len(samples) != 3 * count or not np.isfinite(samples).all():
            raise ValueError("Invalid common FloatS16 input48")
        tail = DELAY_48K + (-len(samples)) % 480
        prepared = out / "raw48" / (name + "-padded.f32")
        np.pad(samples, (0, tail)).astype("<f4").tofile(prepared)
        raw_output = out / "raw48" / (name + "-output.f32")
        command = [report["binary"]["path"], str(prepared), str(raw_output)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (out / "raw48" / (name + ".log")).write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(f"Official RNNoise failed: {name}")
        native = json.loads(process.stdout)
        raw = np.fromfile(raw_output, dtype="<f4")
        if len(raw) != len(samples) + tail or not native["allFinite"] or not np.isfinite(raw).all():
            raise ValueError("Unexpected native FloatS16 output48")
        aligned = np.ascontiguousarray(raw[DELAY_48K:DELAY_48K+len(samples)] / 32768)
        result = audio.resample(torch.from_numpy(aligned), 48000, 16000, **RESAMPLE).numpy().astype(np.float32)
        if len(result) != count or not np.isfinite(result).all():
            raise ValueError("Unexpected normalized Float32 output16")
        target = out / (name + "-rnnoise2025.f32")
        result.astype("<f4").tofile(target)
        if name == "clean_A":
            reference = np.fromfile(input16, dtype="<f4").astype(np.float64)
            lags = range(-128, 129)
            scores = [float(np.dot(result[max(lag, 0):len(result)+min(lag, 0)].astype(np.float64),
                                   reference[max(-lag, 0):len(reference)-max(lag, 0)])) for lag in lags]
            lag = int(np.argmax(scores)) - 128
            report["cleanCalibration"] = {"afterFixedTrimLagSamples16k": lag,
                "scope": "one clean A cross-correlation only; no per-noise delay fitting"}
            if lag != 0:
                save(out / "manifest.json", report)
                raise ValueError(f"Source-predicted20ms delay disagrees with clean A: residual{lag} samples")
        report["cases"].append({"name": name, "kind": case["kind"],
            "input16Sha256": case["inputSha256"], "input48Sha256": sha(input48),
            "inputSamples16k": count, "commonInputScale": case["commonInputScale"],
            "paddedInput48Sha256": sha(prepared), "appendedZeroSamples48k": tail,
            "rawOutput48Sha256": sha(raw_output), "native": native, "command": command,
            "outputSamples16k": len(result), "outputPath": str(target), "outputSha256": sha(target),
            "allFinite": True, "maxAbs": float(np.max(np.abs(result)))})
        save(out / "manifest.json", report)
        print(json.dumps({"case": name, "completed": len(report["cases"]), "allFinite": True}), flush=True)
    if sha(args.manifest) != INPUT_SHA:
        raise ValueError("Input manifest changed during inference")
    report["complete"] = True
    save(out / "manifest.json", report)
    print("Official RNNoise2025 selected phase complete; independent common scoring is separate.", flush=True)


if __name__ == "__main__":
    main()
