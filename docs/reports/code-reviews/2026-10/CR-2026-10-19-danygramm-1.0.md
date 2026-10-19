# Danygramm 1.0: implementation review and release verification

Date: 2026-10-19. Source: release tag `danygramm-1.0`.
Package: `org.miccontrol.messenger.web`, version code `71799`.
APK SHA-256: `02ba8667b1909cffc20d0a5d412d3d6413f1d0d3e0da8a3a795531b4a12191ec`.

## Result

The signed non-debug arm64 candidate passed the final **28/28 Android checks**
in 28.485s with no skipped cases. The final test-only rebuild did not change
the product APK. Host native tests passed ASan/UBSan. The existing signing
identity and installation data are retained. Full scope and evidence are in
[Android runtime tests](../../../../tests/miccontrol/ANDROID_RUNTIME_TESTS.md).

## Reviewed changes and resolved findings

- Three microphone modes configure the existing capture APM immediately.
  NS/HPF/AGC and RNNoise are bypassed in no-effects mode; echo control stays
  with the call engine. Group/conference processors retain their old behavior.
- Native review found a stale-config race that could overwrite a concurrent
  echo-control update. Refresh now takes the normal render/capture locks and
  changes only managed capture settings. Per-APM mode snapshots prevent a
  split NS/RNNoise frame; denoiser history resets on mode changes.
- RNNoise spectral attenuation uses exponent 1.30. Noise-fixture residual
  energy fell 28.2%; clean TTS retained 98.48% of previous output energy.
  This is denoising, not owner-specific speech separation.
- Chat-local ML Kit translation changes transient display text only. Review
  covered ownership/generation/source guards, visible-object identity,
  cache and queue limits, model inventory, callback lifetimes, original
  captions/entities, summary separation and preservation of Premium settings.
- Missing `danygramm_*.xml` inputs caused visible `LOC_ERR` strings. Both
  localization plugins now include these named files. Installed EN/RU assets
  and literal text in the actual sheet are independently checked.
- Persistent delivery uses the existing native Telegram connection and a
  private `specialUse` foreground service. It stops without an active account;
  UI reports actual service and Android notification/battery state. An
  unconfigured Firebase project is not presented as a working FCM provider.
- Updates use the fixed public repository, bounded HTTPS transfers and cache,
  strict redirect/tag validation, size/hash/package/version/certificate checks
  and the Android installer. An actual APK signed with another key was rejected.
- All adaptive icon qualifiers now use the canonical paper plane and two red
  wing stars. The actual render matches upstream proportions. Status icons
  use the same plane silhouette under Android's monochrome rendering.
- AndroidTest L8 originally shadowed 388 target methods with a trimmed runtime.
  Keeping a compatible full runtime in AndroidTest only eliminated all gaps.
  Shipping L8 behavior was independently checked as unchanged.
- Harness fixes preserve real assertions: nullable in-memory account restore
  under its existing lock, no setter-triggered premium request, bounded wait
  for actual FGS notification, and standard chat-resource initialization.

## Release gates

- AfatStandalone app + matching tests: build PASS, own API matched previous
  verified APK in memory, sample flag false, debuggable false and logs false.
- v1/v2 signature PASS; certificate `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe` unchanged.
- All three arm64 libraries have 16 KiB LOAD alignment; real emulator page
  size is 16384. Normal cold launch passed in 1228ms.
- Actual upgrade retained the original first-install timestamp.
- XML/Python syntax, shellcheck, actionlint and whitespace checks PASS.
  CI configuration and nine configuration failure controls were reviewed;
  this release's actual APK was built and tested locally.
- Public publication/download verification is added after the release upload.

## Acceptance limits and next work

No authenticated messaging, real incoming call, prolonged OriginOS sleep,
physical vivo/AirPods route or human intelligibility result is claimed by
these emulator tests. Device acceptance stays in `miccontrol-6w0`; historical
TestDC authentication remains separate. The user requested owner-only voice
extraction next (`miccontrol-adn`); current RNNoise does not satisfy that new
requirement. API credentials, signing material and sessions are not committed.
