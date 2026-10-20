#!/usr/bin/env python3
"""Build/sign the separate permission-free voice speed diagnostic. No adb/publish.

Reuses the pinned NDK/ORT inspection helpers. Generated models, fixtures and .so
files live under this project's ignored build/; its QA key stays in .local/.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(__file__).resolve().parent
MODEL_HASHES = {
    "enroll.onnx": "86645cba23f207def0b31a6e74a615d3b7a813b4fdf957c53b3af2905ba2ffd3",
    "chunk_int8_full.onnx": "7b57c1bfd5acd5b33768a9dff09d9af487d45374b3ba0b991e541ff121eaa337",
}
INPUT_HASHES = {
    "mix.f32": "2f1b768ced4f46bfbea3f428cbf1592e3bdc621e08a5857ae041700437663e8c",
    "reference-6930.f32": "b6ed68a64da99051dd8bd2a689890b01247676b916a2ce448317fe48e4721022",
}
NOTICE_HASHES = {
    "LICENSE": "2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c",
    "ThirdPartyNotices.txt": "143764b952fdb1a7c69ce653bfba74a7744d6a8a573bfb73e235fba356c83de3",
}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def require_hash(path, expected):
    if not path.is_file() or sha(path) != expected:
        raise ValueError(f"Missing/changed pinned input: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=Path.home() / "Library/Android/sdk")
    parser.add_argument("--java-home", type=Path, default=Path("/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"))
    parser.add_argument("--models", type=Path, default=ROOT / ".local/target-voice/voxlock-a50f4e1d/onnx")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "artifacts/qa/target-voice/golden")
    parser.add_argument("--allow-tool-downloads", action="store_true",
                        help="Allow Gradle to fetch missing pinned Android build/lint tooling")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("probe_android_build", ROOT / "tests/miccontrol/build_target_voice_android.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    ndk = args.sdk / "ndk/27.2.12479018"
    if "Pkg.Revision = 27.2.12479018" not in (ndk / "source.properties").read_text():
        parser.error("Expected pinned NDK27.2.12479018")
    compilers = list((ndk / "toolchains/llvm/prebuilt").glob("*/bin/aarch64-linux-android24-clang++"))
    if len(compilers) != 1: parser.error("Expected one NDK host toolchain")
    aar = ROOT / ".tmp/current/tse-runtimes/onnxruntime-android-1.31.0.aar"
    require_hash(aar, helpers.ORT_AAR_SHA256)
    generated = PROJECT / "build/generated/probe"
    assets = generated / "assets"
    libs = generated / "jniLibs/arm64-v8a"
    runtime = PROJECT / "build/ort"
    assets.mkdir(parents=True, exist_ok=True)
    libs.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(aar) as archive:
        names = [n for n in archive.namelist() if n.startswith("headers/") and n.endswith((".h", ".inc"))]
        names.append("jni/arm64-v8a/libonnxruntime.so")
        for name in names:
            if Path(name).is_absolute() or ".." in Path(name).parts: raise ValueError("Unsafe archive path")
            destination = runtime / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    ort = runtime / "jni/arm64-v8a/libonnxruntime.so"
    require_hash(ort, helpers.ORT_LIB_SHA256)
    shutil.copyfile(ort, libs / "libonnxruntime.so")
    for name, expected in MODEL_HASHES.items():
        require_hash(args.models / name, expected)
        shutil.copyfile(args.models / name, assets / name)
    for name, expected in INPUT_HASHES.items(): require_hash(args.fixtures / name, expected)
    (assets / "mix-4s.f32").write_bytes((args.fixtures / "mix.f32").read_bytes()[:64000 * 4])
    shutil.copyfile(args.fixtures / "reference-6930.f32", assets / "reference-a.f32")
    for name, count in (("mix-4s.f32", 64000), ("reference-a.f32", 48000)):
        data = (assets / name).read_bytes()
        if len(data) != count * 4 or not all(math.isfinite(x[0]) and abs(x[0]) <= 1 for x in struct.iter_unpack("<f", data)):
            raise ValueError("Invalid normalized Float32 fixture")
    engine = ROOT / "TMessagesProj/jni/voip/miccontrol/TargetVoiceInference.cpp"
    header = engine.with_suffix(".h")
    wrapper = PROJECT / "src/main/cpp/voice_probe_jni.cpp"
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in (engine, header, wrapper)}
    engine_sha = sha(engine)
    app_sources = {str(p.relative_to(ROOT)): sha(p) for p in (PROJECT / "src").rglob("*") if p.is_file()}
    command = [str(compilers[0]), "-std=c++17", "-O2", "-DNDEBUG", "-Wall", "-Wextra", "-Werror",
               "-fPIC", "-shared", "-static-libstdc++", "-pthread", f'-DVOICE_PROBE_ENGINE_SHA256="{engine_sha}"',
               f"-I{runtime / 'headers'}", f"-I{engine.parent}", str(engine), str(wrapper),
               f"-L{ort.parent}", "-lonnxruntime", "-llog", "-landroid", "-ldl", "-lm",
               "-Wl,-z,max-page-size=16384", "-Wl,-z,common-page-size=16384",
               "-Wl,-z,relro,-z,now,-z,noexecstack", "-Wl,--no-undefined", "-Wl,-soname,libvoiceprobe.so",
               "-o", str(libs / "libvoiceprobe.so")]
    subprocess.run(command, check=True)
    for relative, digest in source_hashes.items(): require_hash(ROOT / relative, digest)
    elf = {p.name: helpers.inspect_elf(p) for p in libs.glob("*.so")}
    license_dir = assets / "licenses"
    license_dir.mkdir(exist_ok=True)
    notices = {
        "VoxLock-LICENSE.txt": args.models.parent / "LICENSE",
        "VoxLock-NOTICE.txt": ROOT / ".tmp/current/voxlock/NOTICE",
        "TargetVoice-NOTICE.txt": engine.parent / "NOTICE.target-voice",
        "LibriSpeech-LICENSE.txt": ROOT / "artifacts/qa/target-voice/speech/LICENSE.TXT",
    }
    for destination, source in notices.items(): shutil.copyfile(source, license_dir / destination)
    ort_notices = ROOT / ".tmp/current/tse-runtimes/onnxruntime-android-1.31.0"
    for name, digest in NOTICE_HASHES.items():
        require_hash(ort_notices / name, digest)
        shutil.copyfile(ort_notices / name, license_dir / ("ORT-" + name))
    (license_dir / "DIAGNOSTIC-NOTICE.txt").write_text(
        "Danygramm voice speed diagnostic\n\n"
        "Contains VoxLock models enroll.onnx/chunk_int8_full.onnx at revision\n"
        "a50f4e1d109301d4b6f61dec57ebb1a61e7d8f03 and ONNX Runtime1.31.0.\n"
        "Weights licensing has the upstream discrepancy documented in TargetVoice-NOTICE.txt;\n"
        "this is a local diagnostic build, held for review before any distribution.\n\n"
        "Public speech source: LibriSpeech test-clean, OpenSLR12, CC BY4.0,\n"
        "Copyright2014 Vassil Panayotov. https://www.openslr.org/12/\n"
        "https://creativecommons.org/licenses/by/4.0/\n"
        "Changes: voice-reference selection, RMS scaling, PCM16 roundtrip, LEFloat32 export,\n"
        "mixed independent utterances6930-75918-0007/1320-122617-0012 cropped to4seconds;\n"
        "enrollment6930-75918-0000 selected to3seconds. No Krisp/AMI demo recording included.\n"
        "No microphone capture, accounts, network permission or live-call integration.\n")
    asset_records = [{"name": name, "bytes": (assets / name).stat().st_size, "sha256": sha(assets / name)}
                     for name in (*MODEL_HASHES, "mix-4s.f32", "reference-a.f32")]
    provenance = {"model_revision": "a50f4e1d109301d4b6f61dec57ebb1a61e7d8f03", "engine_sources": source_hashes,
                  "ort_aar_sha256": helpers.ORT_AAR_SHA256, "ort_library_sha256": helpers.ORT_LIB_SHA256,
                  "assets": {row["name"]: row["sha256"] for row in asset_records}}
    (assets / "probe-manifest.json").write_text(json.dumps({"assets": asset_records, "provenance": provenance}, indent=2) + "\n")
    # This key is intentionally independent from the messenger/release keystore.
    key_dir = ROOT / ".local/voice-probe"
    key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    password_file = key_dir / "password.txt"
    if not password_file.exists():
        fd = os.open(password_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as output: output.write(secrets.token_urlsafe(32))
    os.chmod(password_file, 0o600)
    key = key_dir / "voice-probe.p12"
    env = dict(os.environ)
    env.update({"JAVA_HOME": str(args.java_home), "ANDROID_HOME": str(args.sdk), "ANDROID_SDK_ROOT": str(args.sdk),
                "VOICE_PROBE_KEYSTORE": str(key), "VOICE_PROBE_KEY_PASSWORD": password_file.read_text().strip()})
    if not key.exists():
        subprocess.run([str(args.java_home / "bin/keytool"), "-genkeypair", "-keystore", str(key),
                        "-storetype", "PKCS12", "-alias", "voice-probe", "-storepass:env", "VOICE_PROBE_KEY_PASSWORD",
                        "-keypass:env", "VOICE_PROBE_KEY_PASSWORD", "-keyalg", "RSA", "-keysize", "3072",
                        "-validity", "3650", "-dname", "CN=Danygramm Voice Probe QA", "-noprompt"], env=env, check=True)
        os.chmod(key, 0o600)
    subprocess.run([str(ROOT / "gradlew"), *([] if args.allow_tool_downloads else ["--offline"]),
                    "--no-daemon", "--max-workers=2", "-p", str(PROJECT), "assembleRelease"],
                   cwd=ROOT, env=env, check=True)
    for relative, digest in {**source_hashes, **app_sources}.items(): require_hash(ROOT / relative, digest)
    built = PROJECT / "build/outputs/apk/release/voice-probe-release.apk"
    if not built.is_file():
        candidates = list((PROJECT / "build/outputs/apk/release").glob("*-release.apk"))
        if len(candidates) != 1: raise ValueError("Expected exactly one signed release APK")
        built = candidates[0]
    output = ROOT / "artifacts/Danygramm-Voice-Test.apk"
    output.parent.mkdir(exist_ok=True)
    shutil.copyfile(built, output)
    build_tools = args.sdk / "build-tools/36.0.0"
    verification = subprocess.run([str(build_tools / "apksigner"), "verify", "--verbose", "--print-certs", str(output)],
                                  env=env, check=True, text=True, capture_output=True).stdout
    subprocess.run([str(build_tools / "zipalign"), "-c", "-P", "16", "4", str(output)], env=env, check=True)
    permissions = subprocess.run([str(build_tools / "aapt2"), "dump", "permissions", str(output)],
                                 env=env, check=True, text=True, capture_output=True).stdout
    if "uses-permission" in permissions: raise ValueError("Diagnostic APK unexpectedly requests a permission")
    with zipfile.ZipFile(output) as archive:
        native_entries = sorted(n for n in archive.namelist() if n.startswith("lib/") and n.endswith(".so"))
    if native_entries != ["lib/arm64-v8a/libonnxruntime.so", "lib/arm64-v8a/libvoiceprobe.so"]:
        raise ValueError("APK has an unexpected native payload")
    report = {"package": "org.danygramm.voiceprobe", "apk": str(output.relative_to(ROOT)),
              "bytes": output.stat().st_size, "sha256": sha(output), "permissions": [], "abi": "arm64-v8a",
              "min_sdk": 24, "target_sdk": 36, "ndk": "27.2.12479018", "runtime": "1.31.0",
              "engine_sources": source_hashes, "native_elf": elf, "provenance": provenance,
              "app_sources": app_sources, "manifest_permissions_dump": permissions, "native_entries": native_entries,
              "signature_verification": verification, "zipalign_16k": True, "published": False}
    report_dir = ROOT / "artifacts/qa/voice-probe"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"apk": report["apk"], "bytes": report["bytes"], "sha256": report["sha256"], "published": False}))


if __name__ == "__main__":
    main()
