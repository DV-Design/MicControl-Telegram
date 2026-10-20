# Google Maps configuration review for Danygramm 1.2

Date: 2026-10-20. Reviewer: independent Android artifact reviewer.
Reviewed source: `1adbb1d8af08e4849da9cdc40e5a941a46d97a7f`, against baseline `49f4f0af0201a5ebe9ff27d47531a11c82be47b2`.
Status: source review and independent static inspection of the real CI APK passed. The user separately confirmed working maps on a phone on 2026-10-20.
Scope: configuration, CI secret propagation, final artifact verification and static release identity.

## Findings

No blocking source defects remain in the reviewed changes. No application code was modified by this review.

The final verifier now requires the canonical Maps metadata to be a direct child of `application`. Its initial version accepted that metadata at any depth; the implementation agent corrected this during review. Activity metadata would not configure the application-level Maps SDK.

## Source evidence

- `.github/workflows/build-apk.yml:24` passes `GOOGLE_MAPS_API_KEY` through step environment variables to preflight, build and final verification. The upload includes the hash-only Maps proof. The build summary explicitly leaves map rendering unvalidated.
- `scripts/ci-preflight.py:37` rejects missing or malformed Maps input before restoring a signing key. Error messages contain configuration names and fixed explanations, without secret values.
- `gradle/miccontrol.gradle:20` loads the key from environment, a Gradle property or ignored local configuration. Its release validation at line 22 rejects missing or malformed input. `TMessagesProj_AppStandalone/build.gradle:134` attaches that validation to non-debug prebuild, and line 157 supplies the manifest placeholder.
- `TMessagesProj/config/release/AndroidManifest_standalone.xml:128` supplies `com.google.android.geo.API_KEY` through the placeholder. The reviewed change adds no SDK, provider, Map ID or billable web-service API.
- `scripts/verify-release-artifacts.py:23` decodes the binary manifest with the installed Android SDK tool and captures both output streams in memory. Lines 46–58 reject duplicate/legacy metadata, incorrect parentage, malformed values, and an environment mismatch. CI requires a nonempty comparison value. Lines 59–65 persist only the key hash, APK hash, source commit, identity and explicit validation booleans.
- Version settings produce `71819` / `13.0.2-danygramm-1.2`. The package, own Telegram credential pipeline and signing identity are unchanged by the source diff.

## Checks completed

The implementation agent's seven preflight controls passed, including missing/malformed input and a positive temporary signing-key restore. The evidence records that the main signing key remained unchanged: `artifacts/qa/maps-1.2/preflight-controls.json`.

The independent helper `.tmp/current/inspect-1.2-ci.py` passed 13 focused decoder/proof controls: valid metadata, wrong parentage, legacy metadata, missing/empty/malformed values, unresolved placeholder, duplicate metadata, a valid CI proof, local dummy proof rejection, wrong APK/key hashes, and rejection of the pinned 1.0 manifest without Maps metadata. Evidence: `artifacts/qa/maps-1.2/independent-helper-controls.json`.

The helper reads the own Telegram API configuration and both non-debug BuildConfig classes from the SHA-pinned public 1.0 APK using `dexdump`, without printing or saving their credential values. Python syntax and `git diff --check` passed. No Gradle build was started by this reviewer.

## Real CI artifact inspection

The independent helper completed successfully on the artifact from [CI run 39420257389](https://github.com/DV-Design/MicControl-Telegram/actions/runs/39420257389), source `1adbb1d8af08e4849da9cdc40e5a941a46d97a7f`. APK size: 58,298,398 bytes. SHA-256: `5b88981df7fd835539a8885d048cbaf57b3dc46f3c45e5d8aceef964e9976d42`.

The checks passed for package `org.miccontrol.messenger.web`, version `71819` / `13.0.2-danygramm-1.2`, label Danygramm, both non-debug BuildConfig classes, and own Telegram API equality in memory against the SHA-pinned 1.0 APK. The audit verified v1/v2 signatures, exactly three arm64 libraries with 16 KiB ELF LOAD alignment, the 160 MiB updater cap, checksum/update metadata, absence of TSE/ORT model payloads and application-level Maps metadata.

The packaged Maps key SHA-256 is `1eda660ac68bc7b77710588b114039852795f61d54f8f2eb1584afc5c2d472c1`. It exactly matches the proof generated in CI from the Actions secret. The proof also matches the actual APK hash, source commit and version, with `matchesEnvironment=true`. No key value was printed or saved by this inspection. The local dummy build was not used for the release.

The signing certificate remains SHA-256 `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`, SHA-1 `47b997830c0498bf3d4d618a3955fbca1d280e69`.

Evidence: `artifacts/qa/maps-1.2/ci-independent/candidate.json`, identical copy `artifacts/qa/1.2-candidate.json`. The [1.2 prerelease](https://github.com/DV-Design/MicControl-Telegram/releases/tag/danygramm-1.2) was subsequently downloaded in full without authentication; size, APK SHA-256, checksum and update metadata matched. Evidence: `artifacts/qa/1.2-public-download/verified.json`. The latest stable release remains 1.0.

## User phone confirmation

On 2026-10-20 the user confirmed that maps work in 1.2 on their phone. This is a user-reported physical result, separate from the static artifact checks above. The reviewer did not operate the phone or run a map-rendering test. Audio processing is unchanged from 1.1; the user reported residual noise and speech interruptions on a loud background, tracked separately as `miccontrol-8sd` using 1.2 as its base.

## Limits

The reviewer performed no UI, adb, emulator, device, instrumentation, authentication or Google API request. A packaged key matching the Actions secret proves configuration propagation. This audit did not inspect Cloud-side billing or package/certificate restriction settings. The user's phone confirmation is the evidence for live map rendering. [Google setup documentation](https://developers.google.com/maps/documentation/android-sdk/get-api-key), [Android SDK configuration](https://developers.google.com/maps/documentation/android-sdk/config).

Binary manifest decoding uses the existing Android SDK `aapt2` command, rather than a custom AXML decoder. [Android AAPT2 documentation](https://developer.android.com/tools/aapt2#dump).
