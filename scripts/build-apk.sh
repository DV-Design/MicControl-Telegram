#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ "${1:-}" == "--help" ]]; then
    printf '%s\n' 'Usage: scripts/build-apk.sh [--allow-sample-api] [extra Gradle arguments]' \
        'Set TELEGRAM_API_ID / TELEGRAM_API_HASH in ignored local.properties or the environment.' \
        'The sample API is only for a development test and may prevent login.'
    exit 0
fi
if [[ "${1:-}" == "--allow-sample-api" ]]; then
    export MICCONTROL_ALLOW_SAMPLE_API=true
    shift
fi

if [[ -z "${JAVA_HOME:-}" ]]; then
    if [[ -d /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home ]]; then
        export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
    elif [[ -x /usr/libexec/java_home ]]; then
        export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
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
if [[ ! -x "$ANDROID_HOME/build-tools/36.0.0/apksigner" ]]; then
    printf '%s\n' 'Android SDK Build Tools 36.0.0 is missing. See README_MICCONTROL_RU.md.' >&2
    exit 1
fi
export MICCONTROL_ABIS=arm64-v8a

umask 077
mkdir -p .local artifacts
debug_keystore=.local/miccontrol-debug.keystore
if [[ ! -f "$debug_keystore" ]]; then
    "$JAVA_HOME/bin/keytool" -genkeypair -noprompt -keystore "$debug_keystore" \
        -storetype JKS -storepass android -keypass android -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -dname 'CN=MicControl Development, O=MicControl'
fi

./gradlew :TMessagesProj_AppStandalone:assembleAfatDebug \
    --max-workers="${MICCONTROL_GRADLE_WORKERS:-2}" --no-parallel --console=plain \
    '-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g' "$@"

source_apk=TMessagesProj_AppStandalone/build/outputs/apk/afat/debug/app.apk
output_apk=artifacts/MicControl-arm64-dev.apk
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify "$source_apk"
cp "$source_apk" "$output_apk"
if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$output_apk" > "$output_apk.sha256"
else
    sha256sum "$output_apk" > "$output_apk.sha256"
fi
printf 'APK: %s/%s\n' "$PWD" "$output_apk"
