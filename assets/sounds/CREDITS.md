# Créditos dos efeitos sonoros

Os sons de `assets/sounds/` têm duas origens.

## Trechos de anime (não CC0)

Os arquivos abaixo são trechos de efeitos sonoros originais de anime, baixados de
soundboards públicos, cortados (sem as falas) e com volume igualado: mono, 16 bits, 22,05 kHz.
**Não são de domínio público nem estão sob a licença MIT do Sumi.** Os direitos pertencem
aos respectivos titulares (Dragon Ball © Bird Studio/Shueisha, Toei Animation; Naruto ©
Masashi Kishimoto/Shueisha, Studio Pierrot). Estão aqui só para uso pessoal e sem fins
comerciais e serão removidos a pedido de quem detém os direitos.

| Arquivo | Origem | Obra |
| --- | --- | --- |
| `kamehameha-charge.wav`, `kamehameha-charge-loop.wav` | carga do Kamehameha (início tocado uma vez, depois o trecho de loop repete), via [Myinstants](https://www.myinstants.com) | Dragon Ball |
| `kamehameha-fire.wav` | disparo do raio, via [Myinstants](https://www.myinstants.com) | Dragon Ball |
| `goku.wav` | Teletransporte (Transmissão Instantânea), via [Myinstants](https://www.myinstants.com) | Dragon Ball |
| `puff.wav` | fumaça do jutsu, via [Voicemod Tuna](https://tuna.voicemod.net) | Naruto |
| `clones.wav` | som do selo seguido da fumaça das sombras; a fala "Kage Bunshin no Jutsu" foi removida, via [Voicemod Tuna](https://tuna.voicemod.net) | Naruto |
| `clones-wave.wav` | só a fumaça das sombras, do mesmo arquivo | Naruto |

A Esfera de energia (`genkidama-*`) usa os sons do Kamehameha até ganhar arquivos próprios.

## Sons CC0

Os demais foram feitos a partir de gravações e efeitos publicados em **domínio público /
Creative Commons 0 (CC0 1.0)** (<https://creativecommons.org/publicdomain/zero/1.0/>). CC0 não
exige atribuição; os créditos abaixo são uma cortesia e deixam a origem rastreável.

Fonte: [Freesound](https://freesound.org). Foi usada a prévia em MP3 de alta qualidade de cada
item (a licença de cada página foi conferida como "Creative Commons 0"). Cada WAV final é
mono, 16 bits, 44,1 kHz, com o silêncio inicial removido, corte no tamanho final, fade de
saída e pico normalizado em cerca de -3 dBFS. Quando um arquivo usa mais de uma fonte, elas
estão misturadas.

| Arquivo | Título | Autor | Fonte | Licença |
| --- | --- | --- | --- | --- |
| `anime.wav` | Clean fast Swoosh | Danjocross | <https://freesound.org/people/Danjocross/sounds/507466/> | CC0 |
| `digital.wav` | Digital Glitch_v1 + Cyberpunk Glitch Hologram Transition Whoosh | tadaizm | <https://freesound.org/people/tadaizm/sounds/458065/> | CC0 |
| | | brktkrgll | <https://freesound.org/people/brktkrgll/sounds/856168/> | CC0 |
| `dust.wav` | Short Wind/Air Woosh (A gust of wind) + FX - Swoosh Swirl | NIKOKnecht | <https://freesound.org/people/NIKOKnecht/sounds/569109/> | CC0 |
| | | Breviceps | <https://freesound.org/people/Breviceps/sounds/445963/> | CC0 |
| `cartoon.wav` | Cartoon dash / dodge type SFX | modusmogulus | <https://freesound.org/people/modusmogulus/sounds/789383/> | CC0 |
| `portal.wav` | Scifi, portal, energy, wispy, airy, magic, electric, designed, loop + Black Portal - Dark Dimension Rift | Oldome | <https://freesound.org/people/Oldome/sounds/870393/> | CC0 |
| | | LilMati | <https://freesound.org/people/LilMati/sounds/657653/> | CC0 |
| `restore.wav` | GLEAM-GLOW-SFX-CHIME | newagesoup | <https://freesound.org/people/newagesoup/sounds/351408/> | CC0 |

Para trocar qualquer som, coloque um arquivo com o mesmo nome na pasta `sons/` dos dados do
usuário (veja `THIRD_PARTY_NOTICES.md`). `tools/make_sounds.py` é só o antigo gerador de
reserva; os arquivos distribuídos vêm das tabelas acima.
