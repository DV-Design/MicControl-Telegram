# Code review: MicControl login errors

**Date**: 2026-10-17 (Europe/Belgrade)
**Reviewer**: main agent; independently reviewed source and ran device checks.
**Scope**: `AlertsCreator.processError`, login regression tests, bounded Android
lifecycle tests and dev2 build metadata. Source commit: `46c415d`.
**Verdict**: PASS for the reviewed error handling and sixteen Android cases.

## Finding and fix

**Resolved P1 — failed code requests could return to the phone form silently
(`miccontrol-6kp`).**

`LoginActivity.java:3239` delegates unlisted `auth.sendCode` failures to
`AlertsCreator.processError`. The original handler did not include
`TL_auth_sendCode`, and its initial guard also discarded every RPC error 406.
Consequently API configuration failures, required updates and other failures
could hide the spinner without showing the user a reason.

`AlertsCreator.java:289` now permits send-code errors through the 406 guard.
`AlertsCreator.java:553` routes that request through the existing resend-code
error dialogs. Other request types retain their handling of 406; cancelled
requests with code -1000 remain silent. No authentication success check,
delivery rule, endpoint, credential or permission was weakened. No dependency
was added for the fix.

The fixtures use Telegram's documented RPC codes: API ID errors 400,
`UPDATE_APP_TO_LOGIN` 406, and `AUTH_RESTART` 500.
[Primary method reference](https://core.telegram.org/method/auth.sendCode).

## User configuration diagnosis

The user confirmed enabling **Test Backend**. That selects a separate,
persistent test environment, explaining why its login request does not deliver
a code to the user's ordinary Telegram sessions. The checkbox must be turned
off manually for personal login; restarting the app retains the selection.

The screenshot's code-via-Telegram screen follows a server
`auth.sentCodeTypeApp` response. The mapping and resend protocol were unchanged.
At the time of that run the production RPC response was not observed.
The user's subsequent 2026-10-17 dev2 screenshot now confirms
`API_ID_PUBLISHED_FLOOD` on the personal-login path. This matches Telegram's
documented server restriction for the public sample API ID embedded in dev2.
An APK with the user's own API credentials and actual authenticated functional
checks is still required; making the rejection visible did not fix the API
configuration or establish a successful login.
[Primary authorization reference](https://core.telegram.org/api/auth).

## Independent validation

| Check | Result |
|---|---|
| Baseline dev1: eight login regression cases | Expected RED: five failures, three controls passed |
| Updated dev2: combined runtime/network/login cases | **PASS: 16/16**, 20.155 seconds, zero ignored |
| Production MTProto `help.getConfig` | **PASS**, DC 2, `test_mode=false`, 19 endpoints |
| Lifecycle | Visible Intro/login, task background/return, recreation and cleanup passed |
| App and test APK compilation | **PASS**, 1m 14s, 328 tasks |
| APK signature | **PASS**, v1 and v2, original MicControl certificate |
| Upgrade installation | **PASS**, same package/signing key, code 71759 → 71769 |
| Source whitespace | `git diff --check` passed |

Raw local evidence is preserved under ignored `artifacts/qa/`:
`login-errors-regression-real-codes-red.txt`, `dev2-all-tests-green.txt`,
`dev2-all-tests-green-logcat.txt`. The baseline was run before the product fix.
The updated combined suite ran after clearing data only on the dedicated test
emulator. Its hardware was Android 16 / API 36, arm64, 16 KiB pages, four CPU
cores and 4 GiB RAM.

## Verified artifact

- File: `artifacts/MicControl-arm64-dev2.apk`
- Application ID: `org.miccontrol.messenger.web`
- Version: `13.0.2-miccontrol-dev2`, code `71769`
- Size: 65,651,158 bytes; arm64; minimum SDK 23, target 36
- SHA-256: `c84836a10db8ad665eb972886978007dfbfafdc27cdc1f7632dc0dc96b268972`
- Signing certificate SHA-256: `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`

The original dev1 APK is retained separately. Both builds use the explicitly
enabled public sample API. These automated cases do not establish delivery of
a personal-account login code, message/media exchange, physical calls,
Bluetooth routing or audio quality. Runtime scenarios are tracked separately
in `miccontrol-usj`; device checks remain in `miccontrol-6w0`.

Subsequent test-account probes reached the code screen but could not authorize:
the documented test codes were rejected. An independent Telethon 1.45.0 client
reproduced that result on two test datacenters with the same public sample API.
The exact server-side cause remains unknown; the messaging E2E check is blocked
before login. Details and local evidence paths are recorded in
`tests/miccontrol/ANDROID_RUNTIME_TESTS.md`. The dev2 runtime run produced no
application crash or ANR; capture files are preserved in `artifacts/qa/`.

GitHub authentication was subsequently completed as DV-Design and all source
changes were successfully pushed to `DV-Design/MicControl-Telegram`, `main`,
at `8ea0d62`. The user's initial commit was preserved, and the final source
tree was verified identical after importing the shallow upstream snapshot.
The historical local source hash above was rewritten during this unpublished
history import. No private key, local API configuration or APK was committed.
