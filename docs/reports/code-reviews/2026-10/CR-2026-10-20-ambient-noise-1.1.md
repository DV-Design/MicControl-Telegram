# Review: RNNoise spectral strength 1.6

Scope: `VoiceIsolationDenoiser.{h,cpp}`, RNNoise strength cap, and the native PCM
test harness. Decision: suitable for the user's prerelease audio trial; listening
on the physical phone remains in `miccontrol-6w0`.

The product default and both caps consistently use 1.6. The multiplier still
applies to the model's frequency gains; no uniform microphone gain, VAD expander,
new allocation, buffer, capture lock, Java/UI change or additional delay remains.
The ordinary RNNoise entry point retains strength 1.0 for existing group calls.
Mode switching, exact bypass and the normal WebRTC noise mode retain their paths.

Independent review compared all nine inputs and legacy 1.3 PCM outputs byte for
byte against the pre-change evidence. All matched. Candidate PCM is finite and
the recorded DSP hashes match the reviewed source. The final ASan/UBSan run passed
8/16/32/48 kHz mono/stereo, silence, Reset, 400 toggles and GRU allocation tracking.
The historical 1.3 synthetic-noise ratio remains 0.718265; the new default's
additional energy ratio is 0.746408. These are fixture measurements.

The material tradeoff is documented: some quiet onsets weaken, including a
20 ms clean-speech gain ratio of 0.9019. Overall speech gain and SI-SDR do not
establish consonant intelligibility. This is explicitly a prerelease, with no
physical-call or UI validation claim. The user requested manual UI testing.

Evidence and reproduction: [audio report](../../audio/2026-10/ambient-noise-spectral-evaluation.md).
No unresolved memory or integration defect was found in this small source change.
