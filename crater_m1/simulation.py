"""Small controlled camera/ground scene; truth used ONLY for evaluation."""
from pathlib import Path
import hashlib
import json
import math
import cv2
import numpy as np


def generate(output, count=90):
    if count<2: raise ValueError("simulation needs at least two frames")
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    if (output/"scene.mp4").exists(): raise ValueError("simulation output exists")
    width,height=640,480; fx=fy=450.; cx,cy=320.,220.
    angle=math.radians(20)
    rotation=np.array([[1,0,0],[0,-math.sin(angle),math.cos(angle)],[0,-math.cos(angle),-math.sin(angle)]])
    points=[(-1.,4.,0.),(1.,6.,0.),(.2,8.,0.)]
    writer=cv2.VideoWriter(str(output/"scene.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),10.,(width,height))
    if not writer.isOpened(): raise RuntimeError("cannot create simulation video")
    calibration={"frameId":"LOCAL_ENU_V1","ground_z_m":0.,"frames":{}}
    annotations={"scope":"All three rendered rock silhouettes; controlled synthetic scene, not NASA accuracy.","frames":[]}
    rng=np.random.default_rng(42)
    background=np.full((height,width,3),185,dtype=np.uint8)
    background[:56]=(205,195,175)
    for _ in range(500):
        x,y=rng.integers(0,width),rng.integers(70,height)
        cv2.circle(background,(int(x),int(y)),1,(145,145,145),-1)
    try:
        for index in range(count):
            center=np.array([0,index*.01,1.2]); image=background.copy(); truth=[]
            for number,point in enumerate(points):
                local=rotation.T @ (np.array(point)-center)
                u,v=fx*local[0]/local[2]+cx,fy*local[1]/local[2]+cy
                bw=int(round(fx*.32/local[2])); bh=int(round(fy*.23/local[2]))
                x=int(round(u)); y=int(round(v)); half=bw//2
                polygon=np.array([[x-half,y],[x-half,y-bh//2],[x-half//2,y-bh],
                    [x+half//2,y-bh],[x+half,y-bh//2],[x+half,y]],dtype=np.int32)
                cv2.fillPoly(image,[polygon],(50,50,50))
                cv2.fillPoly(image,[np.array([[x-half//2,y-bh],[x+half//2,y-bh],[x,y-2]])],(75,75,75))
                truth.append({"id":f"rock-{number+1}","type":"rock","bboxPx":[x-half,y-bh,x+half,y],
                    "contactPixel":[x,y],"position_enu_m":list(point)})
            writer.write(image)
            calibration["frames"][str(index)]={"positionUncertaintyRadiusM":.05,"camera":{"width":width,"height":height,
                "fx":fx,"fy":fy,"cx":cx,"cy":cy,"centerEnuM":center.tolist(),
                "rotationCameraToEnu":rotation.tolist()},"roverPositionEnuM":[0,index*.01,0]}
            annotations["frames"].append({"frame_index":index,"detections":truth})
        cv2.imwrite(str(output/"scene-preview.jpg"),image)
    finally: writer.release()
    with (output/"scene.mp4").open("rb") as stream:
        annotations["source_sha256"]=hashlib.file_digest(stream,"sha256").hexdigest()
    (output/"calibration.json").write_text(json.dumps(calibration,indent=2),encoding="utf-8")
    (output/"annotations.json").write_text(json.dumps(annotations,indent=2),encoding="utf-8")
    return {"video":str(output/"scene.mp4"),"frames":count,"calibration":str(output/"calibration.json"),"annotations":str(output/"annotations.json")}
