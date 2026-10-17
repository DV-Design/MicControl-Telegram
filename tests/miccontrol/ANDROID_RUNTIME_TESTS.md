# Android runtime tests

## Current status: eight runtime cases passed

On 2026-10-17 the resumed run passed **all eight cases in 6.594 seconds** on
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
