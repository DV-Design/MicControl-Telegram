# Code Review: portable target-voice diagnostic backend

**Date:** 2026-10-20 (Europe/Belgrade)
**Scope:** `TargetVoiceInference.{h,cpp}`, `target_voice_probe.cpp`, and the two
licensing files. New standalone diagnostic files; no product wiring or CMake,
Gradle, Java, microphone-mode or APK changes.
**Verdict:** PASS for the diagnostic implementation. The VoxLock model remains
unsuitable for an owner-only product claim on the tested speakers.

## Findings addressed

- `TargetVoiceInference.cpp:78`: the actual exported output metadata uses
  symbolic batch/band dimensions. Validation now accepts symbolic output
  dimensions while checking static input-state dimensions, tensor names/types,
  ranks and preallocated runtime output geometry. The actual graphs were used
  for execution; no inference substitute was used.
- `TargetVoiceInference.h:27`: corrected the enrollment privacy description.
  Magnitude/context retain private derived acoustic data that may reconstruct
  speech; they are not described as a harmless, non-recording identifier.
- `TargetVoiceInference.cpp:275` and `:407`: final overlap-add samples are
  checked for finiteness as well as the neural frames/recurrent outputs.
  Invalid/runtime-error streams require Reset before further execution.

No unresolved native correctness issue was found in this scope. Remaining model
quality and Android numerical/performance investigations are tracked by the
parent task `miccontrol-adn`; no duplicate worker Beads tasks were created.

## Ownership and streaming review

- Model/session lifetimes are retained by streams. Profiles own immutable
  magnitude/context independently of streams; each stream retains its profile.
  The probe destroys the inference object and external profile before Push.
- Public inference operations return bounded statuses and do not let C++
  exceptions escape. ONNX handles/statuses are released through RAII.
- Fixed external tensors are allocated at stream creation, with separate input
  and output state banks. Successful Push does not allocate wrapper storage;
  ONNX Runtime's internal allocation remains outside that guarantee.
- The port preserves reflect padding, periodic Hann-squared normalization,
  overlap-add, state retention and gain -0.5 from the pinned VoxLock Stream.
  Push produces 256 samples initially and 640 subsequently. Flush exposes only
  the final 384 valid samples, matching Python after its final output trim.
- Streams are serial worker objects. The header explicitly excludes inference
  under the WebRTC capture lock; no delayed FIFO or live-call path is added.

## Validation

- Strict C++17 compilation: `-Wall -Wextra -Werror`, ORT C API 31, PASS on macOS.
- Three actual int8-full model runs against Python Stream goldens: **bit-identical**,
  max absolute difference 0, RMS difference 0, 318720 samples for each profile.
  Evidence: `artifacts/qa/target-voice/native-macos/parity-6930.log`,
  `parity-1320.log`, and `parity-5639.log`.
- ASan + UBSan: full fixture, Reset from active/finished state, null/short/NaN/
  unnormalized input, silent/short enrollment, empty flush and post-flush guard
  all passed. Reset and golden maximum differences were both 0, with no
  sanitizer diagnostics. Evidence: `native-macos/sanitizers-6930.log`.
- LeakSanitizer is unsupported on this macOS target. The separate system
  `leaks --atExit` run on a real two-chunk fixture with Reset reported **0 leaks,
  0 bytes**. The tool noted restrictions on displaying writable memory content.
  Evidence: `native-macos/leaks-short.log`.
- Android standalone compilation/execution is independently coordinated by the
  APK worker. Earlier execution preserved shapes, finite output and sample
  counts, but differs from the Mac quantized reference. The final finite-output
  guard was separately rebuilt and executed in bounded 1/2-thread probes;
  their RTF remained above 1. The original three-profile evidence is preserved.
- The existing native audio suite and full Gradle/APK suite were not rerun:
  none of their source or build inputs were modified by this step.

The native-macos evidence paths above are beneath `artifacts/qa/target-voice/`.
Raw public-data fixtures and their hashes are listed in
`artifacts/qa/target-voice/golden/manifest.json`. Runtime timings from these
functional runs are diagnostic measurements, not a controlled phone benchmark.

## External dependency and product boundary

ORT 1.31.0 is an explicit new diagnostic dependency. No runtime binaries or model
weights are vendored in this source change. Source/model revisions and declared
Apache attribution are recorded in `NOTICE.target-voice`, including the unresolved
WeSpeaker ECAPA weight-license discrepancy (HF Apache-2.0 versus official
pretrained-model documentation CC BY 4.0). The full upstream source license is
retained in `LICENSE.voxlock`. A future packaged runtime needs its MIT LICENSE and
ThirdPartyNotices. Future compilation must preserve IEEE finite checks (do not
inherit the existing voip `-ffast-math` flags for this backend).

The parent precision-control experiment reproduced wrong-speaker selection in
both FP32 and int8-full: the C owner profile on a B+C mixture retained B at about
0.928 gain while C was about 0.112. The absent-owner test also leaked speech.
Evidence: `artifacts/qa/target-voice/precision-control.json`. This is model-quality
failure, not fixed by a mathematically faithful streaming port or by assuming an
additional speaker verifier will recover already suppressed owner speech.
