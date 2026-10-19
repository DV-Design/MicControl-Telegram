#!/usr/bin/env python3
"""Run the actual bundled RNNoise and WebRTC sinc resampler on the host.

Requires Python 3 and clang/clang++ (or CC/CXX). Optional --sanitize enables
AddressSanitizer and UndefinedBehaviorSanitizer. Build files live in a temp dir.
"""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import wave
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--speech-wav", type=Path,
                        help="optional clean speech fixture: 48 kHz mono PCM16 WAV")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    jni = root / "TMessagesProj/jni"
    voip = jni / "voip"
    webrtc = voip / "webrtc"
    rnnoise = voip / "rnnoise"
    includes = [voip, webrtc, rnnoise / "include", jni / "third_party/absl"]
    flags = ["-O1", "-g", "-DWEBRTC_POSIX", "-DNDEBUG"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    c_sources = [rnnoise / "src" / name for name in (
        "celt_lpc.c", "denoise.c", "kiss_fft.c", "pitch.c", "rnn_data.c",
        "rnn_reader.c", "rnn.c")]
    cpp_sources = [
        voip / "miccontrol/VoiceIsolationDenoiser.cpp",
        webrtc / "common_audio/resampler/push_sinc_resampler.cc",
        webrtc / "common_audio/resampler/sinc_resampler.cc",
        webrtc / "common_audio/audio_util.cc",
        webrtc / "rtc_base/checks.cc",
        webrtc / "rtc_base/memory/aligned_malloc.cc",
        root / "tests/miccontrol/voice_isolation_test.cpp",
    ]
    # SincResampler selects its existing SSE implementation on x86 hosts.
    import platform
    if platform.machine().lower() in ("x86_64", "amd64", "i386", "i686"):
        cpp_sources += [webrtc / "common_audio/resampler/sinc_resampler_sse.cc",
                        webrtc / "system_wrappers/source/cpu_features.cc"]
    cc = shlex.split(os.environ.get("CC", "clang"))
    cxx = shlex.split(os.environ.get("CXX", "clang++"))
    with tempfile.TemporaryDirectory(prefix="miccontrol-audio-") as build:
        objects = []
        for index, source in enumerate(c_sources + cpp_sources):
            target = Path(build) / f"{index}.o"
            is_c = source.suffix == ".c"
            command = (cc if is_c else cxx) + flags
            command += ["-std=c11" if is_c else "-std=c++17"]
            if is_c:
                command += ["-DUSE_KISS_FFT", "-DHAVE_LRINT", "-DHAVE_LRINTF", "-DOPUS_BUILD"]
            if source.name == "denoise.c":
                command += ["-Dcalloc=miccontrol_test_calloc", "-Dfree=miccontrol_test_free"]
            command += [f"-I{include}" for include in includes]
            subprocess.run(command + ["-c", str(source), "-o", str(target)], check=True)
            objects.append(str(target))
        executable = str(Path(build) / "voice_isolation_test")
        subprocess.run(cxx + flags + objects + ["-o", executable], check=True)
        test_args = [executable]
        if args.speech_wav:
            with wave.open(str(args.speech_wav), "rb") as speech:
                if (speech.getframerate(), speech.getnchannels(), speech.getsampwidth(),
                        speech.getcomptype()) != (48000, 1, 2, "NONE"):
                    parser.error("--speech-wav must be uncompressed 48 kHz mono PCM16")
                pcm = speech.readframes(speech.getnframes())
            # The C++ runner receives actual PCM amplitudes, never normalized [-1, 1].
            raw = Path(build) / "speech.f32"
            with raw.open("wb") as output:
                for (sample,) in struct.iter_unpack("<h", pcm):
                    output.write(struct.pack("=f", float(sample)))
            test_args.append(str(raw))
        subprocess.run(test_args, check=True)


if __name__ == "__main__":
    main()
