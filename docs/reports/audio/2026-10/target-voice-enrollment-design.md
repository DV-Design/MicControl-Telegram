# Target voice enrollment design

Date: 2026-10-20. Scope: source-based design only; no app, JNI, Gradle or device changes.
**Integration blocked:** the independent absent-owner reference C still lets speaker B through VoxLock. Correct A/B separation does not establish owner-only behavior. Neither this UI nor an inference-success flag resolves that quality defect. Android performance and owner-absence quality gates must pass before implementation.

Tracking: `miccontrol-m1b` covers the quality blocker; `miccontrol-ulk` covers the isolated native prototype. The existing call modes are not changed by this design.

Actual precision control (`artifacts/qa/target-voice/precision-control.json`) excludes quantization as the cause: enrolled C0 on B+C produces gain B=0.92866 / C=0.11174 with INT8-full and B=0.92826 / C=0.11197 with FP32. On B alone both variants preserve/amplify the impostor, approximately +0.649 dB. A separate correctly preprocessed speaker verifier identifies this wrong output in the small public corpus, but cannot restore C after the separator removes it. See the [independent verification review](../../code-reviews/2026-10/CR-2026-10-20-speaker-verification-diagnostic.md).

## Entry and user flow

Reuse `SettingsActivity.java:704,822` → `DanygrammSettings.show()` and add “Настроить мой голос”. Open a dedicated `BaseFragment`, so recording has a concrete owner and permission callback. Existing settings are an `AlertDialog`, which is unsuitable for retaining the recorder.

1. Explain: speak alone in a quiet place for three seconds; processing and profile stay on this phone. The derived profile is sensitive; do not promise it is irreversible.
2. Prepare fixed-revision, SHA-256-verified generic model assets on an existing `DispatchQueue`/worker before opening the microphone. Show size/progress, cancellation/retry and Wi-Fi by default, with explicit mobile-data consent.
3. Request `RECORD_AUDIO` in context, then show an explicit “Записать 3 секунды” button. No automatic recording after returning from permissions/settings/background.
4. Record with countdown, visible level and Cancel. Accumulate exactly 48,000 mono Float32 samples at 16 kHz; keep raw audio in bounded RAM only. Reject capture errors, silence and clipping as sample-quality failures, without claiming these checks establish speaker identity.
5. Stop and release the recorder, derive profile on the worker, discard raw buffers, then atomically commit the validated profile. Show Ready / Re-record / Delete. Cancelling a replacement preserves an older committed profile.

Do not reuse `MediaController.startRecording()`: its voice-message path creates a document, audio file and draft, with a possible `SendMessagesHelper` branch (`MediaController.java:4705,4885+`). Use platform `AudioRecord` directly behind a testable capture interface.

## Permissions and capture ownership

Use a distinct request code. Code `3` is intercepted by `BasePermissionsActivity.java:72-96`, and its successful branch returns before the fragment receives the result. `LaunchActivity.java:6692` routes other results to the current `BaseFragment.onRequestPermissionsResultFragment()`.

Gate setup with `VoIPService.getSharedState() != null` (`VoIPService.java:972`), which includes incoming pre-notification and group state. `isAnyKindOfCallActive()` at line 5681 excludes `STATE_WAITING_INCOMING`, so it is insufficient. Also reject `AudioManager.MODE_IN_CALL` / `MODE_IN_COMMUNICATION` and an in-app media capture lease.

Checks and notifications alone have a race: `voipServiceCreated` is posted at the end of `onStartCommand()` (line 964). Require a shared capture lease acquired before recorder allocation by enrollment and the actual call/media capture paths. Calls take priority: cancel enrollment and acknowledge recorder release before opening the call recorder. Do not block the main or audio thread waiting for worker completion. Existing call/record notifications remain secondary cancellation guards.

Platform audio focus controls output, not exclusive microphone ownership. On supported Android versions mark enrollment capture privacy-sensitive and watch silencing/device changes; stop instead of enrolling silence. [Android input-sharing documentation](https://developer.android.com/media/platform/sharing-audio-input).

## Lifetime and private storage

`BaseFragment.onPause()` (line 556), Back/Cancel, `onFragmentDestroy()` (line 509), call acquisition and account logout invalidate a session generation, stop/release capture and wipe raw Java/native buffers best-effort. A late, non-cancellable inference may finish but must discard its result. Recheck generation immediately before commit. Resume requires another explicit tap. Keep a previously committed profile on pause/cancel; remove it and native copies on its account's `NotificationCenter.appDidLogout` (`MessagesController.java:16166`).

Profile scope must include stable account identity, not only a reusable account slot. Switching account never loads another account's profile. Generic, public model assets can remain after logout.

The app manifest currently has `allowBackup=true` (line 100). Store profiles under `getNoBackupFilesDir()/target-voice/<account>/`, using `AtomicFile` and strict revision/hash/shape/length/finiteness validation. Do not put profile payload in SharedPreferences, cache exports, external storage, logs or crash attachments. Persist relative paths. `enroll_mag[1,257,376]` plus `context[1,512,298]` contains 996,832 Float32 payload bytes, not a small non-reconstructable embedding. Raw 3-second Float32 audio contains 192,000 bytes, plus bounded scratch buffers. [No-backup storage](https://developer.android.com/reference/android/content/Context#getNoBackupFilesDir()), [AtomicFile](https://developer.android.com/reference/android/util/AtomicFile).

## Minimal boundary after the gates

Java manager: `prepareModels`, `startEnrollment`, `cancel`, `deleteProfile`, account-bound observable status. The worker owns the ORT handle and buffers; no Activity references cross JNI.

JNI: `create(verified model paths)`, `enroll(float[48000]) → typed profile/status`, `loadProfile(validated payload)`, `process(input, output) → status`, `reset`, `close`. Store a versioned header binding the profile to exact model and preprocessing revisions.

Modes 0/1 retain current semantics. Without a valid profile, mode 2 must not display Ready or silently select RNNoise. If persisted mode 2 loses its profile/model, its output is blocked with a visible error and an explicit choice of another mode. On inference errors, underflow, stale profile or invalid output, clear the full output frame and return a fault; never copy input through. A successful inference alone does not prove that the owner was present.

## Focused validation after the gates

- Public-audio fixture injection, no host microphone or account: exact sample count, shape/finiteness, distinct owners, silence/clipping/short-input failure.
- Pause/cancel/logout during capture and inference; late callbacks cannot commit; double-start/close idempotence; no raw files; account-slot reuse; corrupt/truncated/mismatched profile.
- Atomic replacement/crash recovery and backup exclusion; an interrupted replacement preserves the older committed profile.
- Barrier-controlled call/enrollment race, including incoming ringing/pre-notification, group/video calls and media recording; at most one capture lease and no call delay on the UI thread.
- Fault injection verifies completely zeroed output on all mode-2 error/underflow paths, with original mode-0/1 behavior unchanged.
- Native UI checks for permission denial, cancel/retry/delete, progress, accessible controls and visible unavailable/error state. Actual microphone/device-route behavior remains a separate human-device check.
- Mandatory model-quality matrix includes absent owner, independent utterances, overlap, louder impostor, silence, language/channel changes and short-window behavior. No threshold or security guarantee follows from the current three-speaker diagnostic sample.
