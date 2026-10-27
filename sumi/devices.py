from __future__ import annotations
from dataclasses import dataclass
from cv2_enumerate_cameras import enumerate_cameras
from .system import enumeration_backend

@dataclass(frozen=True)
class CameraDevice:
    index: int
    name: str
    path: str
    backend: int

    @property
    def label(self) -> str:
        return f'{self.name} · {self.index}'

    @property
    def virtual(self) -> bool:
        return any(word in self.name.lower() for word in ('obs','virtual','unity','quest'))


def list_cameras() -> list[CameraDevice]:
    # Enumerating metadata does not open the webcam or read frames.
    return [CameraDevice(c.index,c.name,c.path or '',c.backend)
            for c in enumerate_cameras(enumeration_backend())]
