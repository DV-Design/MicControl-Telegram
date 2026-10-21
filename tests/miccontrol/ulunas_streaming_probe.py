#!/usr/bin/env python3
"""Official UL-UNAS ONNX with bounded frame-wise Hann STFT/normalized OLA.

Research only. NumPy supplies FFT and ORT supplies the entire neural network.
The small streaming buffer is checked against the official Torch STFT/iSTFT
contract, including Hann-squared reconstruction weights. No model export.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from dpdfnet_streaming_probe import INPUT_MANIFEST_SHA, ROOT, SMOKE, require_ignored, save, sha

SOURCE_COMMIT = "00f7c700da43d38347f30a6ccebd86fcbc798e07"
MODEL_SHA = "f2e804d54d6a88f4f82f44d86c9f1cf646db2509bfca935cfbfc5fcd8cbfac3b"


class HannStream:
    """512-sample analysis buffer + two 512-sample OLA buffers, 16ms hop.

    Initial/final reflection matches the official center=True waveform example.
    Frame 0 is inferred only after enough actual input arrived; no future file
    samples are read by push(). First committed waveform appears at 512 samples.
    """
    def __init__(self, infer, record=False):
        import numpy as np
        self.np = np; self.infer = infer
        self.window = np.hanning(513)[:-1].astype(np.float32)  # periodic Hann
        self.pending = np.empty(0, np.float32)
        self.ola = np.zeros(512, np.float32); self.weights = np.zeros(512, np.float32)
        self.started = False; self.total = 0; self.emitted = 0
        self.previous = 0.0; self.record = record
        self.input_specs = []; self.output_specs = []

    def frame(self, samples, first=False):
        np = self.np
        spectrum = np.fft.rfft(samples*self.window)
        packed = np.stack((spectrum.real, spectrum.imag), axis=-1).astype(np.float32)[None, :, None, :]
        enhanced = self.infer(packed)
        if self.record:
            self.input_specs.append(packed); self.output_specs.append(enhanced)
        waveform = np.fft.irfft(enhanced[0, :, 0, 0]+1j*enhanced[0, :, 0, 1], n=512).astype(np.float32)*self.window
        if first:
            self.ola[:256] = waveform[256:]; self.weights[:256] = self.window[256:]**2
            return np.empty(0, np.float32)
        self.ola += waveform; self.weights += self.window**2
        result = self.ola[:256]/self.weights[:256]
        self.ola[:256] = self.ola[256:]; self.ola[256:] = 0
        self.weights[:256] = self.weights[256:]; self.weights[256:] = 0
        self.emitted += 256
        return result.copy()

    def push(self, samples):
        np = self.np
        self.total += len(samples)
        self.pending = np.concatenate((self.pending, samples))
        values = []
        if not self.started and len(self.pending) >= 512:
            self.frame(np.pad(self.pending[:512], (256, 0), mode="reflect")[:512], first=True)
            self.started = True
        while self.started and len(self.pending) >= 512:
            values.append(self.frame(self.pending[:512]))
            self.previous = self.pending[255]
            self.pending = self.pending[256:]
        return np.concatenate(values) if values else np.empty(0, np.float32)

    def flush(self):
        np = self.np
        if not self.started:
            raise ValueError("Research fixtures must contain at least 512 samples")
        # One preceding sample is needed for exact end reflection when N is an
        # exact hop multiple (right reflection reaches back 257 samples).
        history = np.concatenate((np.array([self.previous], np.float32), self.pending))
        values = [self.frame(np.pad(history, (0, 512-len(self.pending)), mode="reflect")[1:])]
        remainder = self.total-self.emitted
        assert 0 <= remainder < 256
        if remainder:
            assert np.min(self.weights[:remainder]) > 1e-10
            values.append((self.ola[:remainder]/self.weights[:remainder]).copy())
            self.emitted += remainder
        return np.concatenate(values)


def stream(args):
    import numpy as np
    import onnxruntime as ort
    if sha(args.model) != MODEL_SHA or args.model.stat().st_size != 788967:
        raise ValueError("Pinned UL-UNAS model differs")
    if (args.output_dir/"manifest.json").exists():
        raise ValueError("Use a new directory to preserve evidence")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    options=ort.SessionOptions();options.intra_op_num_threads=options.inter_op_num_threads=1
    options.add_session_config_entry("session.intra_op.allow_spinning","0")
    options.add_session_config_entry("session.inter_op.allow_spinning","0")
    session=ort.InferenceSession(str(args.model),options,providers=["CPUExecutionProvider"])
    names=[x.name for x in session.get_inputs()]
    expected=[[1,257,1,2],[1,5358],[1,402],[1,1056]]
    if [x.shape for x in session.get_inputs()] != expected:raise ValueError("Unexpected signature")
    cases=json.loads(args.input_manifest.read_text())["cases"]
    if args.smoke:cases=[c for c in cases if c["name"] in SMOKE]
    reused={}
    if args.reuse_dir:
        prior=json.loads((args.reuse_dir/"manifest.json").read_text())
        if not prior["complete"] or prior["model"]["sha256"]!=MODEL_SHA or prior["inputManifestSha256"]!=INPUT_MANIFEST_SHA:
            raise ValueError("Reuse provenance differs")
        reused={r["name"]:r for r in prior["cases"]}
    rows=[]
    for case in cases:
        input_path=args.input_manifest.parent/(case["name"]+"-input16.f32")
        if sha(input_path)!=case["inputSha256"]:raise ValueError("Saved input hash differs")
        target=args.output_dir/(case["name"]+"-ulunas.f32")
        if case["name"] in reused:
            old=args.reuse_dir/target.name;row=reused[case["name"]]
            if sha(old)!=row["outputSha256"]:raise ValueError("Reused output hash differs")
            shutil.copyfile(old,target);rows.append({**row,"reusedFrom":str(old)})
            if case["name"]=="clean_A":
                shutil.copyfile(args.reuse_dir/"clean_A-spectral-proof.npz",args.output_dir/"clean_A-spectral-proof.npz")
            continue
        samples=np.fromfile(input_path,dtype="<f4")
        caches=[np.zeros(shape,np.float32) for shape in expected[1:]];frame_times=[]
        def infer(frame):
            nonlocal caches
            begin=time.perf_counter()
            result=session.run(None,dict(zip(names,[frame,*caches])))
            frame_times.append((time.perf_counter()-begin)*1000)
            assert all(np.isfinite(x).all() for x in result)
            caches=result[1:]
            return result[0]
        engine=HannStream(infer, record=case["name"]=="clean_A");output=[];counts=[]
        for start in range(0,len(samples),160):
            block=engine.push(samples[start:start+160]);output.append(block);counts.append(len(block))
        output.append(engine.flush());value=np.concatenate(output)
        assert len(value)==len(samples) and np.isfinite(value).all()
        value.astype("<f4").tofile(target)
        if case["name"]=="clean_A":
            np.savez(args.output_dir/"clean_A-spectral-proof.npz",inputSpecs=np.concatenate(engine.input_specs,axis=2),
                     outputSpecs=np.concatenate(engine.output_specs,axis=2),window=engine.window)
        rows.append({"name":case["name"],"input16Sha256":case["inputSha256"],"outputSha256":sha(target),
                     "outputSamples16k":len(value),"firstTenOutputBlockSizes":counts[:10],
                     "neuralFrameMs":{"p50":float(np.percentile(frame_times,50)),"p95":float(np.percentile(frame_times,95)),
                                      "p99":float(np.percentile(frame_times,99)),"max":max(frame_times)}})
        print(json.dumps({"case":case["name"],"samples":len(value),"finite":True}),flush=True)
    save(args.output_dir/"manifest.json",{"complete":True,"inputManifestSha256":INPUT_MANIFEST_SHA,
        "binary":{"onnxruntime":importlib.metadata.version("onnxruntime"),"numpy":importlib.metadata.version("numpy"),
                  "numThreads":1,"allowSpinning":False},
        "model":{"sourceCommit":SOURCE_COMMIT,"sha256":MODEL_SHA,"bytes":788967,"license":"MIT, official repository",
                 "url":f"https://raw.githubusercontent.com/Xiaobin-Rong/ul-unas/{SOURCE_COMMIT}/ulunas_onnx/onnx_models/ulunas_stream_simple.onnx"},
        "fixedDelay48kSamples":0,"nativeSampleRate":16000,"waveformAlignment":"center=True STFT/iSTFT reconstruction; calibration checked separately",
        "availability":"first256 output after512 input; 40ms when feeding160sample/10ms blocks",
        "cliOutputFormat":"float32 direct ORT+NumPy FFT; no WAV writer",
        "outputNormalization":False,"istftNormalization":"required samplewise sum-of-Hann-squared overlap weights",
        "scope":"host functional, no Android/UI/APM; NN timing excludes FFT/copy and is not phone performance", "cases":rows})


def verify(args):
    import numpy as np
    import torch
    torch.set_num_threads(1)
    proof=np.load(args.output_dir/"clean_A-spectral-proof.npz")
    samples=np.fromfile(args.input_manifest.parent/"clean_A-input16.f32",dtype="<f4")
    window=torch.hann_window(512)
    window_error=float(np.max(np.abs(window.numpy()-proof["window"])))
    assert window_error<2e-7,window_error
    reference=torch.view_as_real(torch.stft(torch.from_numpy(samples)[None],512,256,512,window,
                                           return_complex=True)).numpy()
    stft_error=float(np.max(np.abs(reference-proof["inputSpecs"])))
    spectra=proof["outputSpecs"][0]
    reconstructed=torch.istft(torch.complex(torch.from_numpy(spectra[...,0]),torch.from_numpy(spectra[...,1])),
                              512,256,512,window,onesided=True,length=len(samples)).numpy()
    actual=np.fromfile(args.output_dir/"clean_A-ulunas.f32",dtype="<f4")
    ola_error=float(np.max(np.abs(reconstructed-actual)))
    assert stft_error<3e-5 and ola_error<2e-6,(stft_error,ola_error)
    # Independent identity-only transform check. This is not a neural quality result.
    identity=HannStream(lambda frame:frame);blocks=[]
    for start in range(0,len(samples),160):blocks.append(identity.push(samples[start:start+160]))
    blocks.append(identity.flush());identity_error=float(np.max(np.abs(np.concatenate(blocks)-samples)))
    assert identity_error<2e-6,identity_error
    nfft=1<<(len(samples)*2-1).bit_length()
    correlation=np.fft.irfft(np.fft.rfft(actual,nfft)*np.conj(np.fft.rfft(samples,nfft)),nfft)
    shifts=np.arange(-1600,1601);lag=int(shifts[np.argmax(correlation[shifts%nfft])])
    assert lag==0,lag
    result={"officialHannWindowMaxAbs":window_error,"officialTorchStftMaxAbs":stft_error,"officialTorchIstftMaxAbs":ola_error,
            "identityTransformMaxAbs":identity_error,"cleanAFixedLagSamples16k":lag,"window":"periodic Hann512, hop256",
            "torchVersion":importlib.metadata.version("torch"),"noNewNeuralInference":True}
    save(args.output_dir/"waveform-proof.json",result);print(json.dumps(result),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--model",type=Path,default=ROOT/".tmp/current/denoisers-market/ul-unas/ulunas_onnx/onnx_models/ulunas_stream_simple.onnx")
    p.add_argument("--input-manifest",type=Path,default=ROOT/"artifacts/qa/gtcrn/matrix-43/inputs.json")
    p.add_argument("--stream-python",type=Path,default=ROOT/".local/tse-venv/bin/python")
    p.add_argument("--phase",choices=("all","stream","verify"),default="all")
    p.add_argument("--smoke",action="store_true");p.add_argument("--reuse-dir",type=Path)
    args=p.parse_args()
    args.output_dir=args.output_dir.resolve();args.model=args.model.resolve();args.input_manifest=args.input_manifest.resolve()
    if args.reuse_dir:args.reuse_dir=args.reuse_dir.resolve()
    require_ignored(args.output_dir);require_ignored(args.model)
    if sha(args.input_manifest)!=INPUT_MANIFEST_SHA:raise ValueError("Input manifest changed")
    if not __debug__ or sys.byteorder!='little':p.error("Use little-endian Python without -O")
    if args.phase=="stream":stream(args)
    elif args.phase=="verify":verify(args)
    else:
        command=[str(args.stream_python.absolute()),str(Path(__file__).resolve()),"--phase","stream",
                 "--output-dir",str(args.output_dir),"--model",str(args.model),"--input-manifest",str(args.input_manifest)]
        if args.smoke:command.append("--smoke")
        if args.reuse_dir:command += ["--reuse-dir",str(args.reuse_dir)]
        subprocess.run(command,check=True,cwd=ROOT);verify(args)


if __name__=="__main__":main()
