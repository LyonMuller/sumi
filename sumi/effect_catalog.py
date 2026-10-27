"""Stable effect identifiers shared by UI, pipeline and preferences."""
from .effects import AnimeTeleportEffect, TeleportEffect
from .creative_effects import CartoonExitEffect, DigitalEffect, DustEffect
from .effects_portal import PortalEffect
from .effects_ninja import KawarimiEffect, ShadowCloneEffect
from .effects_energy import EnergyWaveEffect
from .effects_spirit import SpiritBombEffect

EFFECTS: dict[str, type[TeleportEffect]] = {
    'anime': AnimeTeleportEffect, 'goku': TeleportEffect, 'puff': KawarimiEffect, 'clones': ShadowCloneEffect,
    'digital': DigitalEffect, 'dust': DustEffect, 'cartoon': CartoonExitEffect, 'portal': PortalEffect,
    'kamehameha': EnergyWaveEffect, 'genkidama': SpiritBombEffect,
}
LABELS: dict[str, str] = {
    'Teleporte anime': 'anime', 'Kawarimi · tronco': 'puff', 'Clones de sombra': 'clones', 'Onda de energia': 'kamehameha', 'Esfera de energia': 'genkidama', 'Saída digital': 'digital',
    'Virar poeira': 'dust', 'Saída de cena': 'cartoon', 'Portal': 'portal',
    'Suave · rastro': 'goku', 'Instantâneo': 'instant',
}
DESCRIPTIONS: dict[str, str] = {
    'anime': 'Linhas de velocidade e um corte rápido, com acabamento de animação.',
    'puff': 'Uma explosão de fumaça e um tronco fica no seu lugar, antes de cair para fora do quadro.',
    'clones': 'Clones surgem de nuvens de fumaça atrás de você e ficam. O selo de uma mão chama mais clones; cruzar os dedos de novo dispensa todos.',
    'kamehameha': 'Junte as duas mãos em concha na frente do peito para carregar; abra as mãos e empurre para a frente para disparar a onda.',
    'genkidama': 'Erga as duas mãos acima da cabeça para reunir uma esfera gigante; baixe os braços para lançá-la na direção da câmera.',
    'digital': 'Seu recorte se desfaz em blocos de videogame.',
    'dust': 'Seu recorte se dissolve em pequenas partículas levadas para o lado.',
    'cartoon': 'Uma arrancada para o lado, com deformação e rastro.',
    'portal': 'Um portal luminoso recolhe seu recorte e se fecha.',
    'goku': 'Distorção suave com rastro luminoso.',
    'instant': 'Troca imediata pelo fundo preparado. É o modo mais leve.',
}
