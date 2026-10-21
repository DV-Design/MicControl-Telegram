#!/usr/bin/env python3
"""Research-only, real streaming GTCRN vs bundled RNNoise 1.6 on public PCM.

Run with the existing Torch venv; --stream-python selects the existing Sherpa
venv. No model export, Android/UI, account, private audio or output normalization.
Models and PCM stay in Git-ignored paths. See the accompanying evaluation report.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
import run_ambient_noise_tests as public_audio

ROOT = Path(__file__).resolve().parents[2]
GTCRN_COMMIT = "502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73"
MODEL_SHA = "e77603ac0c23dac3227dd2d7135b3a585cbee2679048aecfa886657d3ae1b534"
CHECKPOINT_SHA = "250fa2820ea9947704a62dda8e642ba773a067719c5e4294ad95aeab23f06442"
UPSTREAM_ONNX_SHA = "b4718df6228e7bdf1a8a435cf98f838636eb2fd331acabf86ba87c5192ebcb87"
RATE = 16000
RESAMPLE = dict(lowpass_filter_width=64, rolloff=.9475937167399596,
                resampling_method="sinc_interp_kaiser", beta=14.769656459379492)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def ignored(path):
    relative = Path(path).resolve().relative_to(ROOT)
    if subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=ROOT).returncode:
        raise ValueError(f"Evidence/models must stay Git-ignored: {path}")


def audit_checkpoint(source, out):
    """Only audited pinned modules; never execute the repository's old CLI."""
    import numpy as np
    import torch
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip() != GTCRN_COMMIT:
        raise ValueError("GTCRN source revision changed")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=source).returncode:
        raise ValueError("Pinned GTCRN tracked source files were modified")
    checkpoint = source / "stream/onnx_models/model_trained_on_dns3.tar"
    public_audio.require_hash(checkpoint, CHECKPOINT_SHA)
    # The older root checkpoint differs; the streaming export uses this one.
    sys.path.insert(0, str(source / "stream"))
    from gtcrn import GTCRN
    from gtcrn_stream import StreamGTCRN
    from modules.convert import convert_to_stream
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)["model"]
    model = GTCRN().eval()
    model.load_state_dict(state, strict=True)
    stream = StreamGTCRN().eval()
    convert_to_stream(stream, model)
    shapes = ((2, 1, 16, 16, 33), (2, 3, 1, 1, 16), (2, 1, 33, 16))
    caches = [torch.zeros(shape) for shape in shapes]
    specs = (np.random.default_rng(20261020).normal(size=(12, 1, 257, 1, 2)) * .3).astype(np.float32)
    outputs = []
    with torch.inference_mode():
        for frame in specs:
            result = stream(torch.from_numpy(frame), *caches)
            outputs.append(result[0].numpy())
            caches = list(result[1:])
    np.savez(out / "checkpoint-parity.npz", inputs=specs, output=np.stack(outputs),
             conv=caches[0].numpy(), tra=caches[1].numpy(), inter=caches[2].numpy())
    result = {"sourceCommit": GTCRN_COMMIT, "checkpointSha256": CHECKPOINT_SHA,
              "safeLoad": "torch.load(weights_only=True,map_location=cpu)", "strictKeys": len(state),
              "parameterNumelIncludingFixedErb": sum(t.numel() for t in model.parameters()),
              "learnableParameterNumel": sum(t.numel() for t in model.parameters() if t.requires_grad),
              "stateTensorNumelIncludingBuffers": sum(t.numel() for t in state.values()),
              "stateShapes": shapes}
    save(out / "checkpoint-audit.json", result)


def stream_phase(args):
    import ctypes
    import numpy as np
    import onnx
    import onnxruntime as ort
    import sherpa_onnx
    public_audio.require_hash(args.model, MODEL_SHA)
    upstream = args.source / "stream/onnx_models/gtcrn_simple.onnx"
    public_audio.require_hash(upstream, UPSTREAM_ONNX_SHA)
    exported = onnx.load(args.model)
    assert exported.graph.SerializeToString() == onnx.load(upstream).graph.SerializeToString()
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session = ort.InferenceSession(str(args.model), options, providers=["CPUExecutionProvider"])
    parity = np.load(args.output_dir / "checkpoint-parity.npz")
    caches = [np.zeros(tuple(i.shape), np.float32) for i in session.get_inputs()[1:]]
    estimates = []
    for frame in parity["inputs"]:
        values = session.run(None, dict(zip([i.name for i in session.get_inputs()], [frame, *caches])))
        estimates.append(values[0])
        caches = values[1:]
    error = {name: {"maxAbs": float(np.max(np.abs(a-b))), "rmse": float(np.sqrt(np.mean((a-b)**2)))}
             for name, a, b in [("output", np.stack(estimates), parity["output"]),
                                *[(k, x, parity[k]) for k, x in zip(("conv", "tra", "inter"), caches)]]}
    assert all(x["maxAbs"] < 2e-5 for x in error.values()), error
    config = sherpa_onnx.OnlineSpeechDenoiserConfig(model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
        gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=str(args.model)),
        num_threads=1, provider="cpu", debug=False))
    assert config.validate()
    denoiser = sherpa_onnx.OnlineSpeechDenoiser(config)
    assert denoiser.sample_rate == RATE and denoiser.frame_shift_in_samples == 256

    def run(samples, step=160, flush=True):
        output, sizes = [], []
        for start in range(0, len(samples), step):
            block = np.asarray(denoiser.run(samples[start:start+step], RATE).samples, dtype=np.float32)
            output.append(block); sizes.append(len(block))
        if flush:
            output.append(np.asarray(denoiser.flush().samples, dtype=np.float32))
        result = np.concatenate(output)
        assert np.isfinite(result).all()
        if flush:
            assert len(result) == len(samples), (len(result), len(samples))
        return result, sizes

    manifest = json.loads((args.output_dir / "inputs.json").read_text())
    checks = {}
    for case in manifest["cases"]:
        samples = np.fromfile(args.output_dir / (case["name"] + "-input16.f32"), dtype="<f4")
        denoiser.reset()
        enhanced, sizes = run(samples)
        enhanced.astype("<f4").tofile(args.output_dir / (case["name"] + "-gtcrn.f32"))
        if case["name"] == "clean_A":
            # flush resets state; chunk grouping and explicit reset must agree.
            repeated, _ = run(samples, 256)
            chunk_error = float(np.max(np.abs(repeated-enhanced)))
            assert chunk_error < 1e-6
            run(samples[:1600], flush=False)
            denoiser.reset()
            restarted, _ = run(samples)
            reset_error = float(np.max(np.abs(restarted-enhanced)))
            assert reset_error < 1e-6
            checks.update(chunkGroupingMaxAbs=chunk_error, resetMaxAbs=reset_error,
                          firstTenOutputBlockSizes=sizes[:10], flushResetsState=True)
        print(json.dumps({"gtcrn": case["name"], "samples": len(enhanced), "finite": True}), flush=True)
    # This is the runtime inside the Sherpa wheel, distinct from the ORT Python package.
    lib_path = Path(sherpa_onnx.__file__).parent / "lib/libonnxruntime.dylib"
    runtime = "unknown (inspect platform-specific Sherpa shared library)"
    if lib_path.exists():
        lib = ctypes.CDLL(str(lib_path)); lib.OrtGetApiBase.restype = ctypes.c_void_p
        class ApiBase(ctypes.Structure):
            _fields_ = [("get_api", ctypes.c_void_p), ("version", ctypes.CFUNCTYPE(ctypes.c_char_p))]
        runtime = ctypes.cast(lib.OrtGetApiBase(), ctypes.POINTER(ApiBase)).contents.version().decode()
    save(args.output_dir / "stream-checks.json", {"checkpointOnnxParity": error,
        "graphMatchesPinnedUpstream": True, "modelSha256": MODEL_SHA, "metadata": {m.key: m.value for m in exported.metadata_props},
        "versions": {n: importlib.metadata.version(n) for n in ("sherpa-onnx", "sherpa-onnx-core", "onnx", "onnxruntime")},
        "sherpaBundledOrtVersion": runtime, "streamFeedSamples": 160, "modelHopSamples": 256,
        "outputLengthEqualsInput": True, "allFinite": True, **checks})


def full_phase(args):
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.functional as audio
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    out = args.output_dir
    if (out / "inputs.json").exists():
        raise ValueError("Use a new directory; do not overwrite evidence")
    ignored(out); ignored(args.model)
    out.mkdir(parents=True, exist_ok=True)
    audit_checkpoint(args.source, out)

    def resample(x, source, target):
        return audio.resample(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)),
                              source, target, **RESAMPLE).numpy().astype(np.float32)

    def energy(x):
        x = x.astype(np.float64)
        return float(np.dot(x, x))

    def rms(x):
        return float(np.sqrt(energy(x) / max(len(x), 1)))

    def read(path, expected):
        public_audio.require_hash(path, expected)
        data, sr = sf.read(path, dtype="float32")
        assert data.ndim == 1 and np.isfinite(data).all()
        return data if sr == RATE else resample(data, sr, RATE)

    def loop(x, count):
        # Same 50ms overlap as the existing ambient harness.
        overlap = RATE // 20; ramp = np.linspace(0, 1, overlap, dtype=np.float32)
        result = x.copy()
        while len(result) < count:
            result[-overlap:] = result[-overlap:] * (1-ramp) + x[:overlap] * ramp
            result = np.concatenate((result, x[overlap:]))
        return result[:count]

    voices = {k: read(args.speech_dir / f, h) for k, (f, h) in public_audio.SOURCES.items()}
    noises = {k: read(args.noise_dir / f, h) for k, (f, h) in public_audio.NOISES.items()}
    cases = []

    def add(name, clean, noise, kind, speaker=None, noise_name=None, snr=None, regions=(), bursts=()):
        mixture = clean + noise
        # Leave headroom after upsampling too; apply identical common gain to clean/noise/input.
        peak48 = float(np.max(np.abs(resample(mixture, RATE, 48000))))
        scale = min(1., .90 / max(peak48, 1e-12))
        mixture = (mixture * scale).astype(np.float32); clean = (clean * scale).astype(np.float32)
        native = resample(mixture, RATE, 48000)
        assert float(np.max(np.abs(native))) <= .90001
        for suffix, value in (("input16", mixture), ("clean16", clean), ("input48", native*32768)):
            value.astype("<f4").tofile(out / f"{name}-{suffix}.f32")
        cases.append({"name": name, "kind": kind, "speaker": speaker, "noise": noise_name,
                      "snrDbDuringUtterance": snr, "inputSamples16k": len(mixture), "inputPeak": float(np.max(np.abs(mixture))),
                      "commonInputScale": scale, "speechRegions": regions, "loudBurstRegions": bursts,
                      "inputSha256": sha(out / f"{name}-input16.f32")})

    for label, voice in voices.items():
        voice = (voice * (.06 / rms(voice))).astype(np.float32)
        quiet = np.zeros(RATE, np.float32)
        clean = np.concatenate((quiet, voice, quiet))
        regions = [(RATE, RATE+len(voice))]
        add(f"clean_{label}", clean, np.zeros_like(clean), "clean", label, regions=regions)
        for noise_name, source in noises.items():
            noise = loop(source, len(clean))
            noise = (noise / rms(noise[RATE:RATE+len(voice)])).astype(np.float32)
            for snr in (10, 0, -10):
                add(f"snr{snr}_{label}_{noise_name}", clean, noise * (.06 / 10**(snr/20)),
                    "mixture", label, noise_name, snr, regions)
            # +10dB background with two -10dB, 400ms bursts during speech.
            envelope = np.full(len(clean), .06 / np.sqrt(10), np.float32)
            bursts = []
            for offset in (.5, 1.7):
                start = RATE + int(offset*RATE); end = min(start+6400, RATE+len(voice))
                ramp = np.ones(end-start, np.float32); fade = min(320, len(ramp)//2)
                ramp[:fade] = np.linspace(0, 1, fade); ramp[-fade:] = np.linspace(1, 0, fade)
                envelope[start:end] += ramp * (.06*np.sqrt(10)-.06/np.sqrt(10))
                bursts.append((start, end))
            add(f"bursts_{label}_{noise_name}", clean, noise*envelope, "bursts", label, noise_name,
                regions=regions, bursts=bursts)
    for noise_name, samples in noises.items():
        value = loop(samples, 5*RATE); value *= .06/rms(value)
        add(f"noise_{noise_name}", np.zeros_like(value), value, "noise", noise_name=noise_name)
    add("silence", np.zeros(2*RATE, np.float32), np.zeros(2*RATE, np.float32), "silence")
    manifest = {"sampleRate": RATE, "commonBandwidthHz": 8000, "cases": cases,
                "sourceHashes": {f: h for f, h in [*public_audio.SOURCES.values(), *public_audio.NOISES.values()]}}
    save(out / "inputs.json", manifest)
    command = [sys.executable, str(ROOT / "tests/miccontrol/run_native_tests.py")]
    for case in cases:
        command += ["--ambient-input", str(out / (case["name"]+"-input48.f32")),
                    "--ambient-output", str(out / case["name"])]
    with (out / "rnnoise-native.log").open("w") as log:
        subprocess.run(command, check=True, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    subprocess.run([str(args.stream_python), str(Path(__file__).resolve()), "--stream-only",
                    "--output-dir", str(out), "--model", str(args.model), "--source", str(args.source)], check=True, cwd=ROOT)
    score_phase(args)


def score_phase(args):
    """Score saved PCM; rerunning metrics never repeats model inference."""
    import numpy as np
    import torch
    import torchaudio.functional as audio
    torch.set_num_threads(1)
    out = args.output_dir
    manifest = json.loads((out / "inputs.json").read_text())
    cases = manifest["cases"]
    additional_provenance = {}
    for name, directory in args.additional_candidates:
        proof_path = directory / "manifest.json"
        proof = json.loads(proof_path.read_text())
        if proof.get("complete") is not True or proof.get("inputManifestSha256") != sha(out / "inputs.json"):
            raise ValueError(f"Additional model manifest does not match these inputs: {name}")
        proof_cases = {c["name"]: c for c in proof["cases"]}
        if len(proof_cases) != len(cases):
            raise ValueError(f"Additional model manifest case count differs: {name}")
        for case in cases:
            row = proof_cases[case["name"]]
            if row["input16Sha256"] != case["inputSha256"] or row["outputSha256"] != sha(directory / f"{case['name']}-{name}.f32"):
                raise ValueError(f"Additional model PCM hash differs: {name}/{case['name']}")
        additional_provenance[name] = {"manifestSha256": sha(proof_path),
                                       "binary": proof.get("binary"), "model": proof.get("model"),
                                       "fixedDelay48kSamples": proof.get("fixedDelay48kSamples"),
                                       "cliOutputFormat": proof.get("cliOutputFormat")}

    def resample(x, source, target):
        return audio.resample(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)),
                              source, target, **RESAMPLE).numpy().astype(np.float32)

    def energy(x):
        x = x.astype(np.float64)
        return float(np.dot(x, x))

    def rms(x):
        return float(np.sqrt(energy(x) / max(len(x), 1)))

    def gain(x, y):
        return float(np.dot(x.astype(np.float64), y.astype(np.float64)) / max(energy(y), 1e-30))

    def sisdr(x, reference):
        x = x.astype(np.float64); reference = reference.astype(np.float64)
        x = x-x.mean(); reference = reference-reference.mean()
        target = gain(x, reference) * reference
        return float(10*np.log10((energy(target)+1e-30)/(energy(x-target)+1e-30)))

    prepared = {}
    for case in cases:
        name = case["name"]; count = case["inputSamples16k"]
        raw = np.fromfile(out / (name+"-candidate.f32"), dtype="<f4") / 32768
        # Fixed, documented RNNoise delay at 48k; no mixture-dependent alignment.
        rn = resample(raw[480:480+count*3], 48000, RATE)[:count]
        gt = np.fromfile(out / (name+"-gtcrn.f32"), dtype="<f4")
        clean = np.fromfile(out / (name+"-clean16.f32"), dtype="<f4")
        inp = np.fromfile(out / (name+"-input16.f32"), dtype="<f4")
        if sha(out / (name+"-input16.f32")) != case["inputSha256"]:
            raise ValueError(f"Saved input PCM hash changed: {name}")
        assert len(rn) == len(gt) == len(clean) == len(inp) == count
        assert np.isfinite(rn).all() and np.isfinite(gt).all()
        rn.astype("<f4").tofile(out / (name+"-rnnoise16.f32"))
        prepared[name] = (inp, clean, rn, gt)
    # One clean A calibration only, subsequently frozen for every noisy case.
    _, calibration, rn_cal, gt_cal = prepared["clean_A"]
    def calibration_lag(estimate):
        scores = []
        for lag in range(-128, 129):
            a = estimate[max(lag, 0):len(estimate)+min(lag, 0)]
            b = calibration[max(-lag, 0):len(calibration)-max(lag, 0)]
            scores.append(float(np.dot(a.astype(np.float64), b.astype(np.float64))))
        return int(np.argmax(scores)-128)
    lags = {"rnnoiseAfterFixed10msTrim": calibration_lag(rn_cal), "gtcrnLibraryAlignedOutput": calibration_lag(gt_cal)}
    for name, directory in args.additional_candidates:
        sample = np.fromfile(directory / f"clean_A-{name}.f32", dtype="<f4")
        if len(sample) != len(calibration) or not np.isfinite(sample).all():
            raise ValueError(f"Invalid clean calibration output: {name}")
        lags[name+"AlreadyFixedDelayAligned"] = calibration_lag(sample)
    assert all(lag == 0 for lag in lags.values()), lags

    results = []
    for case in cases:
        inp, clean, rn, gt = prepared[case["name"]]; count = len(inp)
        candidates = [("rnnoise1.6", rn), ("gtcrn", gt)]
        output_paths = {"rnnoise1.6": out / (case["name"]+"-rnnoise16.f32"),
                        "gtcrn": out / (case["name"]+"-gtcrn.f32")}
        for name, directory in args.additional_candidates:
            path = directory / f"{case['name']}-{name}.f32"
            samples = np.fromfile(path, dtype="<f4")
            if len(samples) != count or not np.isfinite(samples).all():
                raise ValueError(f"Additional candidate must be finite, aligned 16k PCM: {path}")
            candidates.append((name, samples)); output_paths[name] = path
        active = np.zeros(count, bool); pause = np.ones(count, bool)
        onset = None
        for start, end in case["speechRegions"]:
            pause[max(0, start-3200):min(count, end+3200)] = False
            voice = clean[start:end]; blocks = len(voice)//160
            levels = np.sqrt(np.mean(voice[:blocks*160].reshape(-1, 160).astype(np.float64)**2, axis=1))
            mask = levels > max(rms(voice)*.08, 3e-5)
            mask = np.convolve(mask.astype(int), np.ones(3, int), "same") > 0
            active[start:start+blocks*160] = np.repeat(mask, 160)
            onset = start + int(np.flatnonzero(levels > max(rms(voice)*.05, 3e-5))[0])*160
        pause[:RATE//2] = False  # startup excluded from the steady pause metric
        row = dict(case)
        row["outputSha256"] = {name: sha(path) for name, path in output_paths.items()}
        row["models"] = {}
        for model, samples in candidates:
            values = {"outputRms": rms(samples), "outputPeak": float(np.max(np.abs(samples))),
                      "pauseRms": rms(samples[pause]), "pauseAttenuationDb":
                      float(10*np.log10((energy(inp[pause])+1e-30)/(energy(samples[pause])+1e-30)))
                      if energy(inp[pause]) > 1e-20 else None}
            if active.any():
                values.update(activeReferenceGain=gain(samples[active], clean[active]),
                              siSdrDb=sisdr(samples[active], clean[active]),
                              inputSiSdrDb=sisdr(inp[active], clean[active]))
                values["siSdrImprovementDb"] = values["siSdrDb"]-values["inputSiSdrDb"]
                values["onsets"] = [{"windowMs": ms, "referenceGain": gain(samples[onset:onset+ms*16], clean[onset:onset+ms*16]),
                                      "siSdrDb": sisdr(samples[onset:onset+ms*16], clean[onset:onset+ms*16])} for ms in (20, 40, 100, 200)]
                windows = []
                for start in range(0, count-1600+1, 800):
                    ref = clean[start:start+1600]
                    if rms(ref) > rms(clean)*.25 and active[start:start+1600].mean() > .8:
                        windows.append(gain(samples[start:start+1600], ref))
                values["active100msGain"] = {"count": len(windows), "min": min(windows),
                    "p10": float(np.percentile(windows, 10)), "fractionBelowHalf": float(np.mean(np.array(windows)<.5))}
                if case["loudBurstRegions"]:
                    burst = np.zeros(count, bool)
                    for start, end in case["loudBurstRegions"]: burst[start:end] = True
                    burst &= active
                    values["loudBurst"] = {"referenceGain": gain(samples[burst], clean[burst]),
                        "siSdrDb": sisdr(samples[burst], clean[burst]), "inputSiSdrDb": sisdr(inp[burst], clean[burst])}
                    recovery = []
                    for _, end in case["loudBurstRegions"]:
                        for ms in (100, 200):
                            stop = min(count, end+ms*16)
                            mask = active[end:stop]
                            if not mask.any():
                                continue
                            ref = clean[end:stop][mask]; estimate = samples[end:stop][mask]
                            # Numerical near-zero energy is separate from the gain<.5 suppression proxy.
                            zero = []
                            for start in range(end, stop-160+1, 160):
                                target = clean[start:start+160]
                                if active[start:start+160].mean() > .8 and rms(target) > rms(clean)*.25:
                                    zero.append(energy(samples[start:start+160]) < max(1e-20, energy(target)*1e-8))
                            recovery.append({"burstEndSample": end, "windowMs": ms,
                                             "referenceGain": gain(estimate, ref),
                                             "active10msWindows": len(zero),
                                             "nearZeroEnergyFraction": float(np.mean(zero)) if zero else None})
                    values["postBurstRecovery"] = recovery
            row["models"][model] = values
        results.append(row)
        print(json.dumps({"case": case["name"], "rnSiSdr": row["models"]["rnnoise1.6"].get("siSdrDb"),
                          "gtSiSdr": row["models"]["gtcrn"].get("siSdrDb")}), flush=True)
    report = {"complete": True, "actualStreamingPcm": True, "outputNormalization": False,
              "scope": "standalone denoisers; full APM NS/AGC/echo, Bluetooth, physical device and UI NOT tested",
              "sampleRate": RATE, "commonBandwidthHz": 8000, "referenceAlignment": lags,
              "rnnoiseFixedDelaySamplesAt48k": 480, "gtcrnAlignment": "Sherpa drops initial OLA hop, returns input-aligned waveform; no noisy-case delay fitting",
              "sourceCommit": GTCRN_COMMIT, "noiseCommit": public_audio.ESC_REVISION,
              "inputPreparation": "full utterance RMS.06, 1s leading/trailing pauses; all 3 speakers x all 3 noises; SNR over full utterance; common headroom scale max.90 including 48k reconstruction",
              "resampling": RESAMPLE, "speechLicense": "LibriSpeech CC BY4.0", "noiseLicense": "ESC-50 CC BY-NC3.0, rain ESC-10 CC BY; research only",
              "sourceHashes": manifest["sourceHashes"], "sourceFileHashes": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(),
                  ROOT / "tests/miccontrol/run_native_tests.py", ROOT / "tests/miccontrol/voice_isolation_test.cpp",
                  ROOT / "TMessagesProj/jni/voip/miccontrol/VoiceIsolationDenoiser.cpp", ROOT / "TMessagesProj/jni/voip/rnnoise/src/denoise.c"]},
              "versions": {n: importlib.metadata.version(n) for n in ("torch", "torchaudio", "numpy", "soundfile", "einops")},
              "streamChecks": json.loads((out / "stream-checks.json").read_text()), "cases": results}
    report["additionalCandidates"] = [{"name": name, "directory": str(directory),
        **additional_provenance[name],
        "contract": "already fixed-delay-aligned mono16k normalized float32; no output normalization; inference/provenance in candidate's separate report"}
        for name, directory in args.additional_candidates]
    save(out / args.result_name, report)
    print("Saved", out / args.result_name, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / ".tmp/current/gtcrn-official")
    parser.add_argument("--model", type=Path, default=ROOT / ".local/target-voice/gtcrn-502ebfa/gtcrn-sherpa.onnx")
    parser.add_argument("--stream-python", type=Path, default=ROOT / ".local/tse-venv/bin/python")
    parser.add_argument("--speech-dir", type=Path, default=ROOT / "artifacts/qa/target-voice/speech")
    parser.add_argument("--noise-dir", type=Path, default=ROOT / "artifacts/qa/ambient-noise/source")
    parser.add_argument("--stream-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--score-only", action="store_true", help="recalculate metrics from existing PCM without inference")
    parser.add_argument("--additional-model", action="append", default=[], metavar="NAME=DIRECTORY",
                        help="score existing <case>-<NAME>.f32 aligned mono16k PCM; does not run the additional model")
    parser.add_argument("--result-name", default="result.json", help="JSON basename, for preserving earlier comparisons")
    args = parser.parse_args()
    for name in ("output_dir", "source", "model", "speech_dir", "noise_dir"):
        setattr(args, name, getattr(args, name).resolve())
    # Resolving a venv's Python symlink loses pyvenv.cfg and selects the base environment.
    args.stream_python = args.stream_python.absolute()
    args.additional_candidates = []
    for item in args.additional_model:
        name, separator, directory = item.partition("=")
        if not separator or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in {"gtcrn", "rnnoise1.6"}:
            parser.error("Additional model syntax: unique lowercase NAME=DIRECTORY")
        if name in {n for n, _ in args.additional_candidates}:
            parser.error("Duplicate additional model name")
        directory = Path(directory).resolve(); ignored(directory)
        args.additional_candidates.append((name, directory))
    if Path(args.result_name).name != args.result_name or not args.result_name.endswith(".json"):
        parser.error("--result-name must be a JSON basename")
    if not __debug__ or sys.byteorder != "little":
        parser.error("Use little-endian Python without -O")
    ignored(args.output_dir); ignored(args.model)
    if args.stream_only and args.score_only:
        parser.error("Choose only one partial phase")
    (stream_phase if args.stream_only else score_phase if args.score_only else full_phase)(args)


if __name__ == "__main__":
    main()
