#!/usr/bin/env python3
"""Audits every Mach-O under a folder: portability and licence gates for the macOS bundle.

    audit_bundle.py <folder> [--max-minos 15.0]

Fails (exit 1) when a binary
  * links a library outside macOS itself and outside the bundle (a /opt/homebrew path would crash
    on every other Mac),
  * is a GPL media library (FFmpeg family, x264, x265, libpostproc, libvlc),
  * needs a newer macOS than --max-minos, or contains an x86_64 slice.
Prints a summary: file count, highest minimum macOS and the non-system libraries found.
"""
from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
GPL_NAMES = re.compile(r'(^|/)(lib)?(avcodec|avformat|avutil|avdevice|avfilter|swscale|swresample|postproc|'
                       r'x264|x265|xvidcore|vlc)[-.\d]*\.(dylib|so)|videoio_ffmpeg', re.IGNORECASE)


def macho_files(folder: Path):
    for directory, _, names in os.walk(folder):
        for name in names:
            path = Path(directory) / name
            if path.is_symlink():
                continue
            try:
                with path.open('rb') as handle:
                    if handle.read(4) in MAGICS:
                        yield path
            except OSError:
                pass


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split('.')[:2])


def minos(path: Path) -> str | None:
    result = subprocess.run(['otool', '-l', str(path)], capture_output=True, text=True).stdout
    # LC_BUILD_VERSION (platform 1 = macOS) or the older LC_VERSION_MIN_MACOSX.
    found = re.findall(r'cmd LC_BUILD_VERSION\n\s+cmdsize \d+\n\s+platform (\d+)\n\s+minos ([\d.]+)', result)
    found = [version for platform, version in found if platform == '1']
    found += re.findall(r'cmd LC_VERSION_MIN_MACOSX\n\s+cmdsize \d+\n\s+version ([\d.]+)', result)
    return max(found, key=version_tuple) if found else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--max-minos', default='15.0')
    arguments = parser.parse_args()
    problems: list[str] = []
    highest = ('0.0', None)
    external: dict[str, set[str]] = {}
    count = 0
    for path in macho_files(arguments.folder):
        count += 1
        relative = path.relative_to(arguments.folder).as_posix()
        if GPL_NAMES.search(relative):
            problems.append(f'GPL media library: {relative}')
        listing = subprocess.run(['otool', '-L', str(path)], capture_output=True, text=True).stdout.splitlines()[1:]
        for line in listing:
            target = line.strip().split(' (')[0]
            if not target.startswith('/') or target.startswith(('/usr/lib/', '/System/')):
                continue  # @rpath/@loader_path, or macOS itself
            external.setdefault(target, set()).add(relative)
            problems.append(f'non-system library {target} linked by {relative}')
            if GPL_NAMES.search(target):
                problems.append(f'GPL media library {target} linked by {relative}')
        archs = subprocess.run(['lipo', '-archs', str(path)], capture_output=True, text=True).stdout.split()
        if 'x86_64' in archs:
            problems.append(f'x86_64 slice in {relative} ({" ".join(archs)})')
        version = minos(path)
        if version:
            if version_tuple(version) > version_tuple(highest[0]):
                highest = (version, relative)
            if version_tuple(version) > version_tuple(arguments.max_minos):
                problems.append(f'{relative} needs macOS {version} (> {arguments.max_minos})')
    print(f'{count} Mach-O files; highest minimum macOS: {highest[0]} ({highest[1]})')
    for line in sorted(set(problems)):
        print('PROBLEM:', line)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
