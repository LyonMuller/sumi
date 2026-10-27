"""Gerador antigo de efeitos sonoros por síntese procedural (sem amostras de terceiros).

Atenção: é só o recurso de reserva antigo. Os arquivos distribuídos em assets/sounds/ vêm de
fontes CC0 listadas em assets/sounds/CREDITS.md; nada no empacotamento ou nos testes chama este
script. Rodá-lo sem passar uma pasta de saída sobrescreveria esses arquivos.

Uso: python tools/make_sounds.py [pasta_de_saída]
Saída: WAV 16 bits, mono, 44,1 kHz, em assets/sounds/<nome>.wav. Determinístico (sementes fixas).
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
ROOT = Path(__file__).resolve().parents[1]
PEAK = 10 ** (-3 / 20)  # -3 dBFS


def rng(name: str) -> np.random.Generator:
    return np.random.default_rng(sum(map(ord, name)) * 7919)


def t_axis(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def noise(g, seconds):
    return g.standard_normal(int(seconds * SR))


def env_ar(n, attack, release, curve=2.0):
    """Ataque linear e decaimento exponencial suave."""
    a = max(int(attack * SR), 1)
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a) ** 1.5
    r = n - a
    if r > 0:
        e[a:] = np.exp(-curve * np.linspace(0, 1, r) * (1.0 / max(release, 1e-3)) * (r / SR))
    return e


def lowpass(x, cutoff):
    """Passa-baixa de um polo; cutoff (Hz) pode ser escalar ou vetor por amostra."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s += a[i] * (x[i] - s)
        y[i] = s
    return y


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def bandpass(x, lo, hi):
    return lowpass(highpass(x, lo), hi)


def sweep(f0, f1, seconds, curve='exp'):
    n = int(seconds * SR)
    u = np.linspace(0, 1, n)
    f = f0 * (f1 / f0) ** u if curve == 'exp' else f0 + (f1 - f0) * u
    return np.cumsum(2 * np.pi * f / SR)


def sine_sweep(f0, f1, seconds, curve='exp'):
    return np.sin(sweep(f0, f1, seconds, curve))


def echo(x, taps):
    """taps: [(atraso_s, ganho)]. Eco/reverb leve, estende o sinal."""
    extra = int(max(d for d, _ in taps) * SR)
    y = np.concatenate([x, np.zeros(extra)])
    for d, g in taps:
        k = int(d * SR)
        y[k:k + len(x)] += x * g
    return y


def reverb(x, seed, decay=0.35, length=0.25):
    g = np.random.default_rng(seed)
    n = int(length * SR)
    ir = g.standard_normal(n) * np.exp(-np.linspace(0, 1, n) * 7)
    ir = lowpass(ir, 5000)
    ir /= np.abs(ir).sum() / 3
    wet = np.convolve(x, ir)
    y = np.concatenate([x, np.zeros(n - 1)])
    return y + decay * wet


def mix(*parts):
    n = max(off + len(p) for off, p in parts)
    y = np.zeros(n)
    for off, p in parts:
        y[off:off + len(p)] += p
    return y


def at(seconds):
    return int(seconds * SR)


def finish(x, fade_in=0.004, fade_out=0.03):
    x = x - x.mean()
    x = x / max(np.abs(x).max(), 1e-9) * PEAK
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    x[:fi] *= np.linspace(0, 1, fi)
    x[-fo:] *= np.linspace(1, 0, fo)
    return x


def soft_clip(x, drive=1.0):
    return np.tanh(x * drive)


# ---------------------------------------------------------------- efeitos

def goku():
    """Teletransporte instantâneo: 'shunn' curto com um brilho agudo."""
    g = rng('goku')
    n = 0.55
    t = t_axis(n)
    wind = bandpass(noise(g, n), 300, 4000) * env_ar(len(t), 0.02, 0.18, 4)
    wind = bandpass(noise(g, n), 800, 9000) * np.exp(-((t - 0.08) / 0.07) ** 2)
    zing = sine_sweep(900, 5200, n, 'exp') * np.exp(-t * 9) * np.minimum(t / 0.01, 1)
    zing += 0.4 * sine_sweep(1800, 10400, n, 'exp') * np.exp(-t * 12)
    thump = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 28)
    y = mix((0, wind * 0.9), (0, zing * 0.7), (0, thump * 0.5))
    return reverb(finish(y, 0.002), 11, 0.25, 0.2)


def anime():
    """Corrida/teleporte anime: whoosh rápido com filtro em varredura."""
    g = rng('anime')
    n = 0.5
    t = t_axis(n)
    cut = 400 * (9000 / 400) ** np.clip(t / 0.22, 0, 1)
    w = lowpass(noise(g, n), cut)
    w = highpass(w, 250) * np.sin(np.pi * np.clip(t / n, 0, 1)) ** 0.7
    tail = sine_sweep(2200, 500, n) * np.exp(-t * 10) * 0.25
    hit = noise(g, 0.03)
    hit = bandpass(hit, 2000, 7000) * np.exp(-np.linspace(0, 1, len(hit)) * 6)
    y = mix((0, w), (0, tail), (at(0.2), hit * 0.8))
    return finish(echo(y, [(0.07, 0.25), (0.14, 0.12)]))


def puff():
    """Kawarimi: nuvem de fumaça 'poof' e batida de madeira."""
    g = rng('puff')
    n = 0.8
    t = t_axis(n)
    cut = 3500 * np.exp(-t * 6) + 250
    poof = lowpass(noise(g, n), cut) * env_ar(len(t), 0.008, 0.25, 5)
    boom = np.sin(sweep(160, 45, n)) * np.exp(-t * 14) * 0.6
    knock = np.zeros(at(0.3))
    tk = t_axis(0.3)
    for off, f, a in ((0.0, 420, 1.0), (0.11, 520, 0.7)):
        k = at(off)
        seg = (np.sin(2 * np.pi * f * tk[: len(tk) - k]) + 0.5 * np.sin(2 * np.pi * f * 2.76 * tk[: len(tk) - k])) \
            * np.exp(-tk[: len(tk) - k] * 55)
        knock[k:] += seg * a
    y = mix((0, poof * 1.0), (0, boom), (at(0.12), knock * 0.55))
    return reverb(finish(y, 0.002), 13, 0.2, 0.2)


def _pop(g, n=0.45, seed_boost=0.0):
    t = t_axis(n)
    cut = (4200 + seed_boost) * np.exp(-t * 7) + 300
    smoke = lowpass(noise(g, n), cut) * env_ar(len(t), 0.004, 0.2, 5)
    body = np.sin(sweep(260 + seed_boost / 10, 70, n)) * np.exp(-t * 18) * 0.7
    click = noise(g, 0.01)
    click = highpass(click, 2000) * np.exp(-np.linspace(0, 1, len(click)) * 8)
    return mix((0, smoke), (0, body), (0, click * 0.6))


def clones():
    return finish(reverb(_pop(rng('clones')), 17, 0.2, 0.18), 0.002)


def clones_wave():
    """Variante para cada nova onda: pop mais agudo, duplo."""
    g = rng('clones-wave')
    a = _pop(g, 0.4, 800)
    b = _pop(g, 0.4, 1400)
    y = mix((0, a), (at(0.07), b * 0.85))
    return finish(reverb(y, 19, 0.2, 0.18), 0.002)


def digital():
    """Glitch: zap com bit-crush, rajadas e arpejo de degraus."""
    g = rng('digital')
    n = 0.6
    t = t_axis(n)
    f = 600 * (6000 / 600) ** np.clip(t / 0.35, 0, 1)
    sq = np.sign(np.sin(np.cumsum(2 * np.pi * f / SR)))
    steps = np.floor(t / 0.04)
    arp = np.sign(np.sin(2 * np.pi * (300 * 2 ** (steps % 5 / 4)) * t))
    y = (sq * 0.5 * env_ar(len(t), 0.003, 0.35, 5) + arp * 0.25 * np.exp(-t * 4))
    nz = noise(g, n)
    gate = (np.sin(2 * np.pi * 23 * t) > 0.2).astype(float) * np.exp(-t * 5)
    y += highpass(nz, 3000) * gate * 0.3
    # bit-crush + redução de taxa
    y = np.round(y * 6) / 6
    hold = 5
    y = np.repeat(y[::hold], hold)[: len(t)]
    return finish(echo(y, [(0.09, 0.2)]))


def dust():
    """Redemoinho de areia: ruído filtrado que gira e se dissipa."""
    g = rng('dust')
    n = 1.3
    t = t_axis(n)
    cut = 2500 + 1500 * np.sin(2 * np.pi * 3.0 * t) - 1200 * t / n
    x = lowpass(noise(g, n), np.maximum(cut, 400))
    x = highpass(x, 500)
    swirl = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * t - 1)
    grains = (g.random(len(t)) > 0.998).astype(float)
    grains = highpass(grains * g.standard_normal(len(t)), 3000) * 4
    y = (x * swirl + grains * 0.3) * env_ar(len(t), 0.12, 0.7, 3.2)
    return finish(reverb(y, 23, 0.25, 0.25), 0.01, 0.1)


def cartoon():
    """Boing seguido de zip cartunesco."""
    n = 0.7
    t = t_axis(n)
    boing_f = 220 + 90 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 6) + 260 * np.exp(-t * 7)
    boing = np.sin(np.cumsum(2 * np.pi * boing_f / SR)) * np.exp(-t * 5)
    boing += 0.3 * np.sin(np.cumsum(4 * np.pi * boing_f / SR)) * np.exp(-t * 7)
    ts = t_axis(0.25)
    zip_ = np.sin(sweep(500, 3200, 0.25)) * np.sin(np.pi * ts / 0.25) * 0.7
    zip_ += 0.3 * np.sign(np.sin(sweep(500, 3200, 0.25))) * np.sin(np.pi * ts / 0.25) * 0.3
    y = mix((0, boing), (at(0.28), zip_))
    return finish(echo(y, [(0.05, 0.15)]))


def portal():
    """Portal que se abre: zumbido em redemoinho com brilho."""
    g = rng('portal')
    n = 1.5
    t = t_axis(n)
    f0 = 110 * (1 + 0.7 * np.clip(t / n, 0, 1))
    fm = np.sin(2 * np.pi * 5 * t) * 6
    hum = np.sin(np.cumsum(2 * np.pi * f0 / SR) + fm)
    hum += 0.5 * np.sin(np.cumsum(2 * np.pi * f0 * 2.01 / SR) + fm)
    hum += 0.3 * np.sin(np.cumsum(2 * np.pi * f0 * 3.02 / SR))
    sh = sine_sweep(300, 2400, n) * (np.clip(t / n, 0, 1) ** 2) * 0.4
    air = bandpass(noise(g, n), 1200, 6000) * (0.4 + 0.4 * np.sin(2 * np.pi * 2.5 * t)) * 0.4
    sparkle = sum(np.sin(2 * np.pi * (1500 + 700 * k) * t) * np.exp(-((t - 0.1 * k) * 10) ** 2) * 0.1
                  for k in range(1, 12))
    e = np.sin(np.pi * np.clip(t / n, 0, 1)) ** 0.6 * np.minimum(t / 0.05, 1)
    y = (hum * 0.5 + sh + air) * e + sparkle
    return finish(reverb(y, 29, 0.35, 0.3), 0.01, 0.15)


def kamehameha_charge():
    """Zumbido de energia em ascensão; laço perfeito de 2 s (frequências inteiras por ciclo)."""
    g = rng('kamehameha-charge')
    n = 2.0
    t = t_axis(n)
    cyc = lambda f: 2 * np.pi * np.round(f * n) / n * t  # frequência inteira por laço
    y = np.zeros_like(t)
    for f, a in ((70, 1.0), (140, 0.7), (210, 0.4), (350, 0.3), (700, 0.15)):
        y += a * np.sin(cyc(f) + 0.7 * np.sin(cyc(3)) * (f / 70) ** 0.3)
    shimmer = np.sin(cyc(1400) + 3 * np.sin(cyc(7))) * (0.5 + 0.5 * np.sin(cyc(2)))
    y += 0.25 * shimmer
    nz = noise(g, n)
    # ruído periodizado: filtra em círculo (concatena 3x e pega o meio)
    big = bandpass(np.tile(nz, 3), 200, 3500)[len(nz): 2 * len(nz)]
    y += 0.25 * big * (0.6 + 0.4 * np.sin(cyc(6)))
    y *= 0.7 + 0.3 * np.sin(cyc(4))
    y = y - y.mean()
    y = y / np.abs(y).max() * PEAK
    return y  # todas as componentes são periódicas em 2 s: o laço fecha sem costura


def kamehameha_fire():
    """Disparo: estalo, rugido de feixe e sub-grave."""
    g = rng('kamehameha-fire')
    n = 2.5
    t = t_axis(n)
    sub = np.sin(sweep(120, 38, n)) * np.exp(-t * 1.1) * np.minimum(t / 0.02, 1)
    sub += 0.4 * np.sin(2 * np.pi * 55 * t) * np.exp(-t * 0.9)
    cut = 6000 * np.exp(-t * 1.4) + 500
    roar = lowpass(noise(g, n), cut) * np.exp(-t * 1.2) * np.minimum(t / 0.015, 1)
    roar *= 0.8 + 0.2 * np.sin(2 * np.pi * 28 * t)
    beam = np.zeros_like(t)
    for f, a in ((220, 1.0), (330, 0.6), (440, 0.5), (880, 0.25)):
        beam += a * np.sin(2 * np.pi * f * t + 2 * np.sin(2 * np.pi * 6 * t))
    beam *= env_ar(len(t), 0.03, 1.6, 2.5) * 0.35
    zap = sine_sweep(6000, 300, 0.4) * np.exp(-t[: at(0.4)] * 10)
    crack = highpass(noise(g, 0.06), 1500) * np.exp(-np.linspace(0, 1, at(0.06)) * 6)
    y = mix((0, sub * 1.1), (0, roar * 0.9), (0, beam), (0, zap * 0.5), (0, crack * 0.8))
    y = soft_clip(y / np.abs(y).max() * 1.4, 1.0)
    y = reverb(y, 31, 0.25, 0.35)[: int(2.5 * SR)]
    return finish(y, 0.001, 0.2)


def restore():
    """Reaparecer: sininho suave de três notas."""
    notes = (784.0, 1046.5, 1568.0)
    parts = []
    for i, f in enumerate(notes):
        tt = t_axis(0.9)
        bell = np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * f * 2.4 * tt) * np.exp(-tt * 12)
        bell *= np.exp(-tt * 4.5) * np.minimum(tt / 0.004, 1)
        parts.append((at(0.09 * i), bell * (1 - 0.15 * i)))
    y = mix(*parts)
    return finish(reverb(y, 37, 0.35, 0.3), 0.002, 0.15)


SOUNDS = {
    'goku': goku, 'anime': anime, 'puff': puff, 'clones': clones, 'clones-wave': clones_wave,
    'digital': digital, 'dust': dust, 'cartoon': cartoon, 'portal': portal,
    'kamehameha-charge': kamehameha_charge, 'kamehameha-fire': kamehameha_fire, 'restore': restore,
}


def write_wav(path: Path, x: np.ndarray) -> None:
    data = (np.clip(x, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / 'assets' / 'sounds'
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn()
        write_wav(out / f'{name}.wav', x)
        print(f'{name}.wav  {len(x) / SR:.2f}s  {(out / f"{name}.wav").stat().st_size // 1024} KB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
