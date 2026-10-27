"""Efeitos sonoros: resolução de arquivos e reprodução leve, sem dependências."""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from .paths import resource_root
from .system import user_data_dir

BUNDLED_EXTENSIONS = ('.wav',)
OVERRIDE_EXTENSIONS_MAC = ('.wav', '.mp3', '.m4a', '.aiff')
OVERRIDE_EXTENSIONS = ('.wav',)


def _default_runner(args: list[str]):
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


class SoundBank:
    """Resolve nome -> arquivo: pasta do usuário (`sons/`) antes dos sons embutidos."""

    def __init__(self, override_dir: Path | None = None, bundled_dir: Path | None = None,
                 platform: str | None = None):
        self.platform = platform or sys.platform
        self.override_dir = Path(override_dir) if override_dir is not None else user_data_dir() / 'sons'
        self.bundled_dir = Path(bundled_dir) if bundled_dir is not None else resource_root() / 'assets' / 'sounds'

    def _override_extensions(self) -> tuple[str, ...]:
        return OVERRIDE_EXTENSIONS_MAC if self.platform == 'darwin' else OVERRIDE_EXTENSIONS

    def path(self, name: str) -> Path | None:
        if not name or '/' in name or '\\' in name or name.startswith('.'):
            return None
        try:
            for ext in self._override_extensions():
                candidate = self.override_dir / f'{name}{ext}'
                if candidate.is_file():
                    return candidate
            candidate = self.bundled_dir / f'{name}.wav'
            return candidate if candidate.is_file() else None
        except OSError:
            return None

    def names(self) -> list[str]:
        found: set[str] = set()
        try:
            if self.bundled_dir.is_dir():
                found.update(p.stem for p in self.bundled_dir.glob('*.wav'))
            if self.override_dir.is_dir():
                exts = self._override_extensions()
                found.update(p.stem for p in self.override_dir.iterdir()
                             if p.suffix.lower() in exts and not p.name.startswith('.'))
        except OSError:
            pass
        return sorted(found)


class SoundPlayer:
    """Toca efeitos sem bloquear e sem nunca levantar exceção para quem chama."""

    def __init__(self, bank: SoundBank | None = None, enabled: bool = True, volume: float = 0.8,
                 runner: Callable[[list[str]], object] | None = None, platform: str | None = None):
        self.bank = bank or SoundBank()
        self.enabled = enabled
        self.volume = volume
        self.platform = platform or sys.platform
        self._runner = runner or _default_runner
        self._lock = threading.Lock()
        self._procs: set = set()
        self._loops: dict[str, tuple[threading.Event, list]] = {}
        self._win_loop: str | None = None

    # ------------------------------------------------------------ interno
    def _volume(self) -> float:
        try:
            return min(max(float(self.volume), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.8

    def _resolve(self, name: str) -> Path | None:
        if not self.enabled or self._volume() <= 0:
            return None
        try:
            return self.bank.path(name)
        except Exception:
            return None

    def _spawn(self, path: Path):
        if self.platform != 'darwin':
            return None
        try:
            proc = self._runner(['afplay', '-v', f'{self._volume():.2f}', str(path)])
        except Exception:
            return None
        with self._lock:
            self._procs = {p for p in self._procs if _alive(p)}
            self._procs.add(proc)
        return proc

    @staticmethod
    def _kill(proc) -> None:
        try:
            proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _winsound(self):
        try:
            import winsound
            return winsound
        except Exception:
            return None

    # ------------------------------------------------------------ API pública
    def play(self, name: str) -> None:
        try:
            path = self._resolve(name)
            if path is None:
                return
            if self.platform == 'darwin':
                self._spawn(path)
            elif self.platform == 'win32':
                ws = self._winsound()
                if ws is not None and self._win_loop is None:
                    ws.PlaySound(str(path), ws.SND_FILENAME | ws.SND_ASYNC)
        except Exception:
            pass

    def loop(self, name: str) -> None:
        try:
            path = self._resolve(name)
            if path is None:
                return
            if self.platform == 'win32':
                ws = self._winsound()
                with self._lock:
                    if ws is None or self._win_loop == name:
                        return
                    self._win_loop = name
                ws.PlaySound(str(path), ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_LOOP)
                return
            if self.platform != 'darwin':
                return
            with self._lock:
                if name in self._loops:
                    return
                stop = threading.Event()
                holder: list = []
                self._loops[name] = (stop, holder)
            # Optional `<name>-loop` file: the intro plays once, then only that part repeats.
            tail = None if name.endswith('-loop') else self._resolve(f'{name}-loop')
            threading.Thread(target=self._loop_worker, args=(path, stop, holder, tail),
                             daemon=True, name=f'sumi-som-{name}').start()
        except Exception:
            pass

    def _loop_worker(self, path: Path, stop: threading.Event, holder: list,
                     tail: Path | None = None) -> None:
        while not stop.is_set():
            proc = self._spawn(path)
            path = tail or path
            if proc is None:
                return
            holder[:] = [proc]
            if stop.is_set():
                self._kill(proc)
                return
            try:
                proc.wait()
            except Exception:
                pass
            if stop.wait(0.02):
                return

    def stop(self, name: str) -> None:
        try:
            with self._lock:
                entry = self._loops.pop(name, None)
                was_win = self._win_loop == name
                if was_win:
                    self._win_loop = None
            if entry is not None:
                entry[0].set()
                for proc in list(entry[1]):
                    self._kill(proc)
            if was_win:
                ws = self._winsound()
                if ws is not None:
                    ws.PlaySound(None, ws.SND_PURGE)
        except Exception:
            pass

    def stop_all(self) -> None:
        try:
            with self._lock:
                loops = list(self._loops.values())
                self._loops.clear()
                procs = list(self._procs)
                self._procs.clear()
                was_win = self._win_loop is not None
                self._win_loop = None
            for stop, holder in loops:
                stop.set()
                procs.extend(holder)
            for proc in procs:
                self._kill(proc)
            if was_win or self.platform == 'win32':
                ws = self._winsound()
                if ws is not None:
                    ws.PlaySound(None, ws.SND_PURGE)
        except Exception:
            pass

    def is_looping(self, name: str) -> bool:
        with self._lock:
            return name in self._loops or self._win_loop == name


def _alive(proc) -> bool:
    try:
        return proc.poll() is None
    except Exception:
        return False
