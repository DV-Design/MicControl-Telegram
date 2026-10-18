# Android runtime tests

## Current status: dev3 built with own API; test-account authentication blocked

On 2026-10-18 the own API secrets were supplied. The first run passed preflight
but failed because `sdkmanager` was unavailable (exit 127). Explicit SDK setup
was added in `35483bd`; [run 39156162098](https://github.com/DV-Design/MicControl-Telegram/actions/runs/39156162098)
then succeeded with 300 Gradle tasks in 29m 13s and produced
`MicControl-arm64-3`.

The downloadable candidate is the [private dev3 prerelease](https://github.com/DV-Design/MicControl-Telegram/releases/tag/miccontrol-dev3).
GitHub sign-in with repository access is required. Local APK:
`artifacts/MicControl-arm64-dev3.apk`, 65,652,128 bytes, SHA-256
`a4340f91518cabe3e8367965413784953676412c4823affd0511fd49337a8b70`.
The release download independently matched that hash.

| Check on this dev3 candidate | Result / scope |
|---|---|
| Package / version | `org.miccontrol.messenger.web`, `13.0.2-miccontrol-dev3`, code `71779`, min 23 / target 36 |
| Configuration inspection | `sampleFlag=false`, `apiIdIsSample=false`, `hashFormatValid=true`; no API secrets recorded |
| APK integrity / signing | SHA-256 matched; v1/v2 verified; existing certificate `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`; both native ELF LOAD alignments at least 16 KiB |
| Upgrade / cold launch | Update install succeeded; 2,620 ms launch on API 36 arm64, 16 KiB pages, four cores, 4 GiB RAM, host GPU |
| MTProto network case | Exactly **one** `MicControlNetworkTest` passed in 1.817s: DC 1, `test_mode=true`, nine endpoints |
| Test-account authentication | **BLOCKED** at `PHONE_CODE_INVALID`; UI and an independent client both rejected the documented test code |
| Personal production login / messaging / calls | Unverified; no personal number or real-account code was used, and authenticated scenarios were not reached |

Evidence: `artifacts/qa/dev3-auth/candidate.json`, `07-networkcase.txt` and
`07-config-test-mode.log` in the same directory. The network result covers the
test server; it is not a production-login result. **The full sixteen-case
suite was not rerun on dev3.** Its historical dev2 result is preserved below.

Dev3 retains the package and signing identity for upgrade installation. For a
personal production account, turn **Test Backend OFF** on the phone-number
screen; that choice persists across updates.

## Dev3 authentication blocker and remaining acceptance

The UI successfully completed `auth.sendCode`, handled `PHONE_MIGRATE_2`, and
displayed a five-digit SMS-code screen on TestDC2. Entering the documented
reserved-account code `22222` returned `PHONE_CODE_INVALID`.

An independent Telethon 1.45.0 probe used the same own API configuration, a
fresh in-memory session and pinned TestDC2 on port 80. It confirmed
`test_mode=true` and `SentCodeTypeSms(length=5)`, then received
`PhoneCodeInvalidError` for both `22222` and the documented six-digit test
fallback `222222`. This reproduces the rejection independently; its server-side
cause is not established. Tests stopped without signup or messaging.

Evidence in `artifacts/qa/dev3-auth/`: `17-after-permissions.json`,
`19-rpc-names.json`, `19-code-result.png`, `19-code-result.json`, and
`20-reference.log`. The verified removal of API ID 4 does not establish that
production login now succeeds. The user's personal production retest has no
reported result yet.

After successful authentication, send and receive a uniquely identified text
message, upload/download a small file and compare SHA-256, find the test message
through search, and restart the app to verify the same account/session and
message history remain available. Record candidate APK hash, environment and
each result. Calls and Bluetooth audio need a separate peer and the actual
vivo/AirPods hardware. None of these authenticated scenarios has passed yet.

## Historical dev1/dev2 results: sample API rejection and sixteen-case PASS

The user's 2026-10-17 dev2 screenshot showed the real production `auth.sendCode`
error **`API_ID_PUBLISHED_FLOOD`**. Dev1/dev2 deliberately used upstream sample
API ID 4; [Telegram documents](https://core.telegram.org/api/obtaining_api_id)
its server restrictions. That rejection motivated the own-API dev3 build;
repeating sample-API requests does not address it.

On 2026-10-17 the resumed dev1 run passed **all eight cases in 6.594 seconds** on
Android 16 arm64 with 16 KiB pages, four emulator cores and 4 GiB RAM. The
network case was explicitly enabled and returned a real production
`help.getConfig`: DC 2, `test_mode=false`, 19 datacenter endpoints. There were
no skipped cases. Raw local evidence is in
`artifacts/qa/android-runtime-tests-bounded.txt` and its matching logcat file.

Cold app launch also succeeded in 5,985 ms. The original ActivityScenario
lifecycle case waited indefinitely for an idle UI queue while the upstream
Intro continuously invalidated its animated view. The bounded test helper
described below removes that harness dependency; app code and the candidate
APK were unchanged for this passing run.

The updated **dev2** app and matching test APK subsequently passed **all sixteen
cases in 20.155 seconds**, including the eight login-error regressions below.
There were zero failures and zero skipped cases. After a clean app-data reset
on the isolated emulator, the network probe again returned production DC 2,
`test_mode=false`, and 19 endpoints. Evidence:
`artifacts/qa/dev2-all-tests-green.txt` and its matching logcat file.

The earlier first-boot run also recorded a startup ANR while loading DEX under
CPU contention with two emulator cores and 3 GiB RAM. Repeating normal launch
with four cores and 4 GiB RAM succeeded. This eight-case suite establishes neither
account login nor messaging/call functionality; those are separate scenarios.

## Lifecycle synchronization

Both software and host GPU runs reached a visible, responsive Intro while the
test runner remained blocked at Android 16 `Instrumentation.startActivitySync`,
line 625. Android registers an `ActivityGoing` idle handler during activity
creation and removes the startup waiter only when that handler runs. The
upstream Intro's animated button calls `invalidate()` from every `onDraw`, so
waiting for the whole UI queue to idle can prevent this harness from advancing.
The application itself was not blocked in an app lock or crashing.

The test-only `TestActivitySession` uses the existing AndroidX Test lifecycle
monitor, starts the real activity with `Context.startActivity`, and waits at
most 45 seconds for each actual lifecycle event. Main-thread actions and
assertions use `Handler`/`FutureTask` with a 15-second limit. It retains a new
activity launch, visible Intro/login checks, a real task move to background and
return, recreation with a different instance and destruction of the old one,
and activity/listener cleanup. Timeouts remain failures; the helper changes no
product animation, credentials, network setting, or assertion into a skip.

Primary implementation references:

- [Android 16 Instrumentation: startActivitySync, prePerformCreate, ActivityGoing](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/core/java/android/app/Instrumentation.java)
- [AndroidX ActivityScenario: idle waits and activity invocation](https://github.com/android/android-test/blob/main/core/java/androidx/test/core/app/ActivityScenario.java)
- [AndroidX ActivityLifecycleMonitor: lifecycle observation on the UI thread](https://github.com/android/android-test/blob/main/runner/monitor/java/androidx/test/runner/lifecycle/ActivityLifecycleMonitor.java)
- [AndroidX ActivityLifecycleCallback: callbacks after lifecycle events](https://github.com/android/android-test/blob/main/runner/monitor/java/androidx/test/runner/lifecycle/ActivityLifecycleCallback.java)

## Reproduction

These tests instrument **TMessagesProj_AppStandalone / AfatDebug**, package
`org.miccontrol.messenger.web`. The current downloaded candidate is
`artifacts/MicControl-arm64-dev3.apk`; local builds below write
`TMessagesProj_AppStandalone/build/outputs/apk/afat/debug/app.apk`. Use the
matching test APK and existing development signing key. The separate upstream
`AppTests` application has a different signing setup and must not replace this
candidate.

Use a dedicated Android emulator without personal accounts. The APK currently
contains only `arm64-v8a`; an ARM64 Android 16 / API 36 image with 16 KiB pages
also exercises native loading on that page size. The unauthenticated lifecycle
and network tests skip when an activated Telegram account is present.

After creating the local key with `scripts/build-apk.sh`, build both APKs:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME="$HOME/Library/Android/sdk"
export MICCONTROL_ABIS=arm64-v8a
# Set own API values in ignored local.properties or the environment.
export MICCONTROL_ALLOW_SAMPLE_API=false
./gradlew :TMessagesProj_AppStandalone:assembleAfatDebug \
  :TMessagesProj_AppStandalone:assembleAfatDebugAndroidTest \
  --max-workers=2 --no-parallel --console=plain \
  '-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g'
```

With one emulator connected, install the application and its matching test APK:

```bash
"$ANDROID_HOME/platform-tools/adb" install -r \
  TMessagesProj_AppStandalone/build/outputs/apk/afat/debug/app.apk
"$ANDROID_HOME/platform-tools/adb" install -r -t \
  TMessagesProj_AppStandalone/build/outputs/apk/androidTest/afat/debug/TMessagesProj_AppStandalone-afat-debug-androidTest.apk
"$ANDROID_HOME/platform-tools/adb" shell am instrument -w -r \
  org.miccontrol.messenger.web.test/androidx.test.runner.AndroidJUnitRunner
```

Seven local cases check the installed manifest and account type, onboarding
lifecycle/background/recreation, JNI buffers with Unicode and TL byte-array
boundaries (including a payload larger than 16 KiB), Telegram peer serialization
with a 64-bit identifier, native TLS ClientHello structure, registered VoIP
implementations, and repeated microphone mode setter calls with preference
restoration. The mode test verifies JNI linkage and setting storage; it does not
capture audio or prove the effect during a call.

The eighth case is an opt-in read-only request through the application's actual
MTProto stack. It fetches `help.getConfig` with a 45-second timeout and validates
the decoded datacenter configuration. It never signs in, requests a code, or
sends a message. Enable it explicitly:

```bash
"$ANDROID_HOME/platform-tools/adb" shell am instrument -w -r \
  -e miccontrolNetwork true \
  org.miccontrol.messenger.web.test/androidx.test.runner.AndroidJUnitRunner
```

Without that argument the network case is **skipped**, not passed. A timeout or
server rejection with the argument enabled is a failure and must be reported.
These checks do not establish production login, message/media delivery,
background push, calls, Bluetooth routing, or sound quality on vivo/AirPods.
Those require separate tests with the relevant accounts and hardware.

## Login error regressions

Before the fix, the original dev1 app failed five of these eight cases while
all three controls passed. After the fix, every case passed in the combined
sixteen-case dev2 run. The baseline failure log is
`artifacts/qa/login-errors-regression-real-codes-red.txt`.

`MicControlLoginErrorsTest` adds eight local cases using the actual
`AlertsCreator.processError`, a real `LoginActivity` attached to the resumed
activity, and actual displayed dialog text. The fixtures cover
`API_ID_PUBLISHED_FLOOD` / `API_ID_INVALID` (400), `UPDATE_APP_TO_LOGIN` (406),
`AUTH_RESTART` (500), an unknown send-code error, and three controls: existing
resend errors remain visible, unrelated 406 responses remain silent, and
cancelled requests (-1000) remain silent. Dialogs and activity state are cleaned
up after each case. The test constructs request objects but never submits a
login request or asks Telegram to deliver a code.

Run this class alone with:

```bash
"$ANDROID_HOME/platform-tools/adb" shell am instrument -w -r \
  -e class org.miccontrol.test.MicControlLoginErrorsTest \
  org.miccontrol.messenger.web.test/androidx.test.runner.AndroidJUnitRunner
```

## Historical dev2 test-account authentication: blocked before messaging

The dev2 UI reached a real test-server code screen after correctly handling
`PHONE_MIGRATE_2`, with phone/call-log permissions denied. The documented code
for the reserved DC2 test number was rejected as `PHONE_CODE_INVALID`, both
with bulk accessibility entry and ordinary Android keyboard events.

An independent **Telethon 1.45.0** probe reproduced the rejection on TestDC2
and a separate reserved TestDC1 number. Both endpoints returned
`Config.test_mode=true` and `SentCodeTypeSms(length=5)`. Each rejected its
documented five-digit code and the six-digit fallback described in
[Telethon's test-server documentation](https://docs.telethon.dev/en/stable/developing/test-servers.html).
The probes used the same public sample API, fresh in-memory sessions and one
send-code request per number; no session/auth key was saved and no signup was
performed. This establishes an independent rejection, not its server-side cause
or a demonstrated restriction affecting every API/account.

Local evidence: `artifacts/qa/dev2-test-auth-errors.txt`,
`telethon-reference-probe.log`, `telethon-reference-probe-dc1.log`, and the two
matching reference scripts. Messaging, file transfer, search and authenticated
session persistence remain **unverified** until an authorized test account is
available. No personal number or real-account confirmation code was used in
these probes. The sixteen-case automated PASS above remains valid within its
documented scope.
