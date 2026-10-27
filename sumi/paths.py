"""Read-only packaged resources and per-user writable state."""
from __future__ import annotations
from pathlib import Path
import sys

from .system import user_data_dir


def resource_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def data_root() -> Path:
    # Preserve the existing development installation and its extension pairing.
    if not getattr(sys, 'frozen', False):
        return Path(__file__).resolve().parents[1]
    return user_data_dir()


def data_file(name: str) -> Path:
    folder = data_root()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


EXTENSION_FILES = ('manifest.json', 'package.json', 'background.js', 'heartbeat.js', 'mixer.js',
                   'protocol.js', 'popup.js', 'popup.html', 'popup.css')


def extension_folder() -> Path:
    """Export only on request; Chrome must never depend on onefile's temp folder."""
    source = resource_root() / 'meet_extension'
    if not getattr(sys, 'frozen', False):
        return source
    # One stable folder: Chrome keeps the unpacked extension across app updates.
    destination = data_root() / 'extensao-meet'
    destination.mkdir(parents=True, exist_ok=True)
    for name in EXTENSION_FILES:
        target = destination / name
        content = (source / name).read_bytes()
        if target.is_file() and target.read_bytes() == content:
            continue
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_bytes(content)
        temporary.replace(target)
    return destination
