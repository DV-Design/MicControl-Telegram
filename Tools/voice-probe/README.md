# Danygramm voice speed diagnostic

Separate Android application: `org.danygramm.voiceprobe`, label **Тест изоляции Danygramm**, version `0.1-diagnostic`. ARM64 only; min API24, target API36. Its compiled manifest requests **zero permissions**, including no microphone or network access. It uses no Telegram account and has backup disabled.

Configured measurement: the existing `TargetVoiceInference` engine processes 4 seconds of bundled public LibriSpeech audio (64,000 Float32 samples), using a separate 3-second public reference and 2 inference threads. Results include counts, finite-output validation, load/enrollment time, RTF, chunk percentiles, process peak RSS, device model/ABI/API and page size. There is no audio playback. This measures the earlier target-speaker prototype; it does not establish quality for the current surrounding-noise requirement.

The platform Activity provides Start, Cancel and explicit Copy JSON. The application-scoped worker retains no Activity. Cancellation is checked during extraction and between native blocks; model loading may finish in the background, with paused generations discarded. These runtime behaviors have **not been exercised on a device**.

## Reproduce

Use existing JDK21, SDK36, NDK27.2.12479018 and the repository's Gradle8.13 wrapper/AGP8.13.2:

```sh
.local/tse-venv/bin/python Tools/voice-probe/build_probe.py
```

If Android build/lint tooling is absent from the Gradle cache, explicitly allow its download with `--allow-tool-downloads`. Models and audio are never downloaded by this script. It expects the existing pinned inputs:

- `.local/target-voice/voxlock-a50f4e1d/onnx/{enroll,chunk_int8_full}.onnx`
- `artifacts/qa/target-voice/golden/{mix,reference-6930}.f32`
- `.tmp/current/tse-runtimes/onnxruntime-android-1.31.0.aar` and its existing LICENSE/ThirdPartyNotices files
- Source engine: `TMessagesProj/jni/voip/miccontrol/TargetVoiceInference.{h,cpp}`

The script verifies pinned SHA256 values, compiles the JNI wrapper with static libc++ and 16KiB alignment, and builds this project's own Gradle configuration. Generated assets/libraries stay under ignored `Tools/voice-probe/build/`. The independent QA signing key/password stay under ignored `.local/voice-probe/`; passwords are passed through environment variables and are not logged. The messenger signing key is not used. Output: `artifacts/Danygramm-Voice-Test.apk`; build evidence: `artifacts/qa/voice-probe/build.json`.

## Verified build, 2026-10-20

- Release build including lint: **PASS**, 48 tasks; no UI/device execution.
- APK: **106,438,238 bytes**, SHA256 `a4f54e5b0b99d58715ce1d17526ccea109d6b7df75b5a80ce9fae657cb5f572a`.
- APK v2 signature: **PASS**. Separate QA certificate SHA256 `24e77473239218e6d79c4fd459f52c4883c717ad6abe4e430d96a893c86af3f6`.
- Actual binary-manifest permission dump: package only, **zero permissions**.
- Exactly two ARM64 native libraries: `libvoiceprobe.so` and `libonnxruntime.so`; ELF LOAD and APK ZIP alignment checks: **16KiB PASS**.
- Current app/native source hashes match the built APK's recorded provenance; builder syntax and whitespace checks: **PASS**.
- **Installation, launch, UI, clipboard, cancellation and device inference: NOT RUN at the user's request.** No physical-vivo performance result is claimed.
- APK remains local and **unpublished**.

## Attribution and distribution hold

The package bundles source/model/runtime notices under `assets/licenses/`. VoxLock code/models declare Apache2.0; model revision is `a50f4e1d109301d4b6f61dec57ebb1a61e7d8f03`. ONNX Runtime1.31.0 uses MIT with its third-party notices. The public LibriSpeech recording is CC BY4.0, attributed to Vassil Panayotov/OpenSLR12; the notice records selection, scaling, mixing and cropping. No Krisp or AMI demo recording is included.

The pretrained ECAPA component has an unresolved upstream license discrepancy: its Hugging Face card declares Apache2.0, while official WeSpeaker pretrained-model documentation says CC BY4.0 for VoxCeleb-trained weights. Preserve all notices and resolve the redistribution terms before publishing this model-bearing APK. See the existing `NOTICE.target-voice` and `tests/miccontrol/TARGET_VOICE_TESTS.md` for source/model provenance and prototype limitations.
