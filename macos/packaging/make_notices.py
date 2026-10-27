#!/usr/bin/env python3
"""Writes the third-party notices of the macOS bundle (Contents/Resources/Licenses).

    make_notices.py --engine <SumiEngine folder> --version 0.6.0 --output <folder>

Runs with the packaging venv (macos/.cache/venv), the environment the engine was frozen from. The list
of bundled components is read from the frozen engine itself (its embedded module archive and its folder
layout) and mapped to the installed distributions, so it follows what really shipped. Licence files are
copied from each distribution; texts for what is statically inside the Python interpreter, the PyInstaller
bootloader exception, OpenCV and the GPL video-output program are added next to them.
"""
from __future__ import annotations
import argparse
import importlib.metadata as metadata
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LICENSE_FILE = re.compile(r'(^|/)(LICEN[CS]E|NOTICE|COPYING|AUTHORS|COPYRIGHT)[^/]*$', re.IGNORECASE)
# Reviewed commits of the GPL video-output program's sources (same pins as the Windows release).
FALLBACK_PINS = {'UPSTREAM_COMMIT': 'dbac4732168c21f1337e30182957130f678aa058',
                 'LIBYUV_COMMIT': '19bbedfd3e37329900d34e104021f04d7205ad78'}
REPOSITORY = 'https://github.com/LyonMuller/sumi'


def module_names(program: Path) -> set[str]:
    """Top-level module names inside a PyInstaller executable's embedded archive plus its folders."""
    from PyInstaller.archive.readers import CArchiveReader
    names: set[str] = set()
    archive = CArchiveReader(str(program)).open_embedded_archive('PYZ.pyz')
    names |= {name.split('.')[0] for name in archive.toc}
    internal = program.parent / '_internal'
    for entry in internal.iterdir():
        names.add(entry.name.split('.')[0])
    return names


def bundled_distributions(engine: Path) -> dict[str, metadata.Distribution]:
    owners = metadata.packages_distributions()
    found: dict[str, metadata.Distribution] = {}
    programs = [engine / 'SumiEngine', engine / '_internal' / 'video_output' / 'SumiVideoOutput']
    for program in programs:
        if not program.is_file():
            continue
        for module in module_names(program):
            for distribution in owners.get(module, []):
                found[distribution.lower().replace('_', '-')] = metadata.distribution(distribution)
    found.setdefault('pyinstaller', metadata.distribution('pyinstaller'))
    return dict(sorted(found.items()))


def license_label(distribution: metadata.Distribution) -> str:
    info = distribution.metadata
    expression = info.get('License-Expression')
    if expression:
        return expression
    classifiers = [item.split('::')[-1].strip() for item in info.get_all('Classifier') or []
                   if item.startswith('License ::')]
    if classifiers:
        return ' / '.join(classifiers)
    text = (info.get('License') or '').strip().splitlines()
    return text[0][:80] if text and len(text[0]) <= 80 else 'ver arquivos de licença'


def copy_license_files(distribution: metadata.Distribution, destination: Path) -> list[str]:
    copied: list[str] = []
    for item in distribution.files or ():
        path = item.as_posix()
        if '.dist-info/' not in path and '.egg-info/' not in path:
            continue
        if not LICENSE_FILE.search(path) and '/licenses/' not in path:
            continue
        source = Path(distribution.locate_file(item))
        if not source.is_file():
            continue
        target = destination / source.name
        destination.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            target = destination / (source.parent.name + '-' + source.name)
        shutil.copyfile(source, target)
        copied.append(target.name)
    return copied


def pins() -> dict[str, str]:
    sys.path.insert(0, str(ROOT))
    try:
        from tools import distribution_licenses as shared  # reuse the Windows release's reviewed pins
        return {key: getattr(shared, key) for key in FALLBACK_PINS}
    except Exception:
        return FALLBACK_PINS
    finally:
        sys.path.pop(0)


def models_text() -> str:
    sys.path.insert(0, str(ROOT))
    try:
        from sumi.model_assets import MODEL_ASSETS
    finally:
        sys.path.pop(0)
    cards: dict[str, tuple[str, str]] = {}
    sys.path.insert(0, str(ROOT))
    try:
        from tools.distribution_licenses import MODEL_CARDS
        cards = MODEL_CARDS
    except Exception:
        pass
    finally:
        sys.path.pop(0)
    rows = ['# Modelos MediaPipe', '',
            'Google LLC. Licença: Apache-2.0. Cópias sem alteração, com hashes fixados no aplicativo.',
            'As fichas oficiais de cada família declaram "Apache License, Version 2.0".', '']
    for name, (url, checksum) in MODEL_ASSETS.items():
        rows += [f'## {name}', f'Modelo: {url}', f'SHA256: {checksum}']
        if name in cards:
            rows.append(f'Ficha oficial: {cards[name][1]}')
        rows.append('')
    return '\n'.join(rows)


def build_information() -> str:
    import cv2
    return cv2.getBuildInformation()


def video_io_lines(info: str) -> str:
    start = info.index('Video I/O:')
    end = info.index('\n\n', start)
    return info[start:end]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    engine, output, version = arguments.engine, arguments.output, arguments.version
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)

    distributions = bundled_distributions(engine)
    table = []
    for key, distribution in distributions.items():
        files = copy_license_files(distribution, output / 'packages' / key)
        table.append((distribution.metadata['Name'], distribution.version, license_label(distribution), files))

    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    (output / 'MODELS.md').write_text(models_text(), encoding='utf-8')

    python_folder = output / 'python'
    python_folder.mkdir()
    shutil.copyfile(HERE / 'notices' / 'python-LICENSE.txt', python_folder / 'LICENSE.txt')
    shutil.copyfile(HERE / 'notices' / 'python-incorporated-software.rst', python_folder / 'incorporated-software.rst')
    shutil.copyfile(HERE / 'notices' / 'bzip2-LICENSE.txt', python_folder / 'bzip2-LICENSE.txt')

    import cv2
    opencv_folder = output / 'opencv'
    opencv_folder.mkdir()
    cv2_directory = Path(cv2.__file__).parent
    for name in ('LICENSE.txt', 'LICENSE-3RD-PARTY.txt'):
        shutil.copyfile(cv2_directory / name, opencv_folder / name)
    info = build_information()
    (opencv_folder / 'build-information.txt').write_text(info, encoding='utf-8')

    video_folder = output / 'video-output'
    video_folder.mkdir()
    shutil.copyfile(ROOT / 'camera_output' / 'LICENSE', video_folder / 'GPL-2.0.txt')
    shutil.copyfile(ROOT / 'camera_output' / 'README.md', video_folder / 'README.md')

    pinned = pins()
    lines = [
        f'# Licenças e componentes: Sumi {version} para macOS', '',
        '## Dois programas independentes', '',
        'O aplicativo Sumi (interface SwiftUI e motor Python), de implementação própria, tem licença MIT '
        '(arquivo LICENSE). O motor captura a webcam, reconhece gestos e compõe os efeitos. Não importa '
        'PyVirtualCam nem carrega seus módulos nativos no próprio processo.', '',
        'SumiVideoOutput (Contents/Resources/engine/_internal/video_output) é um programa separado, '
        'GPL-2.0-only. Recebe vídeo BGR24 pela entrada do processo e o entrega à câmera virtual do OBS. '
        'Não importa o app, MediaPipe, OpenCV, gestos, máscaras ou estados da reunião. O texto da GPL '
        'está em video-output/GPL-2.0.txt.', '',
        '### Fontes correspondentes do SumiVideoOutput', '',
        f'- Código do programa de saída: {REPOSITORY}, pasta `camera_output/`, na tag desta versão.',
        f'- PyVirtualCam 0.15.0, commit {pinned["UPSTREAM_COMMIT"]} (https://github.com/letmaik/pyvirtualcam), '
        f'e libyuv, commit {pinned["LIBYUV_COMMIT"]}, sem alterações.',
        '- Os binários nativos do PyVirtualCam vêm da wheel oficial 0.15.0, não foram recompilados. O pacote '
        f'`Sumi-Fontes-Saida-{version}.zip`, publicado junto com este download, reúne esses fontes.', '',
        '## OpenCV sem FFmpeg', '',
        f'O OpenCV {cv2.__version__} deste aplicativo foi compilado do código-fonte oficial (sdist '
        'opencv-python-headless, hash conferido), sem interface gráfica e só com os módulos core, imgproc, '
        'imgcodecs e videoio. O backend FFmpeg está desligado e nenhuma biblioteca de FFmpeg, x264 ou x265 '
        'acompanha o aplicativo; a captura da câmera usa o AVFoundation do macOS. O wheel padrão do PyPI '
        'para macOS traz FFmpeg com codecs GPL, por isso não é usado. Trecho de '
        '`opencv/build-information.txt` (cv2.getBuildInformation):', '', '```', video_io_lines(info), '```', '',
        'Avisos das bibliotecas incluídas no OpenCV (zlib, libjpeg-turbo, libpng, libtiff, libwebp, OpenJPEG '
        'e outras): opencv/LICENSE-3RD-PARTY.txt.', '',
        '## Python e PyInstaller', '',
        f'O motor roda no CPython {sys.version.split()[0]} (distribuição python-build-standalone), congelado '
        'com o PyInstaller. O CPython tem licença PSF (python/LICENSE.txt). Estão embutidos estaticamente '
        'no interpretador: OpenSSL 3.5 (Apache-2.0), expat (MIT), libffi (MIT), libmpdec (BSD-2-Clause), '
        'bzip2 (licença BSD) e liblzma (domínio público); os textos estão em '
        'python/incorporated-software.rst e python/bzip2-LICENSE.txt. O bootloader do PyInstaller é '
        'GPL-2.0 com exceção expressa que permite distribuir programas empacotados sob qualquer licença '
        '(packages/pyinstaller). Tk, Tcl e Pillow não fazem parte deste aplicativo.', '',
        '## Componentes empacotados', '',
        'Lista gerada a partir do motor congelado. Os arquivos de licença de cada pacote estão em '
        '`packages/<pacote>/`.', '',
        '| Componente | Versão | Licença declarada | Arquivos de licença |', '|---|---|---|---|']
    for name, component_version, label, files in table:
        if not files and name.lower().startswith('pyobjc'):
            files = ['mesmo texto MIT de packages/pyobjc-framework-cocoa/LICENSE.txt']
        lines.append(f'| {name} | {component_version} | {label} | {", ".join(files) or "-"} |')
    lines += ['',
              'O MediaPipe (Apache-2.0) traz as bibliotecas LiteRT/TensorFlow Lite, XNNPACK, Protobuf, '
              'Abseil e outras, ligadas estaticamente em libmediapipe.dylib; seus avisos estão no arquivo '
              'NOTICE em packages/mediapipe. O pacote certifi (MPL-2.0) é usado sem alterações. '
              'O NumPy usa o framework Accelerate do macOS e não inclui bibliotecas de álgebra próprias.', '',
              '## Modelos', '',
              'Três arquivos oficiais do Google MediaPipe (Apache-2.0), sem alterações, com hashes fixados '
              'no aplicativo. URLs, hashes e fichas estão em MODELS.md.', '',
              '## OBS e imagens', '',
              'O OBS Studio é instalado separadamente pelo usuário; não incluímos seu instalador, não '
              'registramos drivers e não modificamos sua instalação. Os efeitos são procedurais próprios, '
              'sem mídia de personagens. As ilustrações e a identidade visual foram fornecidas pelo '
              'mantenedor.', '',
              'Este registro documenta a análise de engenharia da distribuição; não é certificação jurídica.']
    (output / 'THIRD_PARTY_NOTICES.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Avisos escritos em {output}: {len(table)} pacotes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
