"""Opt-in Windows DirectML/Ollama coexistence measurement; no installs or downloads.

Run only after other GPU experiments finish. All outputs must be new and inside
this checkout. Uses the existing M1 interpreter/cache read-only and the actual
M2 WebSocket + M3 parser. This bypasses the normal UI capture guard explicitly
for measurement; it is not a recommended demonstration mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
MODELS = ('qwen3:4b-instruct-2507-q4_K_M', 'embeddinggemma:300m')
REVISION = 'ff690b0a8050566c290287545bd059350f3e9096'
SOURCE_SHA = '04c18d2db35569f11c47732f2e05ed3a71559a8903823fc581e90b0e3168c9ff'
VIDEO_SHA = '74c1764bb1b151486a45372ead706e06cd709700ef6df1791c7822e630c37ad9'
QUESTION = 'How does NASA Perseverance use cameras during autonomous driving?'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Ollama redirects are not permitted')


def api(base, path, payload=None, *, timeout=95):
    if base != 'http://127.0.0.1:11435':
        raise ValueError('Use the dedicated benchmark Ollama instance at 127.0.0.1:11435')
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Ollama response exceeded its bound')
        return json.loads(raw)


def wait_unloaded(base, *, timeout=10, interval=.2):
    """Ollama unload acknowledgement precedes runner removal; prove removal."""
    started = time.monotonic()
    deadline = started + timeout
    polls = 0
    last = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            names = [m.get('name') for m in last.get('models', [])] if last else []
            raise RuntimeError(f'Ollama runners still loaded after {timeout}s: {names}; refusing contaminated baseline')
        # Each poll is bounded by the overall runner-removal deadline.
        last = api(base, '/api/ps', timeout=min(2, remaining))
        polls += 1
        if not isinstance(last, dict) or not isinstance(last.get('models'), list):
            raise RuntimeError('Invalid Ollama process response; unloaded state cannot be established')
        models = last['models']
        if any(not isinstance(m, dict) or m.get('name') not in MODELS for m in models):
            raise RuntimeError('Unexpected model appeared on the dedicated runtime; refusing to interfere')
        if not models:
            return {'elapsedS': time.monotonic() - started, 'polls': polls, 'loadedAfter': last}
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def fingerprint(path):
    value = Path(path).stat()
    return {'size': value.st_size, 'mtimeNs': value.st_mtime_ns}


def validation_command(args, destination):
    bundle = ROOT / 'examples/m1-onnx-calibrated'
    return [str(args.m1_python), '-B', '-m', 'crater_m2.validation', '--output', str(destination),
            '--m3-contract', str(ROOT / 'src/telemetry/contract.ts'), '--node', args.node,
            '--shutdown-timeout', '180', '--', '--perception-video', str(bundle / 'scene.mp4'),
            '--calibration', str(bundle / 'calibration.json'), '--perception-backend', 'onnx-grounding-dino',
            '--device', 'directml', '--cache-dir', str(args.cache), '--stride', '1', '--max-frames', '30',
            '--perception-buffer', '4', '--no-preview', '--duration', '120', '--drain', '30',
            '--fps', '50', '--bandwidth', '4096', '--latency', '.005', '--jitter', '0', '--loss', '0',
            '--no-blackout', '--queue', '128', '--attempts', '20', '--seed', '7']


def gpu_sample():
    try:
        output = subprocess.check_output(['nvidia-smi', '--id=0',
            '--query-gpu=memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'],
            text=True, timeout=3, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        used, free, util = [int(v.strip()) for v in output.splitlines()[0].split(',')]
        return {'usedMiB': used, 'freeMiB': free, 'utilizationPercent': util}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def sample_resources(stop, samples, started, pid, ollama_pid):
    import psutil
    known = {}
    psutil.cpu_percent(None)
    while not stop.is_set():
        memory = psutil.virtual_memory()
        process_rss = process_cpu = 0
        try:
            tree = [psutil.Process(pid), *psutil.Process(pid).children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            tree = []
        for process in tree:
            try:
                tracker = known.setdefault(process.pid, process)
                process_rss += tracker.memory_info().rss
                process_cpu += tracker.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        ollama_rss = 0
        try:
            if ollama_pid:
                parent = psutil.Process(ollama_pid)
                ollama_tree = [parent, *parent.children(recursive=True)]
            else:
                ollama_tree = [p for p in psutil.process_iter(['name']) if 'ollama' in (p.info['name'] or '').lower()]
            for process in ollama_tree:
                try:
                    ollama_rss += process.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        samples.append({'elapsedS': time.perf_counter() - started, 'gpu': gpu_sample(),
            'systemCpuPercent': psutil.cpu_percent(None), 'systemRamUsedMiB': memory.used / 2**20,
            'validationTreeRssMiB': process_rss / 2**20, 'validationTreeCpuPercent': process_cpu,
            'ollamaRssMiB': ollama_rss / 2**20})
        stop.wait(.25)


def resource_summary(samples):
    gpu = [s['gpu']['usedMiB'] for s in samples if s['gpu']]
    return {'sampleCount': len(samples), 'peakGlobalGpuUsedMiB': max(gpu, default=None),
        'meanSystemCpuPercent': statistics.mean(s['systemCpuPercent'] for s in samples) if samples else None,
        'peakSystemRamUsedMiB': max((s['systemRamUsedMiB'] for s in samples), default=None),
        'peakValidationTreeRssMiB': max((s['validationTreeRssMiB'] for s in samples), default=None),
        'peakOllamaRssMiB': max((s['ollamaRssMiB'] for s in samples), default=None)}


def model_work(stop, observation_path, backend, evidence, records, failures, started):
    # Start actual operator-style inference after M1 produces its first frame,
    # ensuring the measured work overlaps capture rather than only model startup.
    while not stop.wait(.025):
        if observation_path.exists() and observation_path.stat().st_size:
            break
    else:
        return
    while not stop.is_set():
        tick = time.perf_counter()
        try:
            with backend.request_budget(90):
                backend.embed([QUESTION], query=True)
                embedding = dict(backend.last_metrics)
                result = backend.chat(QUESTION, evidence)
                completion = dict(backend.last_metrics)
            records.append({'startedS': tick - started, 'finishedS': time.perf_counter() - started,
                'latencyS': time.perf_counter() - tick, 'embedding': embedding, 'completion': completion,
                'result': result, 'verification': 'unverified_generated'})
        except Exception as exc:
            failures.append({'startedS': tick - started, 'errorType': type(exc).__name__, 'error': str(exc)[:2000]})
            return


def run_phase(args, output, phase, backend, evidence):
    destination = output / 'pipeline'
    command = validation_command(args, destination)
    write_json(output / 'command.json', command)
    environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
        PYTHONUNBUFFERED='1', CRATER_M2_SOURCE=str(ROOT))
    stop = threading.Event()
    samples, answers, failures = [], [], []
    started = time.perf_counter()
    with (output / 'validation-stdout.log').open('xb') as stdout, (output / 'validation-stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        sampler = threading.Thread(target=sample_resources, args=(stop,samples,started,process.pid,args.ollama_pid), daemon=True)
        worker = threading.Thread(target=model_work, args=(stop,destination/'perception/observations.jsonl',backend,evidence,answers,failures,started), daemon=True) if phase == 'active_generation' else None
        sampler.start()
        if worker:
            worker.start()
        try:
            exit_code = process.wait(timeout=360)
        except subprocess.TimeoutExpired:
            exit_code = 124
            failures.append({'errorType':'CaptureTimeout','error':'M1/M2 validation exceeded360seconds'})
        finally:
            if process.poll() is None:
                # Terminate only the process tree this script created; never an existing M1 or Ollama instance.
                import psutil
                try:
                    children = psutil.Process(process.pid).children(recursive=True)
                except psutil.NoSuchProcess:
                    children = []
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                process.kill()
                process.wait(timeout=15)
            capture_finished = time.perf_counter() - started
            stop.set()
            sampler.join(timeout=5)
            if worker:
                worker.join(timeout=100)
    write_json(output/'resources.json', samples)
    write_json(output/'inferences.json', {'answers':answers,'failures':failures,'captureFinishedS':capture_finished,
        'note':'An in-flight answer can finish after capture. startedS/finishedS show actual overlap.'})
    if worker and worker.is_alive():
        raise RuntimeError('Ollama request exceeded its aggregate deadline; verify/unload the runtime before continuing')
    validation_path = destination/'validation.json'
    validation = json.loads(validation_path.read_text(encoding='utf-8')) if validation_path.exists() else {}
    m2 = validation.get('m2Report', {})
    m1 = m2.get('source', {}).get('perceptionMetrics', {})
    transport = m2.get('transport', {})
    passed = (exit_code == 0 and validation.get('canonicalM3Validated') is True
        and validation.get('socketMatchesDecodedFrames') is True and validation.get('webSocketFrames') == 30
        and m2.get('completed') is True and m2.get('source',{}).get('producerCompleted') is True
        and m1.get('processed_frames') == 30 and m1.get('model_resources',{}).get('device') == 'directml'
        and 'DmlExecutionProvider' in m1.get('model_resources',{}).get('providers',[])
        and transport.get('generated') == transport.get('delivered') == transport.get('acknowledged') == 30
        and transport.get('pending') == transport.get('queueDropped') == transport.get('abandoned') == 0
        and len(samples) > 0 and any(sample['gpu'] is not None for sample in samples)
        and not failures and (phase != 'active_generation' or len(answers) > 0))
    result = {'phase':phase,'passed':passed,'exitCode':exit_code,'captureWallS':capture_finished,
        'm1':{key:m1.get(key) for key in ('processed_frames','processing_fps','processing_fps_excluding_first',
             'end_to_end_fps','latency_ms_mean','latency_ms_p95','inference_ms_mean','cpu_percent_process_mean','rss_peak_mb','model_resources')},
        'm2':{'completed':m2.get('completed'),'transport':transport,'source':{key:m2.get('source',{}).get(key) for key in
             ('producerCompleted','interrupted','offeredObservations','consumedObservations','maxSampledBufferedObservations','callbackHandoffWaitS','discardedAtStop')}},
        'canonicalM3Validated':validation.get('canonicalM3Validated'), 'resources':resource_summary(samples),
        'inferenceCount':len(answers), 'ollamaLoadedAfter':api(args.ollama_url,'/api/ps')}
    write_json(output/'summary.json',result)
    if not passed:
        raise RuntimeError(f'{phase} did not pass all completion/coexistence gates; inspect {output}')
    return result


def compare(results):
    baseline = [r for r in results if r['phase'] == 'baseline_unloaded']
    fps = statistics.median(r['m1']['processing_fps_excluding_first'] for r in baseline)
    latency = statistics.median(r['m1']['latency_ms_mean'] for r in baseline)
    p95 = statistics.median(r['m1']['latency_ms_p95'] for r in baseline)
    rows=[]
    for phase in ('loaded_idle','active_generation'):
        selected=[r for r in results if r['phase'] == phase]
        current_fps=statistics.median(r['m1']['processing_fps_excluding_first'] for r in selected)
        current_latency=statistics.median(r['m1']['latency_ms_mean'] for r in selected)
        current_p95=statistics.median(r['m1']['latency_ms_p95'] for r in selected)
        rows.append({'phase':phase,'fpsChangePercent':100*(current_fps/fps-1),
            'meanLatencyChangePercent':100*(current_latency/latency-1), 'p95LatencyChangePercent':100*(current_p95/p95-1)})
    degraded=any(r['fpsChangePercent'] < -20 or r['meanLatencyChangePercent'] > 20 or r['p95LatencyChangePercent'] > 30 for r in rows)
    return {'comparisons':rows,'materialDegradation':degraded,
        'policy':'Block science inference during capture and unload before capture.' if degraded else
                 'No material degradation at these settings in this sample. Keep generation operator-triggered; this is not a general coexistence guarantee.',
        'thresholds':'FPS decline >20%, mean latency growth >20%, or p95 growth >30% against median unloaded baseline.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path,help='new output directory inside this checkout')
    parser.add_argument('--m1-python',type=Path,default=Path(r'D:\space_esb_m1\.venv\Scripts\python.exe'))
    parser.add_argument('--cache',type=Path,default=Path(r'D:\space_esb_m1\.cache\huggingface'))
    parser.add_argument('--ollama-url',default='http://127.0.0.1:11435',choices=['http://127.0.0.1:11435'])
    parser.add_argument('--ollama-pid',type=int,help='dedicated Ollama server PID, for isolated RSS sampling')
    parser.add_argument('--node',default='node')
    parser.add_argument('--num-ctx',type=int,default=4096,choices=[2048,4096,8192])
    parser.add_argument('--num-predict',type=int,default=384,choices=[256,384,600])
    parser.add_argument('--repetitions',type=int,default=2,choices=[1,2,3])
    parser.add_argument('--dry-run',action='store_true',help='validate local files and print commands; do not contact Ollama or launch M1')
    args=parser.parse_args(argv)
    args.output=args.output.resolve();args.cache=args.cache.resolve();args.m1_python=args.m1_python.resolve()
    if args.output == ROOT or not args.output.is_relative_to(ROOT) or args.output.exists():
        parser.error('output must be a new child directory of this checkout')
    prepared=args.cache/'prepared-onnx'/REVISION/'model_fp32.onnx'
    metadata=prepared.with_suffix('.json')
    for source in (args.m1_python,prepared,metadata,ROOT/'examples/m1-onnx-calibrated/scene.mp4',ROOT/'examples/m1-onnx-calibrated/calibration.json'):
        if not source.is_file():
            parser.error(f'required existing file missing: {source}')
    if json.loads(metadata.read_text())['source_sha256'] != SOURCE_SHA:
        parser.error('prepared cache metadata does not match the pinned ONNX source; refusing cache preparation')
    if hashlib.sha256((ROOT/'examples/m1-onnx-calibrated/scene.mp4').read_bytes()).hexdigest() != VIDEO_SHA:
        parser.error('calibrated source video checksum mismatch')
    if args.dry_run:
        print(json.dumps({'commands':[validation_command(args,args.output/f'{phase}-1/pipeline') for phase in
            ('baseline_unloaded','loaded_idle','active_generation')], 'offline':True,'existingCacheReadOnly':str(args.cache)},indent=2))
        return 0
    if os.name != 'nt':
        parser.error('Windows DirectML is required')
    import psutil  # Existing resource-sampling prerequisite; fail before any GPU work if absent.
    sys.path.insert(0,str(ROOT))
    from crater_assistant.core import chunks_from_files
    from crater_assistant.ollama import Ollama
    # Fixed evidence across every chat. Retrieval quality/performance is measured separately.
    evidence=[dict(chunk,sourceId=f'S{i+1}') for i,chunk in enumerate(chunks_from_files([
        ROOT/'docs/knowledge/nasa-autonav.md',ROOT/'docs/knowledge/nasa-stereo-cameras.md'])[:3])]
    backend=Ollama(url=args.ollama_url,gpu=True,keep_alive=600,num_ctx=args.num_ctx,num_predict=args.num_predict,timeout=90)
    prerequisites=backend.preflight()
    installed=api(args.ollama_url,'/api/tags')
    loaded=api(args.ollama_url,'/api/ps').get('models',[])
    if any(m.get('name') not in MODELS for m in loaded):
        parser.error('dedicated runtime has unrelated models loaded; refusing to unload them')
    args.output.mkdir(parents=True)
    tracked_before={str(p):fingerprint(p) for p in (prepared,metadata)}
    write_json(args.output/'conditions.json',{'recordedAtUtc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'gitHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'interpreter':str(args.m1_python),'interpreterVersion':subprocess.check_output([str(args.m1_python),'-B','--version'],text=True).strip(),'cache':str(args.cache),'installed':installed,'prerequisites':prerequisites,
        'numCtx':args.num_ctx,'numPredict':args.num_predict,'repetitions':args.repetitions,'fixedEvidence':evidence,
        'resourceScope':'Global NVIDIA device0 memory/system RAM. Validation process tree includes M1/M2/WebSocket validator; per-frame M1 CPU/RSS also in metrics. Ollama RSS covers supplied PID tree or all named Ollama processes.',
        'limitations':'Synthetic calibrated scene, real pixel inference; simulated no-loss radio isolates contention. Not original sensor FPS. Benchmark deliberately bypasses UI capture protection.'})
    results=[]
    for repetition in range(1,args.repetitions+1):
        for phase in ('baseline_unloaded','loaded_idle','active_generation'):
            print(f'{phase} repetition {repetition}',flush=True)
            phase_output=args.output/f'{phase}-{repetition}';phase_output.mkdir()
            backend.unload()
            write_json(phase_output/'unload.json',wait_unloaded(args.ollama_url))
            if phase != 'baseline_unloaded':
                with backend.request_budget(90):
                    backend.embed([QUESTION],query=True)
                    backend.chat(QUESTION,evidence)
                loaded=api(args.ollama_url,'/api/ps')
                if not any(m.get('name') == MODELS[0] and m.get('size_vram',0)>0 for m in loaded.get('models',[])):
                    raise RuntimeError('Qwen GPU offload not demonstrated by Ollama /api/ps')
                write_json(phase_output/'preloaded-models.json',loaded)
            results.append(run_phase(args,phase_output,phase,backend,evidence))
    backend.unload()
    unloaded_after=wait_unloaded(args.ollama_url)
    write_json(args.output/'final-unload.json',unloaded_after)
    tracked_after={str(p):fingerprint(p) for p in (prepared,metadata)}
    if tracked_before != tracked_after:
        raise RuntimeError('existing prepared ONNX cache changed unexpectedly')
    final={'runs':results,'comparison':compare(results),'preparedCacheUnchanged':True,'ollamaUnloadedAfter':unloaded_after['loadedAfter']}
    write_json(args.output/'coexistence.json',final)
    print(json.dumps(final['comparison'],indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
