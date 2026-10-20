#!/usr/bin/env python3
"""Build the isolated native TSE probe for Android arm64/API24; never uses adb.

Requires the existing NDK27.2 and the official, locally downloaded ORT1.31 AAR.
No product Gradle/CMake configuration or app files are changed.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import zipfile


ORT_AAR_SHA256 = "72683787a80d0608a3121b967d8e1239aef48286826661c953211626690540a7"
ORT_LIB_SHA256 = "8005a741e57117b4d7b476417706c0e9af13cf1b89db47e60f0cbc56e1af91e0"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_elf(path):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError(f"Expected little-endian ELF64: {path}")
    if struct.unpack_from("<H", data, 18)[0] != 183:
        raise ValueError(f"Expected AArch64: {path}")
    offset = struct.unpack_from("<Q", data, 32)[0]
    stride, count = struct.unpack_from("<HH", data, 54)
    loads = []
    for index in range(count):
        kind, _, file_offset, vaddr, _, _, _, align = struct.unpack_from(
            "<IIQQQQQQ", data, offset + index * stride)
        if kind == 1:
            loads.append({"offset": file_offset, "vaddr": vaddr, "align": align})
    if not loads or any(row["align"] < 16384 or
                        row["offset"] % 16384 != row["vaddr"] % 16384 for row in loads):
        raise ValueError(f"ELF LOAD segments are not 16KiB compatible: {path}")
    return {"machine": "AArch64", "load_segments": loads}


def main():
    root = Path(__file__).resolve().parents[2]
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT", str(Path.home() / "Library/Android/sdk")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path,
                        default=Path(os.environ.get("ANDROID_NDK_HOME", str(sdk / "ndk/27.2.12479018"))))
    parser.add_argument("--ort-aar", type=Path, default=root / ".tmp/current/tse-runtimes/onnxruntime-android-1.31.0.aar")
    parser.add_argument("--output-dir", type=Path, default=root / ".tmp/current/target-voice-android")
    args = parser.parse_args()
    source = root / "TMessagesProj/jni/voip/miccontrol/TargetVoiceInference.cpp"
    cli = root / "tests/miccontrol/target_voice_probe.cpp"
    for path in (source, cli, args.ort_aar, args.ndk / "source.properties"):
        if not path.is_file():
            parser.error(f"Missing input: {path}")
    if "Pkg.Revision = 27.2.12479018" not in (args.ndk / "source.properties").read_text():
        parser.error("Use the pinned Android NDK27.2.12479018")
    if sha256(args.ort_aar) != ORT_AAR_SHA256:
        parser.error("ORT AAR SHA256 does not match the inspected official1.31.0 artifact")
    toolchains = sorted((args.ndk / "toolchains/llvm/prebuilt").glob("*/bin/aarch64-linux-android24-clang++"))
    if len(toolchains) != 1:
        parser.error("Expected exactly one NDK host toolchain")
    compiler = toolchains[0]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runtime = args.output_dir / "runtime"
    with zipfile.ZipFile(args.ort_aar) as archive:
        names = [name for name in archive.namelist()
                 if name.startswith("headers/") and name.endswith((".h", ".inc"))]
        names.append("jni/arm64-v8a/libonnxruntime.so")
        for name in names:
            # Paths come from a pinned archive; still reject traversal before writing.
            parts = Path(name).parts
            if Path(name).is_absolute() or ".." in parts:
                parser.error("Unsafe path in ORT AAR")
            destination = runtime / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    library = runtime / "jni/arm64-v8a/libonnxruntime.so"
    if sha256(library) != ORT_LIB_SHA256:
        parser.error("Extracted ORT arm64 library SHA256 mismatch")
    executable = args.output_dir / "target_voice_probe"
    command = [
        str(compiler), "-std=c++17", "-O2", "-DNDEBUG", "-Wall", "-Wextra", "-Werror",
        "-fPIE", "-pie", "-static-libstdc++", "-pthread",
        f"-I{runtime / 'headers'}", f"-I{source.parent}", str(source), str(cli),
        f"-L{library.parent}", "-lonnxruntime", "-llog", "-landroid", "-ldl", "-lm",
        "-Wl,-z,max-page-size=16384", "-Wl,-z,common-page-size=16384",
        "-Wl,-z,relro,-z,now,-z,noexecstack", "-Wl,--no-undefined",
        "-Wl,-rpath,$ORIGIN", "-o", str(executable),
    ]
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)
    library_destination = args.output_dir / "libonnxruntime.so"
    library_destination.write_bytes(library.read_bytes())
    report = {
        "abi": "arm64-v8a", "android_api": 24, "ndk": "27.2.12479018",
        "ort_version": "1.31.0", "ort_aar_sha256": ORT_AAR_SHA256,
        "command": command,
        "inputs": [{"path": str(path.relative_to(root)), "sha256": sha256(path)}
                   for path in (source, source.with_suffix(".h"), cli)],
        "files": [{"path": str(path), "bytes": path.stat().st_size,
                   "sha256": sha256(path), "elf": inspect_elf(path)}
                  for path in (executable, library_destination)],
    }
    (args.output_dir / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Built Android probe: {executable}; no Android execution performed.")


if __name__ == "__main__":
    main()
