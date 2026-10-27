"""Satisfies `import matplotlib.pyplot` (executed by mediapipe's drawing_utils) without bundling it.

Sumi never draws with matplotlib; touching the stub raises a clear error instead.
"""
import sys
import types


def _stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []  # type: ignore[attr-defined]

    def missing(attribute: str):
        if attribute.startswith('__'):
            raise AttributeError(attribute)
        raise AttributeError('matplotlib is not included in Sumi (' + name + '.' + attribute + ')')

    module.__getattr__ = missing  # type: ignore[method-assign]
    return module


if 'matplotlib' not in sys.modules:
    package = _stub('matplotlib')
    pyplot = _stub('matplotlib.pyplot')
    package.pyplot = pyplot  # type: ignore[attr-defined]
    sys.modules['matplotlib'] = package
    sys.modules['matplotlib.pyplot'] = pyplot
