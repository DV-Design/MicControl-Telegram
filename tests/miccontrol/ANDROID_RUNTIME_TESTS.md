# Android runtime tests

## Current run: interrupted by user

On 2026-10-17 the user explicitly requested that testing stop. The emulator and
instrumentation were stopped; this suite has **not passed as a whole**. Six local
cases passed on Android 16 arm64 with 16 KiB pages. Cold app launch succeeded in
5,985 ms. The lifecycle case was blocked inside `Instrumentation.startActivitySync`
waiting for an idle UI queue while the upstream Intro continuously invalidated its
animated view. The opt-in network case was not reached. A bounded lifecycle
harness remains follow-up work; resume testing only when requested.

The earlier first-boot run also recorded a startup ANR while loading DEX under
CPU contention with two emulator cores and 3 GiB RAM. Repeating normal launch
with four cores and 4 GiB RAM succeeded. These partial results establish neither
account login nor messaging/call functionality.

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
