from __future__ import annotations
from collections import deque
import cv2
import numpy as np
from numpy.typing import NDArray
from .scene import Frame

class LiveBackground:
    """Remember only confidently visible background; retain a conservative person guard."""
    def __init__(self) -> None:
        self.plate: Frame | None=None
        self.previous_safe: NDArray[np.bool_] | None=None
        self.history: deque[tuple[float,NDArray[np.uint8]]]=deque(maxlen=4)
        self.sample: Frame | None=None
        self.last_sample=-1.0
        self.status='Capture o fundo vazio.'

    def reset(self,background:Frame) -> None:
        self.plate=background.copy()
        self.previous_safe=None
        self.history.clear()
        self.sample=None
        self.last_sample=-1.0

    def observe(self,frame:Frame,mask:NDArray[np.float32],captured_at:float) -> None:
        if self.plate is None or frame.shape!=self.plate.shape or mask.shape!=frame.shape[:2]:
            return
        if captured_at<=self.last_sample or not np.isfinite(mask).all():
            return
        h,w=mask.shape
        radius=max(3,round(w/64))
        kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1))
        guard=cv2.dilate((mask>0.04).astype(np.uint8),kernel)
        self.history.append((captured_at,guard))
        while self.history and captured_at-self.history[0][0]>0.55:
            self.history.popleft()
        combined=np.maximum.reduce([entry[1] for entry in self.history])
        safe=combined==0
        # Two distinct observations must agree before changing the remembered plate.
        if self.previous_safe is not None:
            learn=safe & self.previous_safe
            np.copyto(self.plate,frame,where=learn[:,:,None])
        self.previous_safe=safe
        self.sample=frame.copy()
        self.last_sample=captured_at

    def render(self,live:Frame,fallback:Frame,now:float) -> Frame:
        if live.shape!=fallback.shape:
            raise ValueError('Câmera mudou de resolução. Refaça a calibração.')
        if self.plate is None or self.plate.shape!=live.shape:
            self.reset(fallback)
        if self.sample is None or not self.history or now-self.last_sample>0.35:
            self.status='Recorte desatualizado: usando o fundo aprendido.'
            return self.plate.copy()
        guard=np.maximum.reduce([entry[1] for entry in self.history])
        # Fast changes since the aligned sample are uncertain until the next segmentation.
        # This deliberately freezes moving pixels briefly rather than copying unknown foreground.
        motion=(cv2.cvtColor(cv2.absdiff(live,self.sample),cv2.COLOR_BGR2GRAY)>18).astype(np.uint8)
        motion=cv2.dilate(motion,np.ones((5,5),np.uint8))
        guard=np.maximum(guard,motion)
        result=live.copy()
        cv2.copyTo(self.plate,guard,result)
        # Blend only a narrow exterior fringe, avoiding full-frame float RGB allocations.
        alpha=np.clip(cv2.GaussianBlur(guard.astype(np.float32),(0,0),1.2),0,1)
        edge=(guard==0)&(alpha>0.01)
        weights=alpha[edge][:,None]
        result[edge]=np.clip(np.rint(live[edge]*(1-weights)+self.plate[edge]*weights),0,255).astype(np.uint8)
        self.status='Fundo ao vivo nas áreas visíveis; região oculta usa o cenário aprendido.'
        return result
