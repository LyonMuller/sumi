from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parent
from sumi.model_assets import MODEL_ASSETS
MAX_MODEL_BYTES = 32 * 1024 * 1024

def verify_model(path: Path, expected: str) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f'Modelo inválido: {path.name}. Remova esse arquivo e execute setup_models.py novamente.')

def prepare(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for name, (url, expected) in MODEL_ASSETS.items():
        target = folder / name
        if not target.exists():
            print('Baixando modelo oficial:', name)
            partial = target.with_suffix('.part')
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    if not response.url.startswith('https://storage.googleapis.com/'):
                        raise ValueError('Redirecionamento de modelo não permitido.')
                    with partial.open('wb') as output:
                        total=0
                        while chunk := response.read(1024 * 1024):
                            total+=len(chunk)
                            if total>MAX_MODEL_BYTES: raise ValueError('Modelo excedeu o limite de download.')
                            output.write(chunk)
                verify_model(partial,expected)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        verify_model(target,expected)
        hashes[name] = expected
    (folder / 'checksums.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print('Modelos locais prontos. O aplicativo funciona sem internet.')

if __name__ == '__main__':
    prepare(ROOT / 'models')
