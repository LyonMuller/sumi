"""Development-only retrieval of pinned source/notices; never used by the app."""
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.distribution_licenses import MODEL_CARDS, MODEL_CARD_HASHES, UPSTREAM_COMMIT, git, sha256, upstream_files


def prepare() -> None:
    source = ROOT / 'work' / 'vendor' / 'pyvirtualcam-0.15.0'
    if not source.resolve().is_relative_to((ROOT / 'work').resolve()):
        raise ValueError('Destino fora da pasta de trabalho')
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', 'v0.15.0',
                        'https://github.com/letmaik/pyvirtualcam.git', str(source)], check=True)
    if git(source, 'rev-parse', 'HEAD').decode().strip() != UPSTREAM_COMMIT:
        raise ValueError('Commit upstream mudou; não alterar a confiança automaticamente')
    subprocess.run(['git', '-C', str(source), 'submodule', 'update', '--init', '--depth', '1',
                    '--', 'external/libyuv'], check=True)
    upstream_files()
    folder = ROOT / 'work' / 'compliance' / 'model-cards'
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_CARDS.values():
        path = folder / name
        if not path.exists():
            partial = path.with_suffix('.part')
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    if not response.url.startswith('https://storage.googleapis.com/'):
                        raise ValueError('Redirecionamento inesperado')
                    content = response.read(8 * 1024 * 1024 + 1)
                if len(content) > 8 * 1024 * 1024 or not content.startswith(b'%PDF'):
                    raise ValueError('Ficha de modelo inválida')
                partial.write_bytes(content)
                if sha256(partial) != MODEL_CARD_HASHES[name]:
                    raise ValueError('A ficha mudou; requer nova revisão')
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
        if sha256(path) != MODEL_CARD_HASHES[name]:
            raise ValueError('Ficha local diferente da revisada')
    print('Fontes e fichas oficiais conferidos. Nenhum modelo ou driver foi instalado.')


if __name__ == '__main__':
    prepare()
