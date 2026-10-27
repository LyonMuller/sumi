"""Stage a reviewable copy of public sources locally, without remote operations."""
from __future__ import annotations
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.package_release import VERSION, release_files


def repository_files(root: Path = ROOT) -> list[Path]:
    return release_files(root)


def prepare(root: Path = ROOT) -> Path:
    destination = root / 'dist' / 'source-review' / f'v{VERSION}' / 'repository'
    paths = repository_files(root)
    expected = {path.relative_to(root).as_posix() for path in paths}
    if destination.exists():
        for path in destination.rglob('*'):
            if path.is_file() and path.relative_to(destination).as_posix() not in expected:
                raise ValueError(f'Arquivo inesperado na revisão: {path.name}')
    destination.mkdir(parents=True, exist_ok=True)
    for source in paths:
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Destino fora da pasta de revisão')
        shutil.copyfile(source, target)
    print(f'Fontes preparados localmente: {len(paths)} arquivos. Nenhuma publicação foi executada.')
    return destination


if __name__ == '__main__':
    prepare()
