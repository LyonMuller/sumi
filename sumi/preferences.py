from __future__ import annotations
from pathlib import Path
import json

from .paths import data_file

BACKGROUND_DEFAULT_REVISION = 'static-v1'


def apply_background_default(values: dict[str, str]) -> None:
    """Apply the safer default once, including upgrades from the live default."""
    if values.get('background_default_revision') != BACKGROUND_DEFAULT_REVISION:
        values['background'] = 'static'
        values['background_default_revision'] = BACKGROUND_DEFAULT_REVISION

def load_preferences(path: Path | None = None) -> dict[str, str]:
    try:
        path = path or data_file('user_settings.json')
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict):
            return {}
        return {k:v for k,v in data.items() if isinstance(k,str) and isinstance(v,str)}
    except (OSError,ValueError):
        return {}

def save_preferences(values: dict[str,str], path: Path | None = None) -> None:
    path = path or data_file('user_settings.json')
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
