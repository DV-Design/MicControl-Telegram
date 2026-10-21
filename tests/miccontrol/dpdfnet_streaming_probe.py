#!/usr/bin/env python3
"""Pinned official DPDFNet 48k streaming PCM research; no app/Android/UI.

Use the Torch venv for the default orchestration/resampling phase, and the
existing Sherpa venv for --phase stream. Inputs are the unchanged 43-case public
manifest. No output gain normalization, model export or parameter tuning.
"""
import argparse
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "9bd9844a227bb6aa57e55588d8d0e961fcff1c46"
HF_COMMIT = "dd6818d00f50c836fed43a6243ebe49116de5964"
INPUT_MANIFEST_SHA = "c4bca5c8a8bf23b654dd96ca180660aaae3fe5f3f19a85c90e0c4ba198a48877"
MODELS = {
    "2": ("dpdfnet2_48khz_hr", "7f0575a5cec0ba4ffd8f8bd657e06d007e4ccdd955d76faab922b9d3291dc14b", 10493337),
    "8": ("dpdfnet8_48khz_hr", "7b3afbb260a08fe9af3d16e3bda992971be1e7e951d1dee7c2d235f5c43f5631", 14857107),
}
SMOKE = ("clean_A", "clean_B", "bursts_A_vacuum_cleaner", "snr-10_B_rain", "noise_vacuum_cleaner")
RESAMPLE = dict(lowpass_filter_width=64, rolloff=.9475937167399596,
                resampling_method="sinc_interp_kaiser", beta=14.769656459379492)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def require_ignored(path):
    relative = Path(path).resolve().relative_to(ROOT)
    if subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=ROOT).returncode:
        raise ValueError(f"Models/evidence must remain Git-ignored: {path}")


def selected_cases(args):
    if sha(args.input_manifest) != INPUT_MANIFEST_SHA:
        raise ValueError("Public input manifest changed")
    data = json.loads(args.input_manifest.read_text())
    return [c for c in data["cases"] if not args.smoke or c["name"] in SMOKE]


def bundled_ort():
    import sherpa_onnx
    lib = Path(sherpa_onnx.__file__).parent / "lib/libonnxruntime.dylib"
    if not lib.exists():
        return "inspect platform-specific bundled shared library"
    loaded = ctypes.CDLL(str(lib)); loaded.OrtGetApiBase.restype = ctypes.c_void_p
    class ApiBase(ctypes.Structure):
        _fields_ = [("api", ctypes.c_void_p), ("version", ctypes.CFUNCTYPE(ctypes.c_char_p))]
    return ctypes.cast(loaded.OrtGetApiBase(), ctypes.POINTER(ApiBase)).contents.version().decode()


def stream_phase(args):
    import numpy as np
    import onnx
    import sherpa_onnx
    if (args.output_dir / "raw-manifest.json").exists():
        raise ValueError("Use a new output directory; raw evidence is immutable")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    name, expected, size = MODELS[args.variant]
    if sha(args.model) != expected or args.model.stat().st_size != size:
        raise ValueError("Pinned official HF model hash/size mismatch")
    model = onnx.load(args.model)
    metadata = {p.key: p.value for p in model.metadata_props}
    # The pinned HF eight-block file is mislabeled as the two-block profile.
    # Keep its bytes unchanged; SHA and independently checked state size identify
    # the actual model. Both files passed strict checkpoint/12-frame parity.
    expected_state = {"2": 56436, "8": 90228}[args.variant]
    if metadata["profile"] != "dpdfnet2_48khz_hr" or int(metadata["state_size"]) != expected_state or int(metadata["sample_rate"]) != 48000 or int(metadata["hop_length"]) != 480:
        raise ValueError("Unexpected model contract")
    # Official Sherpa supports namespaced ORT SessionConfig through a provider file.
    # It is not the DPDFNet offline attenuation config. Online limit is ignored;
    # zero is explicitly the documented full-suppression configuration.
    config_path = args.output_dir / "cpu-no-spinning.conf"
    config_path.write_text("SessionConfig.session.intra_op.allow_spinning=0\n"
                           "SessionConfig.session.inter_op.allow_spinning=0\nDEBUG=1\n")
    config = sherpa_onnx.OnlineSpeechDenoiserConfig(model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
        dpdfnet=sherpa_onnx.OfflineSpeechDenoiserDpdfNetModelConfig(model=str(args.model), attenuation_limit_db=0),
        num_threads=1, provider="cpu:"+str(config_path), debug=False))
    if not config.validate():
        raise ValueError("Sherpa config rejected")
    begin = time.perf_counter()
    denoiser = sherpa_onnx.OnlineSpeechDenoiser(config)
    init_ms = (time.perf_counter()-begin)*1000
    assert denoiser.sample_rate == 48000 and denoiser.frame_shift_in_samples == 480
    reused = None
    if args.reuse_raw_dir:
        reused = json.loads((args.reuse_raw_dir / "raw-manifest.json").read_text())
        if not reused["complete"] or reused["model"]["sha256"] != expected or reused["inputManifestSha256"] != INPUT_MANIFEST_SHA:
            raise ValueError("Reuse manifest does not match this model/input")
        reused = {row["name"]: row for row in reused["cases"]}
    rows = []
    for case in selected_cases(args):
        source_path = args.input_manifest.parent / (case["name"]+"-input48.f32")
        if sha(args.input_manifest.parent / (case["name"]+"-input16.f32")) != case["inputSha256"]:
            raise ValueError("Saved input16 hash changed")
        target = args.output_dir / (case["name"]+"-raw48.f32")
        if reused and case["name"] in reused:
            row = reused[case["name"]]
            old = args.reuse_raw_dir / target.name
            if row["input48Sha256"] != sha(source_path) or row["rawSha256"] != sha(old):
                raise ValueError("Reuse PCM hash mismatch")
            shutil.copyfile(old, target)
            rows.append({**row, "reusedFrom": str(old)})
            continue
        samples = np.fromfile(source_path, dtype="<f4") / 32768
        assert len(samples) == case["inputSamples16k"]*3 and np.isfinite(samples).all()
        assert float(np.max(np.abs(samples))) < .901
        # 100ms drain keeps all model/OLA delayed samples; no loopback or private data.
        samples = np.concatenate((samples, np.zeros(4800, np.float32)))
        denoiser.reset()
        blocks, sizes, times = [], [], []
        for start in range(0, len(samples), 480):
            begin = time.perf_counter()
            value = denoiser.run(samples[start:start+480], 48000)
            times.append((time.perf_counter()-begin)*1000)
            block = np.asarray(value.samples, dtype=np.float32)
            blocks.append(block); sizes.append(len(block))
        blocks.append(np.asarray(denoiser.flush().samples, dtype=np.float32))
        result = np.concatenate(blocks)
        assert len(result) == len(samples) and np.isfinite(result).all()
        result.astype("<f4").tofile(target)
        row = {"name": case["name"], "input16Sha256": case["inputSha256"], "input48Sha256": sha(source_path),
               "inputSamples16k": case["inputSamples16k"], "rawSamples48k": len(result), "rawSha256": sha(target),
               "firstTenOutputBlockSizes": sizes[:10], "flushSamples": len(blocks[-1]),
               "processingMs": {"p50": float(np.percentile(times, 50)), "p95": float(np.percentile(times, 95)),
                    "p99": float(np.percentile(times, 99)), "max": max(times), "sum": sum(times)},
               "processingBlockMs": times}
        rows.append(row)
        print(json.dumps({"streamingCase": case["name"], "variant": name, "rawSamples": len(result),
                          "p95HostMs": row["processingMs"]["p95"]}), flush=True)
    save(args.output_dir / "raw-manifest.json", {"complete": True, "sourceCommit": SOURCE_COMMIT,
        "inputManifestSha256": INPUT_MANIFEST_SHA, "model": {"name": name, "sha256": expected, "bytes": size,
            "url": f"https://huggingface.co/Ceva-IP/DPDFNet/resolve/{HF_COMMIT}/onnx/{name}.onnx", "hfCommit": HF_COMMIT,
            "metadata": metadata, "license": "Apache-2.0 (official model card)"},
        "binary": {"sherpaVersion": importlib.metadata.version("sherpa-onnx"), "bundledOrtVersion": bundled_ort(),
                   "numThreads": 1, "intraOpAllowSpinning": 0, "interOpAllowSpinning": 0},
        "modelInitMsExcludedFromProcessing": init_ms,
        "timingScope": "host library call wall time only, not Android/phone performance; copies/DFT included, model construction excluded",
        "onlineAttenuationLimitDb": 0, "onlineAttenuation": "not applied by official online implementation; full suppression",
        "inputFeedSamples48k": 480, "appendedZeroTailSamples48k": 4800, "cases": rows})


def finalize_phase(args):
    import numpy as np
    import torch
    import torchaudio.functional as audio
    torch.set_num_threads(1)
    raw = json.loads((args.output_dir / "raw-manifest.json").read_text())
    if not raw["complete"] or raw["model"]["sha256"] != MODELS[args.variant][1]:
        raise ValueError("Raw manifest incomplete/model mismatch")
    raw_cases = {case["name"]: case for case in raw["cases"]}
    ref = np.fromfile(args.input_manifest.parent / "clean_A-input48.f32", dtype="<f4") / 32768
    estimate = np.fromfile(args.output_dir / "clean_A-raw48.f32", dtype="<f4")
    # One CLEAN calibration per model. Positive lag means actual model output
    # delayed relative to input. Never fit a noisy case independently.
    nfft = 1 << (len(ref)+len(estimate)-1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(estimate, nfft)*np.conj(np.fft.rfft(ref, nfft)), nfft)
    candidates = np.arange(-4800, 4801)
    lag = int(candidates[np.argmax(corr[candidates % nfft])])
    if lag < 0 or lag >= 4800:
        raise ValueError(f"Unexpected calibration delay: {lag}")
    name = "dpdfnet"+args.variant+"_hr"
    rows = []
    for case in selected_cases(args):
        raw_path = args.output_dir / (case["name"]+"-raw48.f32")
        if sha(raw_path) != raw_cases[case["name"]]["rawSha256"]:
            raise ValueError("Raw output was modified")
        samples = np.fromfile(raw_path, dtype="<f4")
        length = case["inputSamples16k"]
        aligned = samples[lag:lag+length*3]
        value = audio.resample(torch.from_numpy(aligned), 48000, 16000, **RESAMPLE).numpy()
        assert len(value) == length and np.isfinite(value).all()
        target = args.output_dir / (case["name"]+"-"+name+".f32")
        value.astype("<f4").tofile(target)
        rows.append({"name": case["name"], "input16Sha256": case["inputSha256"],
                     "input48Sha256": raw_cases[case["name"]]["input48Sha256"],
                     "outputSha256": sha(target), "outputSamples16k": length})
    report = {"complete": True, "inputManifestSha256": INPUT_MANIFEST_SHA, "inputManifest": str(args.input_manifest),
              "binary": raw["binary"], "model": raw["model"], "rawManifestSha256": sha(args.output_dir / "raw-manifest.json"),
              "fixedDelay48kSamples": lag, "calibration": "clean_A once, shared for every selected case; no noisy-case delay fitting",
              "cliOutputFormat": "float32 direct Sherpa library, no WAV quantization", "outputNormalization": False,
              "outputResample": RESAMPLE, "cases": rows}
    # Small early summary on the exact same active/onset definitions as the shared scorer.
    baseline = json.loads((args.input_manifest.parent / "result-with-dfn3.json").read_text())
    base = {c["name"]: c for c in baseline["cases"]}; summary = []
    for case in selected_cases(args):
        length = case["inputSamples16k"]
        clean = np.fromfile(args.input_manifest.parent / (case["name"]+"-clean16.f32"), dtype="<f4")
        x = np.fromfile(args.output_dir / (case["name"]+"-"+name+".f32"), dtype="<f4")
        if not case["speechRegions"]:
            inp = np.fromfile(args.input_manifest.parent / (case["name"]+"-input16.f32"), dtype="<f4")
            summary.append({"name": case["name"], "noiseAttenuationDb": float(10*np.log10((np.dot(inp[8000:].astype(float),inp[8000:].astype(float))+1e-30)/(np.dot(x[8000:].astype(float),x[8000:].astype(float))+1e-30)))})
            continue
        active = np.zeros(length, bool)
        for start, end in case["speechRegions"]:
            voice = clean[start:end]; n = len(voice)//160
            rms = float(np.sqrt(np.mean(voice.astype(float)**2)))
            levels = np.sqrt(np.mean(voice[:n*160].reshape(-1,160).astype(float)**2,axis=1))
            mask = np.convolve((levels>max(rms*.08,3e-5)).astype(int),np.ones(3,int),"same")>0
            active[start:start+n*160] = np.repeat(mask,160)
            onset = start+int(np.flatnonzero(levels>max(rms*.05,3e-5))[0])*160
        a=x[active].astype(float);b=clean[active].astype(float);gain=float(np.dot(a,b)/np.dot(b,b))
        a-=a.mean();b-=b.mean();p=np.dot(a,b)/np.dot(b,b)*b
        sisdr=float(10*np.log10((np.dot(p,p)+1e-30)/(np.dot(a-p,a-p)+1e-30)))
        target=clean[onset:onset+1600].astype(float);z=x[onset:onset+1600].astype(float)
        summary.append({"name":case["name"],"siSdrDb":sisdr,"referenceGain":gain,
                        "onset100msGain":float(np.dot(z,target)/np.dot(target,target)),
                        "baselineModels":base[case["name"]]["models"]})
    report["earlySummary"] = summary
    save(args.output_dir / "manifest.json", report)
    print(json.dumps({"variant":name,"fixedDelaySamples48k":lag,"completeCases":len(rows),
                      "earlySummary":[{k:v for k,v in row.items() if k!='baselineModels'} for row in summary]},indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant",choices=MODELS,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--input-manifest",type=Path,default=ROOT/"artifacts/qa/gtcrn/matrix-43/inputs.json")
    parser.add_argument("--model",type=Path)
    parser.add_argument("--stream-python",type=Path,default=ROOT/".local/tse-venv/bin/python")
    parser.add_argument("--phase",choices=("all","stream","finalize"),default="all")
    parser.add_argument("--smoke",action="store_true",help="five fixed cases; not another matrix")
    parser.add_argument("--reuse-raw-dir",type=Path,help="reuse exact-model/input checked raw smoke cases")
    args=parser.parse_args()
    args.output_dir=args.output_dir.resolve();args.input_manifest=args.input_manifest.resolve()
    args.model=(args.model or ROOT/(".local/target-voice/"+MODELS[args.variant][0]+"-hf.onnx")).resolve()
    args.stream_python=args.stream_python.absolute()
    if args.reuse_raw_dir: args.reuse_raw_dir=args.reuse_raw_dir.resolve()
    if not __debug__ or sys.byteorder!='little': parser.error("Use little-endian Python without -O")
    require_ignored(args.output_dir);require_ignored(args.model);selected_cases(args)
    if args.phase=="stream": stream_phase(args)
    elif args.phase=="finalize": finalize_phase(args)
    else:
        command=[str(args.stream_python),str(Path(__file__).resolve()),"--phase","stream","--variant",args.variant,
                 "--output-dir",str(args.output_dir),"--input-manifest",str(args.input_manifest),"--model",str(args.model)]
        if args.smoke: command.append("--smoke")
        if args.reuse_raw_dir:command += ["--reuse-raw-dir",str(args.reuse_raw_dir)]
        subprocess.run(command,check=True,cwd=ROOT)
        finalize_phase(args)


if __name__=="__main__":main()
