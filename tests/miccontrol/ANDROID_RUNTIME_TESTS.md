# Android runtime tests

## Current status: production login blocked by the sample API

The user's 2026-10-17 dev2 screenshot shows the real production
`auth.sendCode` error **`API_ID_PUBLISHED_FLOOD`**. This is now direct evidence
of the rejection on the user's device. The APK deliberately used the public
upstream sample API ID 4; [Telegram documents](https://core.telegram.org/api/obtaining_api_id)
that this sample is server-limited and unsuitable for end-user applications.
The own `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` needed for a corrected build
are absent. Repeating the same sample-API login does not address this failure.

The sixteen passing checks below remain valid for their stated scope; **they
are not a successful-login or messaging result**. No working-client claim is
made for dev1/dev2.

The manual GitHub build for the next dev3 candidate now requires own API
credentials and the existing private signing key. Its preflight rejects the
sample ID/hash and validates the original signing certificate before SDK,
submodules or native compilation. Actionlint/ShellCheck, Bash/Python syntax,
eleven negative input cases and a format-only positive private-key restoration
check passed. Main-agent review independently repeated six relevant cases and
verified exact restored bytes, mode 0600 and the untouched original local key.
Those are configuration/signing checks, not Telegram authentication results.
The default Gradle configuration also rejected missing own API values in six
seconds; raw evidence is `artifacts/qa/own-api-missing-preflight.txt`.

## Required functional acceptance after replacing the credentials

Use the same package and signing certificate so the user can upgrade. First
verify that the candidate contains the intended non-sample API configuration,
then attempt one login on a dedicated authorized test account. Record the
actual server response. If authentication fails, stop the messaging scenario
and report that failure rather than replacing it with a connectivity result.

After successful authentication, send and receive a uniquely identified text
message, upload/download a small file and compare SHA-256, find the test message
through search, and restart the app to verify the same account/session and
message history remain available. Record candidate APK hash, environment and
each result. Calls and Bluetooth audio need a separate peer and the actual
vivo/AirPods hardware. None of these authenticated scenarios has passed yet.

## Previous scoped result: sixteen runtime cases passed

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

These tests instrument **TMessagesProj_AppStandalone / AfatDebug**, the same
`org.miccontrol.messenger.web` candidate as `artifacts/MicControl-arm64-dev.apk`.
They use the local development signing key. The separate upstream `AppTests`
application has a different signing setup and must not replace this candidate.

Use a dedicated Android emulator without personal accounts. The APK currently
contains only `arm64-v8a`; an ARM64 Android 16 / API 36 image with 16 KiB pages
also exercises native loading on that page size. The unauthenticated lifecycle
and network tests skip when an activated Telegram account is present.

After creating the local key with `scripts/build-apk.sh`, build both APKs:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME="$HOME/Library/Android/sdk"
export MICCONTROL_ABIS=arm64-v8a
# Only if using the deliberately limited upstream sample API:
export MICCONTROL_ALLOW_SAMPLE_API=true
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

## Test-account authentication: blocked before messaging

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
