#!/usr/bin/env python3
"""Freeze ONLY the pinned public A/C fixture profiles in diagnostic ONNX graphs.

Models and generated files must remain ignored by Git. The 5-input compatibility
variant intentionally ignores its enrollment/context inputs and always selects
public A6930: NEVER ship it or use it for another owner. No private recording is
accepted. This script performs real ORT inference, not product integration.
"""
import argparse
import collections
import copy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import types

MODEL_SHA256 = {
    "enroll.onnx": "86645cba23f207def0b31a6e74a615d3b7a813b4fdf957c53b3af2905ba2ffd3",
    "chunk_int8_full.onnx": "7b57c1bfd5acd5b33768a9dff09d9af487d45374b3ba0b991e541ff121eaa337",
}
PUBLIC_REFERENCE_SHA256 = {
    "6930": "b6ed68a64da99051dd8bd2a689890b01247676b916a2ce448317fe48e4721022",
    "5639": "24a219e56b1484af21d05e0ef8aa3b4c2484d827900d92b67afa0440c7c4fdb0",
}
PUBLIC_GOLDEN_SHA256 = {
    "6930": "5fa596f31e63d9a6f59047e0828472740b58dcc256d5d0f1edb7524415956949",
    "5639": "77aee4a01cf2884b104cad374f822db46b02553ffc2385d25cab8b85cef1d3c9",
}
PUBLIC_MIX_SHA256 = "2f1b768ced4f46bfbea3f428cbf1592e3bdc621e08a5857ae041700437663e8c"
PUBLIC_QUERY_SHA256 = {
    "1320-122617-0012.flac": "6b5cd2c31ee61665ea0d81f2c76a1f2c32cb4f46e5ec5861bd9157e262785252",
    "5639-40744-0002.flac": "111c6b8b19d093736570bced344035b48f75c770aacc60103da9d9a20f904fb2",
}
VOXLOCK_COMMIT = "08ed37cbb79f449ca6b499bc23fb14138b207bfd"
CORE_SHA256 = "28049a0904482472a7892e1a357350d31418c3009fd2209f78007f73dc2afaca"


def require_hash(path, expected):
    path = Path(path)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Missing/changed pinned public input: {path}")


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-manifest", type=Path, default=root / "artifacts/qa/target-voice/golden/manifest.json")
    parser.add_argument("--model-dir", type=Path, default=root / ".local/target-voice/voxlock-a50f4e1d/onnx")
    parser.add_argument("--voxlock-source", type=Path, default=root / ".tmp/current/voxlock")
    parser.add_argument("--speech-dir", type=Path, default=root / "artifacts/qa/target-voice/speech")
    parser.add_argument("--output-dir", type=Path, default=root / ".tmp/current/target-voice-frozen-canonical")
    parser.add_argument("--evidence-dir", type=Path, default=root / "artifacts/qa/target-voice/frozen-context-canonical")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without python -O; parity assertions must remain enabled")
    for path in (args.output_dir, args.evidence_dir):
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            parser.error("Generated graphs/evidence must stay in an ignored repository directory")
        if subprocess.run(["git", "check-ignore", "--quiet", str(relative)], cwd=root).returncode != 0:
            parser.error(f"Output is not Git-ignored: {path}")
    revision = subprocess.run(["git", "-C", str(args.voxlock_source), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    if revision != VOXLOCK_COMMIT:
        parser.error(f"Use pinned VoxLock source {VOXLOCK_COMMIT}")
    require_hash(args.voxlock_source / "voxlock/core.py", CORE_SHA256)
    for name, digest in MODEL_SHA256.items():
        require_hash(args.model_dir / name, digest)
    public_manifest = json.loads(args.golden_manifest.read_text())
    if (public_manifest["sampleRate"] != 16000 or public_manifest["chunkSamples"] != 640
            or public_manifest["dtype"] != "little-endian-float32"
            or public_manifest["samples"] != 318720):
        parser.error("Use the exact public 16kHz/640-sample golden fixture")
    require_hash(public_manifest["input"], PUBLIC_MIX_SHA256)
    for identity, digest in PUBLIC_REFERENCE_SHA256.items():
        case = next(row for row in public_manifest["cases"] if row["speaker"] == identity)
        require_hash(case["reference"], digest)
        require_hash(case["expected"], PUBLIC_GOLDEN_SHA256[identity])
    for name, digest in PUBLIC_QUERY_SHA256.items():
        require_hash(args.speech_dir / name, digest)
    print("DIAGNOSTIC ONLY: fixed public A/C acoustic data. NEVER ship the generated graphs; "
          "5-input FROZEN_A ignores supplied profiles and cannot represent another owner.", file=sys.stderr, flush=True)
    sys.dont_write_bytecode = True

    import numpy as np
    import onnx
    from onnx import numpy_helper
    import onnxruntime as ort
    import soundfile as sf

    OUT=args.output_dir.resolve(); OUT.mkdir(parents=True,exist_ok=True)
    EVIDENCE=args.evidence_dir.resolve(); EVIDENCE.mkdir(parents=True,exist_ok=True)
    MODEL_DIR=args.model_dir.resolve()
    ORIGINAL=MODEL_DIR/'chunk_int8_full.onnx'
    ORIGINAL_HASH='7b57c1bfd5acd5b33768a9dff09d9af487d45374b3ba0b991e541ff121eaa337'
    CORE=args.voxlock_source.resolve()/'voxlock/core.py'
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==ORIGINAL_HASH
    assert hashlib.sha256(CORE.read_bytes()).hexdigest()=='28049a0904482472a7892e1a357350d31418c3009fd2209f78007f73dc2afaca'
    spec=importlib.util.spec_from_file_location('pinned_voxlock_core',CORE)
    core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
    if ort.__version__ != '1.31.0':
        parser.error('Use pinned onnxruntime 1.31.0')
    ort.disable_telemetry_events()

    def options(optimized=None):
        o=ort.SessionOptions();o.intra_op_num_threads=4;o.inter_op_num_threads=1
        o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        o.add_session_config_entry('session.intra_op.allow_spinning','0')
        o.add_session_config_entry('session.inter_op.allow_spinning','0')
        if optimized:o.optimized_model_filepath=str(optimized)
        return o

    def session(path,optimized=None):
        return ort.InferenceSession(str(path),options(optimized),providers=['CPUExecutionProvider'])

    def fingerprint(model):
        return {t.name:hashlib.sha256(t.SerializeToString(deterministic=True)).hexdigest() for t in model.graph.initializer}

    def stats(model):
        return {'nodes':len(model.graph.node),'initializers':len(model.graph.initializer),
                'inputs':[x.name for x in model.graph.input],
                'ops':dict(collections.Counter(n.op_type for n in model.graph.node))}

    original_proto=onnx.load(ORIGINAL)
    weight_hashes=fingerprint(original_proto)
    original_optimized_path=OUT/'original.ort-optimized.onnx'
    original=session(ORIGINAL,original_optimized_path)
    enroll=session(MODEL_DIR/'enroll.onnx')
    golden=public_manifest
    mixture=np.fromfile(golden['input'],dtype='<f4')
    assert mixture.shape == (318720,) and np.isfinite(mixture).all()
    report={'diagnosticOnly':True,'publicCorpusOnly':True,'productionWired':False,
            'complete':False,
            'originalModel':str(ORIGINAL),'originalSha256':ORIGINAL_HASH,
            'onnx':onnx.__version__,'ort':ort.__version__,
            'sourceCommit':'08ed37cbb79f449ca6b499bc23fb14138b207bfd',
            'modelBindingWarning':'Outputs embed PUBLIC A/C acoustic profiles. Never ship or use fixed A with any other owner; compat inputs are ignored',
            'modelRevision':'a50f4e1d109301d4b6f61dec57ebb1a61e7d8f03',
            'original':stats(original_proto),'originalOptimized':stats(onnx.load(original_optimized_path)),
            'macsLinear512to128PerBlockEstimate':32*298*512*128,
            'macEstimateScope':'Theoretical arithmetic of 32 context Linear layers only; not runtime dominance or speedup',
            'publicFixtureHashesValidated':True,
            'timingScope':'host functional, not a controlled phone benchmark',
            'profiles':[]}

    def save_report():
        (EVIDENCE/'host-proof.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')

    class FrozenAdapter:
        """Signature adapter only: every call executes the actual ONNX session."""
        def __init__(self,s):self.s=s;self.names={x.name for x in s.get_inputs()}
        def run(self,names,feeds):return self.s.run(names,{k:v for k,v in feeds.items() if k in self.names})

    def full_stream(chunk,reference,x):
        stream=core.Stream(types.SimpleNamespace(enroll=enroll,chunk=FrozenAdapter(chunk)),reference)
        begin=time.perf_counter();parts=[];times=[]
        for offset in range(0,len(x),640):
            start=time.perf_counter();parts.append(stream.push(x[offset:offset+640]));times.append((time.perf_counter()-start)*1000)
        parts.append(stream.flush());y=np.concatenate(parts)[:len(x)]
        assert len(y)==len(x) and np.isfinite(y).all()
        return y,{'wallSeconds':time.perf_counter()-begin,'pushMeanMs':float(np.mean(times)),
                   'pushP50Ms':float(np.percentile(times,50)),'pushP95Ms':float(np.percentile(times,95)),
                   'rtf':(time.perf_counter()-begin)/(len(x)/16000)}

    def diff(a,b):
        assert a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all()
        d=a.astype(np.float64)-b.astype(np.float64)
        return {'shape':list(a.shape),'maxAbs':float(np.max(np.abs(d))),'rmse':float(np.sqrt(np.mean(d*d))),'bitIdentical':bool(np.array_equal(a,b))}

    def compare_outputs(actual, expected):
        assert len(actual) == len(expected) == 3
        differences = [diff(a, b) for a, b in zip(actual, expected)]
        assert max(item['maxAbs'] for item in differences) < 2e-5
        return differences

    def freeze(name,mag,ctx,keep_unused_inputs=False):
        m=copy.deepcopy(original_proto)
        fixed={'enroll_mag':mag,'context':ctx}
        if keep_unused_inputs:
            replacements={n:f'DIAGNOSTIC_ONLY_FROZEN_{name}_{n}' for n in fixed}
            for node in m.graph.node:
                for i,value in enumerate(node.input):
                    if value in replacements:node.input[i]=replacements[value]
            for n,a in fixed.items():m.graph.initializer.append(numpy_helper.from_array(np.ascontiguousarray(a),replacements[n]))
        else:
            for n,a in fixed.items():m.graph.initializer.append(numpy_helper.from_array(np.ascontiguousarray(a),n))
            remaining=[x for x in m.graph.input if x.name not in fixed]
            del m.graph.input[:];m.graph.input.extend(remaining)
        m.graph.name=f'DIAGNOSTIC_ONLY_FROZEN_{name}_PUBLIC_PROFILE_NOT_GENERAL_PURPOSE'
        prop=m.metadata_props.add();prop.key='danygramm.diagnostic_only_frozen_profile';prop.value=name
        prop=m.metadata_props.add();prop.key='danygramm.public_profile_source';prop.value='LibriSpeech test-clean; no private recording'
        prop=m.metadata_props.add();prop.key='danygramm.fixed_profile_sha256';prop.value=PUBLIC_REFERENCE_SHA256['6930' if name=='A' else '5639']
        prop=m.metadata_props.add();prop.key='danygramm.do_not_ship';prop.value='true: fixed public corpus owner, not a general enrollment model'
        prop=m.metadata_props.add();prop.key='danygramm.compat_inputs_ignored';prop.value=str(keep_unused_inputs).lower()
        current=fingerprint(m)
        assert all(current[k]==v for k,v in weight_hashes.items()),'Original initializer mutated'
        assert len(current)==len(weight_hashes)+2
        onnx.checker.check_model(m)
        suffix='5-input-compat' if keep_unused_inputs else '3-input'
        path=OUT/f'DIAGNOSTIC_ONLY_FROZEN_{name}-{suffix}.onnx';onnx.save_model(m,path)
        optimized=path.with_suffix('.ort-optimized.onnx');s=session(path,optimized)
        return s,{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
                   'originalInitializersUnchanged':True,'originalInitializerCount':len(weight_hashes),
                   'graph':stats(m),'optimized':stats(onnx.load(optimized)),
                   'runtimeInputs':[(x.name,x.shape,x.type) for x in s.get_inputs()],
                   'optimizedPath':str(optimized)}

    for identity,label in [('6930','A'),('5639','C')]:
        case=next(x for x in golden['cases'] if x['speaker']==identity)
        reference=np.fromfile(case['reference'],dtype='<f4');assert reference.shape==(48000,)
        mag,ctx=enroll.run(None,{'enroll':reference[None]})
        assert mag.shape == (1,257,376) and ctx.shape == (1,512,298)
        assert np.isfinite(mag).all() and np.isfinite(ctx).all()
        row={'profile':label,'speaker':identity,'reference':case['reference'],
             'referenceSha256':hashlib.sha256(Path(case['reference']).read_bytes()).hexdigest(),
             'magShape':list(mag.shape),'contextShape':list(ctx.shape)}
        frozen,details=freeze(label,mag,ctx);row['threeInput']=details
        states=[np.zeros((6,32,256),np.float32),np.zeros((6,32,256),np.float32)]
        frozen_states=[x.copy() for x in states]
        first=np.concatenate((mixture[1:257][::-1],mixture[:640]))
        waves=[first,np.concatenate((first[512:],mixture[640:1280]))]
        row['directChunkParity']=[]
        for index,wav in enumerate(waves):
            feeds={'wav':wav[None],'enroll_mag':mag,'context':ctx,'h':states[0],'c':states[1]}
            expected=original.run(None,feeds)
            got=frozen.run(None,{'wav':wav[None],'h':frozen_states[0],'c':frozen_states[1]})
            differences=compare_outputs(got,expected)
            row['directChunkParity'].append({'K':4 if index==0 else 5,'outputs':differences})
            states=expected[1:];frozen_states=got[1:]
        got,timings=full_stream(frozen,reference,mixture)
        expected=np.fromfile(case['expected'],dtype='<f4')
        row['fullGoldenParity']=diff(got,expected);row['functionalTiming']=timings
        got.astype('<f4').tofile(EVIDENCE/f'frozen-{label}.f32')
        assert row['fullGoldenParity']['maxAbs']<2e-5
        if label=='A':
            compatible,compat_details=freeze(label,mag,ctx,True)
            row['fiveInputDiagnostic']=compat_details
            assert {x.name for x in compatible.get_inputs()}=={'wav','enroll_mag','context','h','c'}
            got_compat=compatible.run(None,{'wav':first[None],'enroll_mag':mag,'context':ctx,
                                          'h':np.zeros((6,32,256),np.float32),'c':np.zeros((6,32,256),np.float32)})
            expected_first=original.run(None,{'wav':first[None],'enroll_mag':mag,'context':ctx,
                                             'h':np.zeros((6,32,256),np.float32),'c':np.zeros((6,32,256),np.float32)})
            row['fiveInputFirstChunkParity']=compare_outputs(got_compat,expected_first)
            ignored_profile=compatible.run(None,{'wav':first[None],
                'enroll_mag':np.zeros_like(mag),'context':np.zeros_like(ctx),
                'h':np.zeros((6,32,256),np.float32),'c':np.zeros((6,32,256),np.float32)})
            row['fiveInputZeroProfileStillSelectsA']=compare_outputs(ignored_profile,expected_first)
            del compatible
        if label=='C':
            def read_query(filename):
                x,sr=sf.read(args.speech_dir/filename,dtype='float32')
                assert sr==16000 and x.ndim==1 and np.isfinite(x).all()
                x=core.loud_sample(x,3,30);rms=float(np.sqrt(np.mean(x.astype(np.float64)**2)+1e-16))
                return (x*(.06/rms)).astype(np.float32)
            b=read_query('1320-122617-0012.flac');c=read_query('5639-40744-0002.flac');region=slice(4000,-4000)
            row['badCaseControl']=[]
            for query,x in [('B_only',b),('B+C',b+c)]:
                baseline,_=full_stream(original,reference,x);changed,_=full_stream(frozen,reference,x)
                basis=np.column_stack((b[region],c[region] if query=='B+C' else np.zeros_like(b[region]))).astype(np.float64)
                gains0=np.linalg.lstsq(basis,baseline[region].astype(np.float64),rcond=None)[0]
                gains1=np.linalg.lstsq(basis,changed[region].astype(np.float64),rcond=None)[0]
                control={'query':query,'originalGainsBC':gains0.tolist(),'frozenGainsBC':gains1.tolist(),'parity':diff(changed,baseline)}
                assert control['parity']['maxAbs'] < 2e-5
                row['badCaseControl'].append(control)
        original_ops=report['originalOptimized']['ops'];new_ops=details['optimized']['ops']
        row['removedOptimizedOps']={op:original_ops.get(op,0)-new_ops.get(op,0) for op in original_ops if original_ops.get(op,0)>new_ops.get(op,0)}
        report['profiles'].append(row);save_report()
        print(json.dumps({'profile':label,'parity':row['fullGoldenParity'],'functionalTiming':timings,
                          'originalOptimizedNodes':report['originalOptimized']['nodes'],
                          'frozenOptimizedNodes':details['optimized']['nodes']}),flush=True)
        del frozen;gc.collect()
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==ORIGINAL_HASH
    report['originalModelUnchangedAfterExperiment']=True
    report['complete']=True
    save_report();print('Saved',EVIDENCE/'host-proof.json',flush=True)


if __name__ == "__main__":
    main()
