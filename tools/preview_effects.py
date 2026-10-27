"""Render every effect over a real photo, to judge motion and quality by eye.

    python -m tools.preview_effects PERSON.jpg BACKGROUND.jpg OUT_DIR [--effect portal]
    python -m tools.preview_effects ... --load clones=sumi.effects_ninja:ShadowCloneEffect

PERSON is a webcam-like photo with someone in it; BACKGROUND is an empty scene. The
person is cut out with the app's own segmenter and placed on the background, so the
effect sees the same kind of silhouette it gets from the camera. For each effect the
tool writes a contact sheet (disappear and return), an MP4 at 30 FPS and the render
time per frame, which must stay well under 33 ms to keep the camera at 30 FPS.
"""
from __future__ import annotations
import argparse
import importlib
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sumi.effect_catalog import EFFECTS  # noqa: E402
from sumi.effects import Silhouette  # noqa: E402

FPS = 30
SIZE = (1280, 720)


def load(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise SystemExit(f'Não consegui abrir {path}')
    # Fill 16:9 exactly, cropping the excess like a webcam would.
    height, width = image.shape[:2]
    scale = max(SIZE[0] / width, SIZE[1] / height)
    image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    top = (image.shape[0] - SIZE[1]) // 2
    left = (image.shape[1] - SIZE[0]) // 2
    return image[top:top + SIZE[1], left:left + SIZE[0]].copy()


def scene(person_path: Path, background_path: Path) -> tuple[np.ndarray, np.ndarray, Silhouette]:
    from sumi.paths import resource_root
    from sumi.vision import Segmenter
    person = load(person_path)
    background = load(background_path)
    segmenter = Segmenter(resource_root() / 'models')
    try:
        cut = segmenter.capture(person, 1.0)
    finally:
        segmenter.close()
    alpha = cut.mask[:, :, None]
    live = np.clip(person * alpha + background * (1 - alpha), 0, 255).astype(np.uint8)
    return live, background, Silhouette(10.0, live, cut.mask)


def timeline(kind, subject: Silhouette, live: np.ndarray, background: np.ndarray,
             hidden_target: bool) -> tuple[list[np.ndarray], list[float]]:
    effect = kind(subject, hidden_target, 10.0)
    frames, costs = [], []
    steps = int(np.ceil(effect.duration * FPS)) + 1
    for index in range(steps + 4):
        now = 10.0 + index / FPS
        start = perf_counter()
        frames.append(effect.render(live, background, now))
        costs.append((perf_counter() - start) * 1000)
    return frames, costs


def sheet(frames: list[np.ndarray], columns: int = 6) -> np.ndarray:
    picks = np.linspace(0, len(frames) - 1, columns * 2).round().astype(int)
    tiles = [cv2.resize(frames[i], (426, 240), interpolation=cv2.INTER_AREA) for i in picks]
    for i, tile in zip(picks, tiles):
        cv2.putText(tile, f'{i / FPS:.2f}s', (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
    rows = [np.hstack(tiles[r * columns:(r + 1) * columns]) for r in range(2)]
    return np.vstack(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('person', type=Path)
    parser.add_argument('background', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--effect', action='append', help='Only these effects (repeatable)')
    parser.add_argument('--load', action='append', default=[], metavar='NAME=module:Class',
                        help='Also render an effect class that is not in the catalog yet')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    live, background, subject = scene(args.person, args.background)
    cv2.imwrite(str(args.out / 'live.png'), live)
    effects = dict(EFFECTS)
    for spec in args.load:
        name, target = spec.split('=', 1)
        module, cls = target.split(':', 1)
        effects[name] = getattr(importlib.import_module(module), cls)
    for name, kind in effects.items():
        if args.effect and name not in args.effect:
            continue
        leave, cost_out = timeline(kind, subject, live, background, True)
        back, cost_in = timeline(kind, subject, live, background, False)
        cv2.imwrite(str(args.out / f'{name}-sair.png'), sheet(leave))
        cv2.imwrite(str(args.out / f'{name}-voltar.png'), sheet(back))
        writer = cv2.VideoWriter(str(args.out / f'{name}.mp4'), cv2.VideoWriter_fourcc(*'avc1'), FPS, SIZE)
        for frame in [live] * 15 + leave + [background] * 15 + back + [live] * 10:
            writer.write(frame)
        writer.release()
        costs = cost_out + cost_in
        print(f'{name:8} {kind.duration:.2f}s  render median {median(costs):5.1f} ms  '
              f'p95 {np.percentile(costs, 95):5.1f} ms')


if __name__ == '__main__':
    main()
