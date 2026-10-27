"""Synthetic renderer timings, excluding capture, inference, UI and virtual output."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from statistics import median
from time import perf_counter
import cv2
import numpy as np
from sumi.effects import Silhouette
from sumi.effect_catalog import EFFECTS

def main() -> None:
    background=np.full((720,1280,3),40,np.uint8)
    mask=np.zeros((720,1280),np.float32)
    cv2.circle(mask,(640,180),88,1,-1)
    cv2.ellipse(mask,(640,500),(160,260),0,0,360,1,-1)
    live=background.copy(); live[mask>0]=(80,140,210)
    subject=Silhouette(10,live,mask)
    for name,kind in EFFECTS.items():
        start=perf_counter(); effect=kind(subject,True,10)
        setup=(perf_counter()-start)*1000
        samples=[]
        for p in np.linspace(.05,.95,24):
            start=perf_counter()
            effect.render(live,background,10+float(p)*effect.duration)
            samples.append((perf_counter()-start)*1000)
        print(f'{name}: setup={setup:.1f}ms median={median(samples):.1f}ms p95={np.percentile(samples,95):.1f}ms')

if __name__=='__main__': main()
