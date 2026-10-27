"""Export Windows ICO sizes using the visible symbol, preserving the source PNG."""
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SIZES=(16,24,32,48,64,128,256)


def export_icon() -> None:
    source=ROOT/'assets'/'brand'/'app-icon.png'
    target=source.with_suffix('.ico')
    with Image.open(source) as image:
        original=image.convert('RGBA')
    # Ignore near-invisible alpha fringe when calculating the usable artwork bounds.
    bounds=original.getchannel('A').point(lambda alpha:255 if alpha>=8 else 0).getbbox()
    if bounds is None:
        raise ValueError('O PNG do ícone está vazio.')
    artwork=original.crop(bounds)
    frames=[]
    for size in SIZES:
        padding=max(1,round(size*.025))
        symbol=artwork.copy()
        symbol.thumbnail((size-padding*2,size-padding*2),Image.Resampling.LANCZOS)
        frame=Image.new('RGBA',(size,size),(0,0,0,0))
        frame.alpha_composite(symbol,((size-symbol.width)//2,(size-symbol.height)//2))
        frames.append(frame)
    frames[-1].save(target,format='ICO',sizes=[(size,size) for size in SIZES],append_images=frames[:-1])
    print('ICO exportado com símbolo ampliado, proporção preservada e margem reduzida.')


if __name__=='__main__':
    export_icon()
