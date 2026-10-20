#!/usr/bin/env python3
"""Deploy/run the isolated native probe on emulator-5554 after explicit --execute.

Use public golden LE Float32/16kHz fixtures only. No app data, account, network,
permissions, APK, or Gradle operations occur. Device writes stay under the fixed
/data/local/tmp/danygramm-tse directory. Without --execute only local validation
and the planned commands run; adb is never invoked.
"""

import argparse
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys


REMOTE = "/data/local/tmp/danygramm-tse"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_f32(path):
    data = path.read_bytes()
    if not data or len(data) % 4:
        raise ValueError(f"Expected nonempty Float32 file: {path}")
    samples = array("f")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    if any(not math.isfinite(value) for value in samples):
        raise ValueError(f"Nonfinite Float32 data: {path}")
    return samples


def compare(actual, expected):
    if len(actual) != len(expected):
        raise ValueError(f"Sample count mismatch: {len(actual)} != {len(expected)}")
    squared_error = math.fsum((a - b) ** 2 for a, b in zip(actual, expected))
    actual_energy = math.fsum(value * value for value in actual)
    expected_energy = math.fsum(value * value for value in expected)
    denominator = math.sqrt(actual_energy * expected_energy)
    return {
        "samples": len(actual),
        "max_abs_diff": max(abs(a - b) for a, b in zip(actual, expected)),
        "rmse": math.sqrt(squared_error / len(actual)),
        "relative_l2_error": math.sqrt(squared_error / expected_energy) if expected_energy else None,
        "cosine_similarity": (math.fsum(a * b for a, b in zip(actual, expected)) / denominator
                              if denominator else None),
    }


def main():
    root = Path(__file__).resolve().parents[2]
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", str(Path.home() / "Library/Android/sdk")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-dir", type=Path, default=root / ".tmp/current/target-voice-android")
    parser.add_argument("--enroll-model", type=Path, required=True)
    parser.add_argument("--chunk-model", type=Path, required=True)
    parser.add_argument("--mixture", type=Path, required=True)
    parser.add_argument("--golden-manifest", type=Path,
                        help="verify the root-generated fixture SHA256 manifest before execution")
    parser.add_argument("--case", action="append", nargs=3, metavar=("NAME", "PROFILE", "EXPECTED"), required=True,
                        help="repeat per speaker; profile exactly 48000 samples; expected has mixture length")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--reset-check", action="store_true")
    parser.add_argument("--max-rmse", type=float,
                        help="optional explicit reference tolerance; metrics are always recorded")
    parser.add_argument("--output-dir", type=Path, default=root / "artifacts/qa/target-voice/android")
    parser.add_argument("--adb", type=Path, default=sdk / "platform-tools/adb")
    parser.add_argument("--execute", action="store_true", help="perform adb operations after root approves the run")
    args = parser.parse_args()
    if not 1 <= args.threads <= 4:
        parser.error("Use 1..4 threads for this prototype")
    if args.max_rmse is not None and (not math.isfinite(args.max_rmse) or args.max_rmse < 0):
        parser.error("--max-rmse must be finite and nonnegative")
    if args.golden_manifest:
        golden = json.loads(args.golden_manifest.read_text())
        for row in golden["files"]:
            path = Path(row["path"])
            if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
                parser.error(f"Golden fixture changed: {path}")
    probe = args.probe_dir / "target_voice_probe"
    library = args.probe_dir / "libonnxruntime.so"
    build_report = json.loads((args.probe_dir / "build.json").read_text())
    for row in build_report["files"]:
        path = args.probe_dir / Path(row["path"]).name
        if sha256(path) != row["sha256"]:
            parser.error(f"Build output changed since its ELF inspection: {path}")
    mixture = read_f32(args.mixture)
    if max(abs(value) for value in mixture) > 1:
        parser.error("Mixture must be normalized to [-1,1]")
    cases = []
    for name, profile_path, expected_path in args.case:
        profile_path, expected_path = Path(profile_path), Path(expected_path)
        profile, expected = read_f32(profile_path), read_f32(expected_path)
        if len(profile) != 48000 or max(abs(value) for value in profile) > 1:
            parser.error(f"Profile must contain 48000 normalized samples: {name}")
        if len(expected) != len(mixture):
            parser.error(f"Expected output length differs from mixture: {name}")
        cases.append({"name": name, "profile": profile_path, "expected": expected_path})
    if args.golden_manifest:
        golden_paths = {Path(row["path"]).resolve() for row in golden["files"]}
        used_fixtures = [args.mixture] + [case[key] for case in cases for key in ("profile", "expected")]
        if any(path.resolve() not in golden_paths for path in used_fixtures):
            parser.error("Every selected fixture must belong to the verified golden manifest")
    payload = [(probe, "target_voice_probe"), (library, "libonnxruntime.so"),
               (args.enroll_model, "enroll.onnx"), (args.chunk_model, "chunk.onnx"),
               (args.mixture, "mix.f32")]
    payload += [(case["profile"], f"profile-{index}.f32") for index, case in enumerate(cases)]
    # Validate/model provenance before contacting the device; never log model contents.
    inputs = [{"path": str(path), "sha256": sha256(path), "remote_name": name}
              for path, name in payload]
    adb_prefix = [str(args.adb), "-s", "emulator-5554"]

    def adb(arguments, timeout=180):
        command = adb_prefix + arguments
        print(shlex.join(command), flush=True)
        if args.execute:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            result.check_returncode()
            return result.stdout
        return ""

    def shell(arguments, timeout=180):
        return adb(["shell", shlex.join(arguments)], timeout)

    device = {}
    for key, command in (("abi", ["getprop", "ro.product.cpu.abi"]),
                         ("sdk", ["getprop", "ro.build.version.sdk"]),
                         ("page_size", ["getconf", "PAGESIZE"])):
        value = shell(command).strip()
        if args.execute:
            device[key] = value
    if args.execute and (device["abi"] != "arm64-v8a" or
                         int(device["sdk"]) < 24 or device["page_size"] != "16384"):
        parser.error(f"Expected arm64 Android API24+ with 16KiB pages, got {device}")
    shell(["mkdir", "-p", REMOTE])
    for path, name in payload:
        adb(["push", str(path), f"{REMOTE}/{name}"])
    shell(["chmod", "700", f"{REMOTE}/target_voice_probe"])
    if args.execute:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"device": device, "threads": args.threads, "chunk_ms": 40,
              "build": build_report, "inputs": inputs, "cases": [], "pairwise": []}
    if args.golden_manifest:
        report["golden_manifest"] = {"path": str(args.golden_manifest),
                                     "sha256": sha256(args.golden_manifest)}
    outputs = []
    for index, case in enumerate(cases):
        command = ["env", f"LD_LIBRARY_PATH={REMOTE}", f"{REMOTE}/target_voice_probe",
                   "--enroll-model", f"{REMOTE}/enroll.onnx", "--chunk-model", f"{REMOTE}/chunk.onnx",
                   "--profile", f"{REMOTE}/profile-{index}.f32", "--mixture", f"{REMOTE}/mix.f32",
                   "--output", f"{REMOTE}/output-{index}.f32", "--threads", str(args.threads)]
        if args.reset_check:
            command.append("--reset-check")
        raw = shell(command, timeout=600)
        destination = args.output_dir / f"output-{index}.f32"
        adb(["pull", f"{REMOTE}/output-{index}.f32", str(destination)])
        if not args.execute:
            continue
        (args.output_dir / f"probe-{index}.json").write_text(raw)
        metrics = json.loads(raw)
        required = {"runtime_version": "1.31.0", "sample_rate": 16000,
                    "profile_samples": 48000, "input_samples": len(mixture),
                    "output_samples": len(mixture), "threads": args.threads,
                    "magnitude_shape": [1, 257, 376], "context_shape": [1, 512, 298],
                    "first_output_count": 256}
        for name, expected_value in required.items():
            if metrics.get(name) != expected_value:
                raise ValueError(f"Native contract mismatch {case['name']}: {name}")
        for name in ("rtf", "p50_ms", "p95_ms", "p99_ms", "max_ms", "peak_rss_kib"):
            value = metrics.get(name)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Missing/invalid native measurement: {name}")
        output = read_f32(destination)
        parity = compare(output, read_f32(case["expected"]))
        outputs.append(output)
        report["cases"].append({"name": case["name"], "metrics": metrics,
                                "expected_path": str(case["expected"]),
                                "expected_sha256": sha256(case["expected"]),
                                "output_sha256": sha256(destination), "parity": parity})
    if not args.execute:
        print("Dry run complete; adb was not invoked. Use --execute only after root GO.")
        return
    for left in range(len(outputs)):
        for right in range(left + 1, len(outputs)):
            report["pairwise"].append({"left": cases[left]["name"], "right": cases[right]["name"],
                                       **compare(outputs[left], outputs[right])})
    (args.output_dir / "result.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"cases": report["cases"], "pairwise": report["pairwise"]}, indent=2))
    if args.max_rmse is not None and any(case["parity"]["rmse"] > args.max_rmse for case in report["cases"]):
        raise SystemExit("Reference RMSE tolerance exceeded; see result.json")


if __name__ == "__main__":
    main()
