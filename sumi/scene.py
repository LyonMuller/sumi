from __future__ import annotations
import numpy as np
from numpy.typing import NDArray
Frame = NDArray[np.uint8]

class Scene:
    def __init__(self) -> None:
        self.background: Frame | None = None
        self.pending: Frame | None = None
        self.hidden = False

    def propose(self, samples: list[Frame]) -> None:
        if len(samples) < 6:
            raise ValueError('Poucas amostras. Tente calibrar novamente.')
        if any(s.shape != samples[0].shape for s in samples):
            raise ValueError('A webcam mudou de resolução. Reinicie a captura.')
        stack = np.stack(samples)
        if float(np.abs(stack[-1].astype(float) - stack[0]).mean()) > 10:
            raise ValueError('Movimento ou mudança de luz. Repita com o cenário vazio.')
        self.pending = np.median(stack, axis=0).astype(np.uint8)

    def confirm(self) -> None:
        if self.pending is None:
            raise ValueError('Capture o fundo primeiro.')
        self.background = self.pending.copy()
        self.pending = None

    def toggle(self) -> None:
        if self.background is None:
            raise ValueError('Calibre e confirme o fundo antes de desaparecer.')
        self.hidden = not self.hidden

    def restore(self) -> None:
        self.hidden = False

    def render(self, live: Frame) -> Frame:
        if self.background is not None and self.background.shape != live.shape:
            self.background = None
            self.pending = None
            self.hidden = False
            raise ValueError('Resolução mudou. Calibre o fundo novamente.')
        return self.background.copy() if self.hidden and self.background is not None else live.copy()
