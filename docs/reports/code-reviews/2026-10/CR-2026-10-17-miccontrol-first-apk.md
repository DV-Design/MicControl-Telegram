# Code Review Report: MicControl first APK

**Generated**: 2026-10-16 22:18:05 UTC
**Date**: 2026-10-17 (Europe/Belgrade)
**Status**: ✅ success — source/build checks
**Version**: 13.0.2-miccontrol-dev1
**Workflow**: code-review
**Phase**: verification
**Reviewer**: main agent; this report records its independently completed review and verification.
**Scope**: Java mode selection/persistence, JNI bridge, common WebRTC APM capture processing, RNNoise lifecycle, Android build configuration, branding and fork authentication isolation. Upstream base: `f32ffeec763f0bdbf4bec25b52d654f77bff733d`. No new dependencies or modified submodules.

## Summary

**Verdict: PASS for source/build checks.** No unresolved code findings remain from this review. Two P2 findings were fixed and verified. Device runtime, Bluetooth routing and perceived audio quality remain untested.

| Findings | P0 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| Open | 0 | 0 | 0 | 0 |
| Resolved | 0 | 0 | 2 | 0 |

## Resolved findings

### P2 — RNNoise state reset leaked recurrent buffers (`miccontrol-7f9`)

- **Evidence**: `TMessagesProj/jni/voip/rnnoise/src/denoise.c:264` zeroes the state with `memset`, then allocates three GRU buffers with `calloc`. Calling `rnnoise_init` on an already initialized state overwrote the allocated buffer pointers when the microphone mode changed.
- **Impact**: repeated mode changes leaked memory during calls.
- **Fix**: `TMessagesProj/jni/voip/miccontrol/VoiceIsolationDenoiser.cpp:21` destroys the old state and creates a new one instead of reinitializing live allocated state.
- **Verification**: reproduced the failing allocation-accounting check before accepting the fix. The final native suite passes with ASan/UBSan and balanced allocation counters. Bead closed after verification.

### P2 — Fork login depended on official signing/OAuth configuration (`miccontrol-y9n`)

- **Evidence**: the fork changes its package and signing key, while upstream SMS hashes and Google OAuth configuration belong to the official client. Google OAuth client settings can also be overwritten from saved/server configuration. System accounts and contact MIME types originally shared the official client's identifiers.
- **Fix**: `TMessagesProj/src/main/java/org/telegram/messenger/BuildVars.java:31` defines the fork's account type; authenticator, sync/contact XML, contact creation and intent handling use the matching MicControl identifiers. `BuildVars.java:46` supplies an explicit disabled Google Sign-in capability, checked in both visibility and click paths in `TMessagesProj/src/main/java/org/telegram/ui/LoginActivity.java:6008`; server configuration cannot reenable the official OAuth path. `LoginActivity.java:3082` disables SMS app hashes/Firebase login and `BuildVars.java:97` returns no official SMS hash. Manual code entry remains available. Passkeys are disabled for the fork.
- **Verification**: main-agent source review and successful complete Android compilation. Bead closed after verification; actual account login requires a device and remains a runtime follow-up.

## Validation

| Gate | Result |
|---|---|
| Full `:TMessagesProj_AppStandalone:assembleAfatDebug` | **PASS**, 4m 59s, 300 tasks |
| Final repeated build | **PASS**, 1s, 4 executed / 296 up-to-date; identical APK SHA-256 |
| Java/JNI/C++ compilation | **PASS**, included in the Android build |
| `python3 tests/miccontrol/run_native_tests.py --sanitize` | **PASS**, independently run by the main agent |
| Native test coverage | 8/16/32/48 kHz, mono/stereo, exact bypass, 50 toggles per rate, finite/bounded amplitude, silence, channel isolation and allocation counters |
| `bash -n scripts/build-apk.sh` | **PASS** |
| Changed/new XML syntax | **PASS**, 19 files parsed in final verification |
| `git diff --check` | **PASS** |
| APK signature | **PASS**, apksigner v1 + v2 |
| Native packaging | **PASS**, both packaged libraries are arm64 only; ELF LOAD alignment 16 KiB |
| JNI entry point | **PASS**, exported microphone-mode setter verified |

Compiler/deprecation/metadata warnings came from upstream code or tooling; there were no build errors. No additional JavaScript/TypeScript type-check gate applies to this Android project.

## Verified APK

- **Local artifact**: `artifacts/MicControl-arm64-dev.apk`
- **Size**: 65,651,539 bytes
- **SHA-256**: `7548c483a68940425311492d5e62a67b729055718b14da8b2ba30fe26be3bccb`
- **Application ID / label**: `org.miccontrol.messenger.web` / `MicControl`
- **Version**: `13.0.2-miccontrol-dev1`, versionCode `71759`
- **SDK**: min `23`, target `36`; `debuggable=true`
- **Signing certificate**: `CN=MicControl Development, O=MicControl`
- **Certificate SHA-256**: `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`

The APK and local signing key are intentionally ignored by Git. This is a development APK built with the explicitly enabled public upstream sample API. It has no claim of production signing or device validation.

## Remaining work and handoff

- `miccontrol-6w0`: physical vivo X200 Ultra / AirPods 3 checks: account login, personal voice/video calls, Bluetooth microphone route, in-call mode changes, persistence, background delivery, audio quality and battery use.
- `miccontrol-7vi`: own Telegram API credentials, optional own Firebase/OAuth/Maps configuration, release signing and notification verification before a daily-use release. Keep credentials outside Git.
- `miccontrol-b4y`: source push awaits the user's repository URL/access. No push is claimed. Main feature `miccontrol-2c2` stays in progress until the source commits are pushed successfully.

The source/build verdict covers the reviewed implementation and verified development artifact. It does not establish runtime call quality or complete repository publication.
