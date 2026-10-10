"""CLI for local perception and explicitly selected hosted experiments."""
import argparse
import json
from pathlib import Path
from .video import inspect_video


def main():
    parser=argparse.ArgumentParser(description="C.R.A.T.E.R. M1 local perception")
    sub=parser.add_subparsers(dest="command",required=True)
    inspect=sub.add_parser("inspect"); inspect.add_argument("video")
    download=sub.add_parser("download-model"); download.add_argument("--cache-dir",default=".cache/huggingface")
    run=sub.add_parser("run"); run.add_argument("video"); run.add_argument("--output",required=True)
    run.add_argument("--backend",choices=["grounding-dino","synthetic-contrast","hf-hosted","hf-space"],default="grounding-dino")
    run.add_argument("--view",choices=["full","left","right"],default="full")
    run.add_argument("--crop",type=int,nargs=4,metavar=("X","Y","W","H"))
    run.add_argument("--stride",type=int,default=1); run.add_argument("--max-frames",type=int)
    run.add_argument("--threshold",type=float,default=.25); run.add_argument("--text-threshold",type=float,default=.2)
    run.add_argument("--prompt"); run.add_argument("--image-size",type=int,default=640)
    run.add_argument("--device",choices=["auto","cpu","cuda"],default="auto")
    run.add_argument("--cache-dir",default=".cache/huggingface"); run.add_argument("--calibration")
    run.add_argument("--no-preview",action="store_true")
    run.add_argument("--env-file",default=".env")
    run.add_argument("--max-rock-area",type=float,default=.5,help="hf-space maximum box fraction of image area (default .5)")
    check=sub.add_parser("hf-check",help="validate .env without an API call"); check.add_argument("--env-file",default=".env")
    simulate=sub.add_parser("simulate"); simulate.add_argument("--output",required=True); simulate.add_argument("--frames",type=int,default=90)
    evaluate=sub.add_parser("evaluate"); evaluate.add_argument("predictions"); evaluate.add_argument("annotations"); evaluate.add_argument("--output"); evaluate.add_argument("--iou",type=float,default=.5)
    args=parser.parse_args()
    try:
        if args.command=="inspect": result=inspect_video(args.video)
        elif args.command=="download-model":
            from huggingface_hub import snapshot_download
            from .detectors import MODEL_ID, MODEL_REVISION
            location=snapshot_download(MODEL_ID,revision=MODEL_REVISION,cache_dir=args.cache_dir,
                allow_patterns=["*.json","*.txt","*.safetensors"])
            result={"model":MODEL_ID,"snapshot":location}
        elif args.command=="hf-check":
            from .hf_config import HFConfig
            config=HFConfig.load(args.env_file)
            result={"model":config.model,"provider":config.provider,"token_configured":True,
                "api_call_made":False,"max_side":config.max_side,"max_requests":config.max_requests,
                "challenge_local_perception_compliant":False}
        elif args.command=="simulate":
            from .simulation import generate
            result=generate(args.output,args.frames)
        elif args.command=="evaluate":
            from .evaluation import evaluate
            result=evaluate(args.predictions,args.annotations,args.iou)
            if args.output: Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
        else:
            if not 0<args.threshold<1 or not 0<args.text_threshold<1 or args.image_size<128: raise ValueError("invalid model settings")
            from .detectors import GroundingDino,SyntheticContrastDetector
            from .pipeline import run as run_pipeline
            if args.backend in {"hf-hosted","hf-space"}:
                from .hf_config import HFConfig
                from .hf_detector import HostedGrounding
                config=HFConfig.load(args.env_file)
                limit=args.max_frames if args.max_frames is not None else 3
                if limit<1: raise ValueError("max-frames must be positive")
                if limit>config.max_requests: raise ValueError("max-frames exceeds HF_MAX_REQUESTS")
                args.max_frames=limit
                if args.backend=="hf-space":
                    from .hf_space import SpaceGrounding,SPACE_ID
                    if args.prompt is not None: raise ValueError("hf-space uses the tested rock. stone. boulder. prompt; --prompt is for local Grounding DINO")
                    detector=SpaceGrounding(config,threshold=args.threshold,text_threshold=args.text_threshold,max_area=args.max_rock_area)
                    print(f"Free Space experimental perception: {SPACE_ID}; at most {limit} requests; daily quota and queues apply. Not local edge inference.",flush=True)
                else:
                    detector=HostedGrounding(config,threshold=args.threshold)
                    print(f"Hosted experimental perception: {config.model} via {config.provider}; at most {limit} requests. Not local edge inference.",flush=True)
            else:
                detector=SyntheticContrastDetector() if args.backend=="synthetic-contrast" else GroundingDino(
                    device=args.device,threshold=args.threshold,text_threshold=args.text_threshold,prompt=args.prompt or "a rock.",
                    cache_dir=args.cache_dir,image_size=args.image_size)
            result=run_pipeline(args.video,args.output,detector,view=args.view,crop=args.crop,stride=args.stride,
                max_frames=args.max_frames,calibration=args.calibration,preview=not args.no_preview)
            result["backend"]=args.backend
            (Path(args.output)/"metrics.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result,indent=2))
    except (ValueError,RuntimeError,OSError) as exc:
        parser.exit(1,f"M1 error: {exc}\n")

if __name__=="__main__": main()
