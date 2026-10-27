"""Operating-system differences in one place: folders, camera APIs, outputs and texts.

Every function reads ``sys.platform`` when called, so tests can simulate each system.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys

APP_FOLDER = 'Sumi'
OUTPUT_PROGRAM = 'SumiVideoOutput'


def is_windows() -> bool:
    return sys.platform == 'win32'


def is_macos() -> bool:
    return sys.platform == 'darwin'


def _data_dir(folder: str) -> Path:
    if is_macos():
        return Path.home() / 'Library' / 'Application Support' / folder
    local = os.environ.get('LOCALAPPDATA')
    return (Path(local) if local else Path.home() / 'AppData' / 'Local') / folder


def user_data_dir() -> Path:
    """Per-user writable folder of the installed app."""
    return _data_dir(APP_FOLDER)


def user_data_label(name: str = '') -> str:
    """How messages name the user data folder, or a file inside it."""
    if is_macos():
        return f'~/Library/Application Support/{APP_FOLDER}' + (f'/{name}' if name else '')
    return f'%LOCALAPPDATA%\\{APP_FOLDER}' + (f'\\{name}' if name else '')


def camera_backends() -> tuple[int, ...]:
    """OpenCV capture APIs to try, in order, when a device has no known backend."""
    import cv2
    if is_macos():
        return (cv2.CAP_AVFOUNDATION,)
    if is_windows():
        return (cv2.CAP_DSHOW, cv2.CAP_MSMF)
    return (cv2.CAP_V4L2,)


def enumeration_backend() -> int:
    """OpenCV API used to list cameras without opening them."""
    return camera_backends()[0]


def output_choices() -> dict[str, str]:
    """Interface label of each virtual camera choice and the output program backend."""
    choices = {'Só prévia': 'off', 'OBS Virtual Camera': 'obs'}
    if is_windows():
        choices['Unity Capture'] = 'unitycapture'
    return choices


def output_executable(folder: Path) -> Path:
    return folder / (OUTPUT_PROGRAM + '.exe' if is_windows() else OUTPUT_PROGRAM)


def hidden_process_flags() -> int:
    """Avoid console windows for child processes on Windows; no-op elsewhere."""
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0) if is_windows() else 0


def camera_permission_hint() -> str:
    if is_macos():
        return ('Confira a permissão em Ajustes do Sistema → Privacidade e Segurança → Câmera '
                'e feche outros apps que usam a câmera.')
    return 'Confira também a permissão de câmera nas configurações do Windows.'


def ui_font_family() -> str:
    # Tk maps this name to the San Francisco system font on macOS.
    return 'Helvetica Neue' if is_macos() else 'Segoe UI'


def open_path(path: Path) -> None:
    """Open a file or folder with the system's default app. Raises OSError on failure."""
    if is_windows():
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = 'open' if is_macos() else 'xdg-open'
    try:
        subprocess.run([command, str(path)], check=True, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, FileNotFoundError) as error:
        raise OSError(str(error)) from error


def show_fatal_error(message: str) -> None:
    """Best-effort native alert when the interface could not start."""
    try:
        if is_windows():
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'Sumi', 0x10)  # type: ignore[attr-defined]
        elif is_macos():
            subprocess.run(['osascript', '-e', 'on run argv', '-e',
                            'display alert "Sumi" message (item 1 of argv) as critical',
                            '-e', 'end run', message], timeout=120,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, AttributeError, subprocess.SubprocessError):
        pass
