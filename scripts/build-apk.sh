#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
build_type=standalone
allow_sample=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help)
            printf '%s\n' 'Usage: scripts/build-apk.sh [--debug] [--allow-sample-api] [extra Gradle arguments]' \
                'Default: non-debug standalone APK with own API and the existing signing key.' \
                'Set TELEGRAM_API_ID / TELEGRAM_API_HASH in ignored local.properties or the environment.' \
                '--allow-sample-api is permitted only with --debug.'
            exit 0 ;;
        --debug) build_type=debug; shift ;;
        --allow-sample-api) allow_sample=true; shift ;;
        *) break ;;
    esac
done
if [[ "$build_type" == standalone && "$allow_sample" == true ]]; then
    printf '%s\n' 'Sample API credentials are forbidden in a standalone release.' >&2
    exit 1
fi
export MICCONTROL_ALLOW_SAMPLE_API="$allow_sample"

if [[ -z "${JAVA_HOME:-}" ]]; then
    if [[ -d /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home ]]; then
        export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
    elif [[ -x /usr/libexec/java_home ]]; then
        JAVA_HOME="$(/usr/libexec/java_home -v 21)"
        export JAVA_HOME
    else
        printf '%s\n' 'Set JAVA_HOME to a JDK 21 installation.' >&2
        exit 1
    fi
fi
export PATH="$JAVA_HOME/bin:$PATH"
if [[ -z "${ANDROID_HOME:-}" ]]; then
    if [[ -n "${ANDROID_SDK_ROOT:-}" ]]; then
        export ANDROID_HOME="$ANDROID_SDK_ROOT"
    elif [[ -d "$HOME/Library/Android/sdk" ]]; then
        export ANDROID_HOME="$HOME/Library/Android/sdk"
    else
        export ANDROID_HOME="$HOME/Android/Sdk"
    fi
fi
build_tools="$ANDROID_HOME/build-tools/36.0.0"
if [[ ! -x "$build_tools/apksigner" ]]; then
    printf '%s\n' 'Android SDK Build Tools 36.0.0 is missing. See README_MICCONTROL_RU.md.' >&2
    exit 1
fi
export MICCONTROL_ABIS=arm64-v8a
umask 077
mkdir -p artifacts
sha256_digest() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@";
    else shasum -a 256 "$@";
    fi
}
signing_keystore=.local/miccontrol-debug.keystore
if [[ ! -f "$signing_keystore" ]]; then
    printf '%s\n' 'Existing .local/miccontrol-debug.keystore is required; do not generate a replacement.' >&2
    exit 1
fi
expected_cert=59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe
certificate_digest=$("$JAVA_HOME/bin/keytool" -exportcert -keystore "$signing_keystore" \
    -storepass android -alias androiddebugkey 2>/dev/null | sha256_digest | cut -d ' ' -f 1)
if [[ "$certificate_digest" != "$expected_cert" ]]; then
    printf '%s\n' 'Signing certificate differs from the installed Danygramm app.' >&2
    exit 1
fi
if [[ "$build_type" == standalone ]]; then
    gradle_task=:TMessagesProj_AppStandalone:assembleAfatStandalone
    output_apk=artifacts/Danygramm-arm64.apk
else
    gradle_task=:TMessagesProj_AppStandalone:assembleAfatDebug
    output_apk=artifacts/Danygramm-arm64-debug.apk
fi
./gradlew "$gradle_task" \
    --max-workers="${MICCONTROL_GRADLE_WORKERS:-2}" --no-parallel --console=plain \
    '-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g' "$@"

source_apk="TMessagesProj_AppStandalone/build/outputs/apk/afat/$build_type/app.apk"
cert_report=$(mktemp)
trap 'rm -f "$cert_report"' EXIT
"$build_tools/apksigner" verify --print-certs "$source_apk" > "$cert_report"
grep -Fxq "Signer #1 certificate SHA-256 digest: $expected_cert" "$cert_report"
badging=$("$build_tools/aapt" dump badging "$source_apk")
if [[ "$build_type" == standalone ]] && grep -q '^application-debuggable' <<< "$badging"; then
    printf '%s\n' 'Refusing to publish a debuggable standalone APK.' >&2
    exit 1
fi
cp "$source_apk" "$output_apk"
(cd artifacts && sha256_digest "${output_apk##*/}" > "${output_apk##*/}.sha256")
if [[ "$build_type" == standalone ]]; then
    python3 scripts/make-update-metadata.py <<< "$badging"
    python3 scripts/verify-release-artifacts.py
fi
printf 'APK: %s/%s\n' "$PWD" "$output_apk"
