"""Real inference -> tracker -> JSONL, preview, resource/performance report."""
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import cv2
import numpy as np
import psutil
from .schema import observation, validate_pose
from .tracking import Tracker
from .video import frames, inspect_video


def utc_now(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")


def run(video,output,detector,*,view="full",crop=None,stride=1,max_frames=None,
        rover_id="rover-1",calibration=None,preview=True,tracker=None,on_observation=None):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    # Do not truncate a prior run silently.
    if (output/"observations.jsonl").exists(): raise ValueError("output already contains a run; choose a new directory")
    info=inspect_video(video); tracker=tracker or Tracker()
    poses=None
    if calibration is not None:
        poses=json.loads(Path(calibration).read_text(encoding="utf-8"))
    process=psutil.Process(); before=process.cpu_times(); start=time.perf_counter()
    latencies=[]; inference=[]; memory=[]; counts=[]; writer=None; cpu=[]
    process.cpu_percent(None)
    try:
        with (output/"observations.jsonl").open("w",encoding="utf-8") as stream:
            for sequence,(frame_index,video_time,image,rect) in enumerate(frames(video,view=view,crop=crop,stride=stride,max_frames=max_frames)):
                captured=utc_now(); tick=time.perf_counter(); detector.synchronize()
                t=time.perf_counter(); detections=detector.detect(image); detector.synchronize()
                inference.append((time.perf_counter()-t)*1000)
                observed=tracker.update(detections,image)
                h,w=image.shape[:2]
                camera=None; rover_position=None; pose_uncertainty=None
                if poses is not None:
                    pose=poses["frames"].get(str(frame_index))
                    if pose is None: raise ValueError(f"no calibrated pose for frame {frame_index}")
                    camera=pose["camera"]; rover_position=pose["roverPositionEnuM"]; pose_uncertainty=pose["positionUncertaintyRadiusM"]
                    validate_pose(camera,rover_position,pose_uncertainty,w,h)
                    if camera["width"]!=w or camera["height"]!=h or rect != (0,0,info["width"],info["height"]):
                        raise ValueError("calibration must match uncropped video resolution")
                payload={"schemaVersion":1,"roverId":rover_id,"sequence":sequence,"capturedAt":captured,
                    "source":{"file":Path(video).name,"file_sha256":info["sha256"],"frame_index":frame_index,"video_time_s":video_time,
                        "capture_timing":"simulated_known_pose" if poses is not None else "video_playback_unknown_original_cadence"},
                    "image":{"width":w,"height":h,"crop_xywh":list(rect)},"camera":camera,
                    "roverPosition":None if rover_position is None else {"frameId":"LOCAL_ENU_V1","xM":rover_position[0],"yM":rover_position[1],"zM":rover_position[2]},
                    "positionUncertaintyRadiusM":pose_uncertainty,
                    "detections":[observation(track.id,track.detection,captured,w,h) for track in observed]}
                stream.write(json.dumps(payload,allow_nan=False)+"\n"); stream.flush()
                if on_observation is not None: on_observation(payload)
                elapsed=(time.perf_counter()-tick)*1000; latencies.append(elapsed)
                memory.append(process.memory_info().rss/1048576); counts.append(len(observed)); cpu.append(process.cpu_percent(None))
                if preview:
                    display=image.copy()
                    for track in observed:
                        x1,y1,x2,y2=map(int,track.detection.bbox)
                        cv2.rectangle(display,(x1,y1),(x2,y2),(60,220,90),2)
                        cv2.putText(display,f"{track.id} {track.detection.type} {track.detection.confidence:.2f}",
                            (x1,max(15,y1-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,(30,180,40),1)
                        cv2.circle(display,tuple(map(int,track.detection.contact_pixel)),3,(0,100,255),-1)
                    text=f"M1 | frame {frame_index} | {1000/elapsed:.1f} processing FPS | {len(observed)} observations"
                    cv2.rectangle(display,(0,0),(w,32),(15,20,30),-1)
                    cv2.putText(display,text,(10,22),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1)
                    if writer is None:
                        writer=cv2.VideoWriter(str(output/"preview.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),info["fps"]/stride,(w,h))
                        if not writer.isOpened(): raise RuntimeError("cannot encode preview MP4")
                    writer.write(display)
                    if sequence==0 or sequence%10==0: cv2.imwrite(str(output/f"frame-{frame_index:05d}.jpg"),display)
    finally:
        if writer is not None: writer.release()
    total=time.perf_counter()-start
    if not latencies: raise ValueError("no frames decoded")
    after=process.cpu_times(); steady=latencies[1:] or latencies
    report={"video":info,"processed_frames":len(latencies),"detections_total":sum(counts),
        "unique_track_ids":tracker.next_id-1,"wall_seconds":total,"end_to_end_fps":len(latencies)/total,
        "processing_fps":1000/float(np.mean(latencies)),"processing_fps_excluding_first":1000/float(np.mean(steady)),
        "latency_ms_mean":float(np.mean(latencies)),"latency_ms_p95":float(np.percentile(latencies,95)),
        "inference_ms_mean":float(np.mean(inference)),"cpu_seconds":after.user+after.system-before.user-before.system,
        "cpu_percent_process_mean":float(np.mean(cpu)),"cpu_percent_note":"process CPU can exceed 100% on multicore",
        "rss_peak_mb":max(memory),"model_resources":detector.resources(),
        "original_capture_fps":None,"notes":["Playback FPS is not original sensor capture cadence.",
            "Processing latency includes inference, association, JSON serialization; excludes preview encoding.",
            "Model loading excluded; first inference included. RSS sampled once per frame.",
            "Uncalibrated observations have null camera and rover position; no metric coordinates inferred."]}
    (output/"metrics.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    return report
