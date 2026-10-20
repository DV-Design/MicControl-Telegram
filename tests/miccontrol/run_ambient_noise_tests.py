#!/usr/bin/env python3
"""Measure actual exp1.3 RNNoise/application PCM on pinned public speech/noise.

No target-speaker model inference, account, Android UI, output normalization or private
recording. --download-fixtures explicitly fetches only the three pinned ESC-50
WAVs; existing LibriSpeech FLACs are checked by SHA256. Audio stays Git-ignored.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
ESC_REVISION = "33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6"
SOURCES = {
    "A": ("6930-75918-0007.flac", "059969de8f6b780e1a4982805e977c3e73e40d3759c8fa8cb0cb8fabd9eb5b27"),
    "B": ("1320-122617-0012.flac", "6b5cd2c31ee61665ea0d81f2c76a1f2c32cb4f46e5ec5861bd9157e262785252"),
    "C": ("5639-40744-0002.flac", "111c6b8b19d093736570bced344035b48f75c770aacc60103da9d9a20f904fb2"),
}
NOISES = {
    "rain": ("1-17367-A-10.wav", "d732acd2e0c7c40405968010f49f250740c86998fc416eff2ed5330fc8c89dea"),
    "vacuum_cleaner": ("1-100210-A-36.wav", "f97e97b0fe0afce323d858503b6fa3ffd6c8cb1162c43cf3b24461300fb9abf6"),
    "keyboard_typing": ("1-137-A-32.wav", "d68e4716f74f073be8f78f5fe8e45daf7c09b0ec0575b21f57989d803536abb3"),
}
RATE = 48000
DELAY = 480  # bundled RNNoise analysis/synthesis has one 10ms frame of delay


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_hash(path, expected):
    if not Path(path).is_file() or digest(path) != expected:
        raise ValueError(f"Missing/changed pinned public audio: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech-dir", type=Path, default=ROOT / "artifacts/qa/target-voice/speech")
    parser.add_argument("--noise-dir", type=Path, default=ROOT / "artifacts/qa/ambient-noise/source")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--download-fixtures", action="store_true")
    parser.add_argument("--expect-wrapper-baseline", action="store_true",
                        help="before editing DSP, require application wrapper to equal exp1.3 bit for bit")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    if not __debug__ or sys.byteorder != "little":
        parser.error("Use little-endian host without python -O")
    out = args.output_dir.resolve()
    for target in (out, args.noise_dir.resolve()):
        try:
            relative = target.relative_to(ROOT)
        except ValueError:
            parser.error("Public raw/evidence files must stay in Git-ignored repository paths")
        if subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=ROOT).returncode:
            parser.error(f"Output is not Git-ignored: {target}")
    if (out / "result.json").exists():
        parser.error("Use a new output directory to preserve previous evidence")
    for name, expected in SOURCES.values():
        require_hash(args.speech_dir / name, expected)
    for name, expected in NOISES.values():
        path = args.noise_dir / name
        if not path.is_file() and args.download_fixtures:
            args.noise_dir.mkdir(parents=True, exist_ok=True)
            url = f"https://raw.githubusercontent.com/karolpiczak/ESC-50/{ESC_REVISION}/audio/{name}"
            path.write_bytes(urllib.request.urlopen(url).read())
        require_hash(path, expected)

    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.functional as audio
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    def energy(samples):
        return float(np.dot(samples.astype(np.float64), samples.astype(np.float64)))
    def rms(samples):
        return float(np.sqrt(energy(samples) / max(len(samples), 1)))
    def read48(path):
        samples, rate = sf.read(path, dtype="float32")
        assert samples.ndim == 1 and np.isfinite(samples).all()
        if rate != RATE:
            samples = audio.resample(torch.from_numpy(samples), rate, RATE,
                lowpass_filter_width=64, rolloff=.9475937167399596,
                resampling_method="sinc_interp_kaiser", beta=14.769656459379492).numpy()
        return samples.astype(np.float32)
    def normalized(samples, target):
        assert rms(samples) > 1e-8
        return (samples * (target / rms(samples))).astype(np.float32)
    def repeat_noise(samples, count):
        # 50ms overlap avoids manufactured clicks where a public 5s clip loops.
        overlap = 2400
        result = samples.copy()
        ramp = np.linspace(0, 1, overlap, dtype=np.float32)
        while len(result) < count:
            result[-overlap:] = result[-overlap:] * (1-ramp) + samples[:overlap] * ramp
            result = np.concatenate((result, samples[overlap:]))
        return result[:count]

    out.mkdir(parents=True, exist_ok=True)
    noise_audio = {label: normalized(read48(args.noise_dir / pair[0]), .06 / np.sqrt(10))
                   for label, pair in NOISES.items()}
    cases = []
    for (label, (speech_file, _)), noise_label in zip(SOURCES.items(), NOISES):
        voice = normalized(read48(args.speech_dir / speech_file), .06)
        silence = np.zeros(RATE, np.float32)
        clean = np.concatenate((silence, voice, silence, voice, silence))
        speech_regions = [(RATE, RATE + len(voice)), (2*RATE + len(voice), 2*RATE + 2*len(voice))]
        noise = repeat_noise(noise_audio[noise_label], len(clean))
        for name, source, kind in [(f"clean_{label}", clean, "clean"),
                                   (f"mixture_{label}_{noise_label}", clean+noise, "mixture")]:
            path = out / f"{name}-input.f32"
            (source * 32768).astype("<f4").tofile(path)
            clean_path = out / f"{name}-clean.f32"
            (clean * 32768).astype("<f4").tofile(clean_path)
            cases.append({"name": name, "kind": kind, "noise": noise_label if kind=="mixture" else None,
                "input": str(path), "clean": str(clean_path), "inputSamples": len(source),
                "speechRegions": speech_regions, "publicSpeech": speech_file})
    for noise_label, samples in noise_audio.items():
        name = f"noise_{noise_label}"
        source = repeat_noise(samples, 6*RATE)
        path = out / f"{name}-input.f32"; (source * 32768).astype("<f4").tofile(path)
        cases.append({"name":name, "kind":"noise", "noise":noise_label,
            "input":str(path), "inputSamples":len(source), "speechRegions":[]})
    command = [sys.executable, str(ROOT / "tests/miccontrol/run_native_tests.py")]
    if args.sanitize:
        command.append("--sanitize")
    for case in cases:
        command += ["--ambient-input", case["input"], "--ambient-output", str(out / case["name"])]
    with (out / "native.log").open("w") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    report = {"complete":False, "actualPcm":True, "outputNormalization":False,
        "baseline":"unchanged rnnoise_process_frame_strength(...,1.30f), same PCM/clamp",
        "sampleRate":RATE, "rnnoiseDelaySamples":DELAY,
        "scope":"host actual bundled RNNoise + application wrapper; no Android/UI or full APM claim",
        "noiseSourceCommit":ESC_REVISION,
        "sourceLicense":"LibriSpeech CC BY4.0; ESC-50 CC BY-NC3.0 (rain ESC-10 CC BY); research only, audio not packaged",
        "inputPreparation":"full public utterances at RMS.06; 1s silence before/between/after two repeats; 10dB SNR mixtures, 50ms noise loop overlap",
        "sourceHashes":{name:digest(args.speech_dir/name) for name,_ in SOURCES.values()},
        "noiseHashes":{name:digest(args.noise_dir/name) for name,_ in NOISES.values()},
        "dspSha256":digest(ROOT / "TMessagesProj/jni/voip/miccontrol/VoiceIsolationDenoiser.cpp"),
        "rnnoiseSha256":digest(ROOT / "TMessagesProj/jni/voip/rnnoise/src/denoise.c"),
        "versions":{name:importlib.metadata.version(name) for name in ("numpy","soundfile","torch","torchaudio")},
        "cases":[]}
    def compare(before,after,mask,reference=None):
        a=before[mask].astype(np.float64);b=after[mask].astype(np.float64)
        ea=energy(a);eb=energy(b)
        result={"samples":len(a), "baselineEnergy":ea, "candidateEnergy":eb}
        if ea>1e-18:
            result.update({"energyRatio":eb/ea,"rmsRatioDb":float(10*np.log10(max(eb,1e-30)/ea)),
                "cosine":float(np.dot(a,b)/np.sqrt(max(ea*eb,1e-30)))})
        if reference is not None:
            target=reference[mask].astype(np.float64)
            target_energy=energy(target)
            if target_energy>1e-18:
                gain_before=float(np.dot(a,target)/target_energy)
                gain_after=float(np.dot(b,target)/target_energy)
                result.update({"referenceGainBaseline":gain_before,"referenceGainCandidate":gain_after})
                if abs(gain_before)>1e-12:
                    result["referenceGainRatio"]=gain_after/gain_before
                centered=target-target.mean()
                def sisdr(value):
                    estimate=value-value.mean()
                    projected=np.dot(estimate,centered)/max(energy(centered),1e-30)*centered
                    return float(10*np.log10((energy(projected)+1e-30)/(energy(estimate-projected)+1e-30)))
                result.update({"siSdrBaselineDb":sisdr(a),"siSdrCandidateDb":sisdr(b)})
        return result
    for case in cases:
        name=case["name"]
        before=np.fromfile(out/f"{name}-baseline.f32",dtype="<f4")
        after=np.fromfile(out/f"{name}-candidate.f32",dtype="<f4")
        probability=np.fromfile(out/f"{name}-probability.f32",dtype="<f4")
        assert len(before)==len(after)==len(probability)*480 and np.isfinite(before).all() and np.isfinite(after).all()
        if args.expect_wrapper_baseline:
            assert np.array_equal(before,after), f"Before-edit wrapper differs from exp1.3: {name}"
        count=len(before)
        pause=np.zeros(count,bool); speech=np.zeros(count,bool)
        boundaries=[0]+[value for pair in case["speechRegions"] for value in pair]+[case["inputSamples"]]
        for index in range(0,len(boundaries)-1,2):
            start,end=boundaries[index:index+2]
            pause[start+RATE//2+DELAY:end+DELAY]=True
        row={**case,"inputSha256":digest(case["input"]), "baselineEqualsCandidate":bool(np.array_equal(before,after)),
            "pause":compare(before,after,pause), "outputSamples":count, "allFinite":True}
        prob_indices=np.nonzero(pause[DELAY:min(case["inputSamples"]+DELAY,count):480])[0]
        if len(prob_indices):
            row["pauseSpeechProbability"]={str(q):float(np.percentile(probability[prob_indices],q)) for q in (0,25,50,75,95,100)}
        if case["speechRegions"]:
            clean=np.fromfile(case["clean"],dtype="<f4")
            aligned_clean=np.pad(clean,(DELAY,count-len(clean)-DELAY))
            onsets=[]
            for start,end in case["speechRegions"]:
                voice=clean[start:end]
                frame_rms=np.sqrt((voice[:len(voice)//480*480].reshape(-1,480).astype(np.float64)**2).mean(1))
                active=frame_rms>max(rms(voice)*.08,1.)
                active=np.convolve(active.astype(int),np.ones(3,dtype=int),"same")>0
                for index,is_active in enumerate(active):
                    if is_active: speech[start+index*480+DELAY:start+(index+1)*480+DELAY]=True
                first=int(np.flatnonzero(frame_rms>max(rms(voice)*.05,1.))[0])*480
                onset=max(start,start+first-480)
                for milliseconds in (20,40,100,200):
                    mask=np.zeros(count,bool);mask[onset+DELAY:onset+DELAY+48*milliseconds]=True
                    onsets.append({"sourceOnsetSample":onset,"windowMs":milliseconds,**compare(before,after,mask,aligned_clean)})
            row["activeSpeech"]=compare(before,after,speech,aligned_clean)
            row["onsets"]=onsets
        report["cases"].append(row)
        print(json.dumps({"case":name,"baselineEqual":row["baselineEqualsCandidate"],
            "pauseRatioDb":row["pause"].get("rmsRatioDb"),
            "speechEnergyRatio":row.get("activeSpeech",{}).get("energyRatio"),
            "onsetMinEnergyRatio":min((item.get("energyRatio",1.) for item in row.get("onsets",[])),default=None)}),flush=True)
    report["complete"]=True
    (out/"result.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("Saved",out/"result.json",flush=True)


if __name__ == "__main__":
    main()
