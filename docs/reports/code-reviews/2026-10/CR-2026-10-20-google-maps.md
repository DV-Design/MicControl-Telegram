# Google Maps configuration review for Danygramm 1.2

Date: 2026-10-20. Reviewer: independent Android artifact reviewer.
Baseline: `49f4f0af0201a5ebe9ff27d47531a11c82be47b2` plus the scoped Maps configuration changes.
Status: source review passed; inspection of the real CI release artifact is pending.
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

## Pending real CI artifact inspection

The helper requires an explicitly supplied APK, checksum, update metadata, Maps proof, expected source commit and expected APK SHA-256. It rejects the local dummy proof because `matchesEnvironment` must be true and `sourceCommit` must equal the expected full CI commit.

The actual audit will check version/package/label, both non-debug BuildConfig classes, own Telegram API equality in memory against the SHA-pinned 1.0 APK, signing certificate SHA-256 and SHA-1, v1/v2 signatures, exactly three arm64 libraries with 16 KiB ELF LOAD alignment, the 160 MiB updater cap, checksum/update metadata, absence of TSE/ORT model payloads, application-level Maps metadata and exact equality to the CI proof's key hash.

The expected signing certificate remains SHA-256 `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`, SHA-1 `47b997830c0498bf3d4d618a3955fbca1d280e69`.

## Limits

No UI, adb, emulator, device, instrumentation, authentication or Google API request was performed. A packaged key matching the Actions secret proves configuration propagation. It does not establish enabled Maps SDK access, billing status, Android package/certificate restrictions, or successful live map rendering. Google requires those Cloud-side prerequisites separately. [Google setup documentation](https://developers.google.com/maps/documentation/android-sdk/get-api-key), [Android SDK configuration](https://developers.google.com/maps/documentation/android-sdk/config).

Binary manifest decoding uses the existing Android SDK `aapt2` command, rather than a custom AXML decoder. [Android AAPT2 documentation](https://developer.android.com/tools/aapt2#dump).
