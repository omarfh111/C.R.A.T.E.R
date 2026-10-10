"""CLI with explicit online setup and offline inference by default."""
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
    run.add_argument("--backend",choices=["grounding-dino","synthetic-contrast"],default="grounding-dino")
    run.add_argument("--view",choices=["full","left","right"],default="full")
    run.add_argument("--crop",type=int,nargs=4,metavar=("X","Y","W","H"))
    run.add_argument("--stride",type=int,default=1); run.add_argument("--max-frames",type=int)
    run.add_argument("--threshold",type=float,default=.25); run.add_argument("--text-threshold",type=float,default=.2)
    run.add_argument("--prompt",default="a rock."); run.add_argument("--image-size",type=int,default=640)
    run.add_argument("--device",choices=["auto","cpu","cuda"],default="auto")
    run.add_argument("--cache-dir",default=".cache/huggingface"); run.add_argument("--calibration")
    run.add_argument("--no-preview",action="store_true")
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
            detector=SyntheticContrastDetector() if args.backend=="synthetic-contrast" else GroundingDino(
                device=args.device,threshold=args.threshold,text_threshold=args.text_threshold,prompt=args.prompt,
                cache_dir=args.cache_dir,image_size=args.image_size)
            result=run_pipeline(args.video,args.output,detector,view=args.view,crop=args.crop,stride=args.stride,
                max_frames=args.max_frames,calibration=args.calibration,preview=not args.no_preview)
            result["backend"]=args.backend
            (Path(args.output)/"metrics.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result,indent=2))
    except (ValueError,RuntimeError,OSError) as exc:
        parser.exit(1,f"M1 error: {exc}\n")

if __name__=="__main__": main()
