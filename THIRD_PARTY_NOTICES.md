# Licenças e componentes — Sumi 0.6.0

## Dois programas independentes

O aplicativo gráfico, de implementação própria, mantém licença MIT. Ele captura a
webcam, reconhece gestos e compõe os efeitos. Não importa PyVirtualCam e não carrega
seus módulos nativos no próprio processo.

SumiVideoOutput é um programa separado, GPL-2.0-only. Recebe vídeo BGR24 padrão
pela entrada do processo e envia ao driver virtual instalado. Não importa o app,
MediaPipe, OpenCV, Tkinter, gestos, máscaras ou estados da reunião. Pode receber
quadros de qualquer produtor de vídeo bruto. Só confirma o quadro após o envio.

Os arquivos são distribuídos juntos por conveniência, com licenças preservadas;
o arquivo único é um contêiner que extrai e inicia programas independentes.
A análise considera também a interface genérica e a ausência de ligação/importação
entre os módulos, não apenas a existência de processos diferentes.

Referência de critérios: https://www.gnu.org/licenses/gpl-faq.en.html#MereAggregation
Este registro documenta a análise de engenharia da distribuição; não é certificação jurídica.

## Componentes

| Componente | Licença / condição | Uso |
|---|---|---|
| Aplicativo Sumi | MIT, conforme LICENSE | Interface, captura, gestos e efeitos |
| SumiVideoOutput | GPL-2.0-only | Programa independente de saída |
| PyVirtualCam 0.15.0 | GPL-2.0 | Somente no programa de saída |
| libyuv | BSD e avisos/patentes próprios | Incorporado no PyVirtualCam |
| MediaPipe e modelos selecionados | Apache-2.0 | Somente no app principal |
| OpenCV | Apache-2.0 e avisos dos componentes incluídos | Captura (DirectShow/MSMF no Windows, AVFoundation no macOS) e composição |
| NumPy | BSD e avisos das bibliotecas nativas incluídas | Cálculos nos dois programas |
| CustomTkinter / cv2-enumerate-cameras | MIT | Interface e enumeração |
| Pillow | HPND e avisos próprios | Imagens da interface |
| Python | PSF e avisos próprios | Interpretadores empacotados |

O plugin opencv_videoio_ffmpeg não é incluído: a captura usa explicitamente
DirectShow/MSMF. O build recusa sua presença. O processo de saída também exclui
MediaPipe, OpenCV, SSL/OpenSSL e bibliotecas da interface. Textos de licença de
outros pacotes do ambiente podem estar preservados por cautela, sem que seus
binários estejam incluídos.

## Arquivos que devem acompanhar os downloads

- `Sumi-Fontes-Saida-0.6.0.zip`: fonte do programa de saída, receita de build,
  PyVirtualCam v0.15.0 no commit dbac4732168c21f1337e30182957130f678aa058 e o submódulo
  libyuv no commit 19bbedfd3e37329900d34e104021f04d7205ad78, com seus avisos originais.
- `Sumi-Licencas-0.6.0.zip`: avisos coletados, licença GPL completa, termos
  das bibliotecas, atribuição e origem dos modelos.
- `SHA256SUMS.txt`: integridade de todos os artefatos.

Ofereça esses pacotes no mesmo local e com o mesmo acesso dos executáveis. Quem
só quer usar pode baixar apenas instalador ou portátil; não é obrigado a estudar,
compilar ou baixar os fontes. Não distribua o executável negando acesso aos fontes
correspondentes exigidos pela GPL. Os direitos de modificar/redistribuir o componente
GPL são preservados; eles não concedem acesso de escrita ao repositório do mantenedor.

Os fontes de terceiros são sem alterações; a saída de vídeo própria é uma obra
nova e licenciada GPL-2.0-only. Os binários nativos usados vêm da wheel oficial
PyVirtualCam 0.15.0, não foram recompilados; o arquivo de fontes inclui os fontes
correspondentes da versão e os scripts upstream. Não se promete reprodução bit a bit.

## Modelos

São três arquivos oficiais Google MediaPipe, sem alterações, com hashes fixados
no aplicativo. As fichas oficiais de Hand Tracking Lite/Full, BlazeFace Short Range
e Selfie Segmentation declaram Apache License, Version 2.0. O arquivo MODELS.md do
pacote de licenças relaciona URLs e hashes dos modelos e das fichas consultadas.
O texto Apache-2.0 e o NOTICE do MediaPipe estão incluídos nos avisos.

## OBS, inspiração e imagens

OBS Studio é instalado separadamente pelo usuário; não incluímos seu instalador,
registramos drivers nem modificamos sua instalação.

VanishCam (https://github.com/Nicovic17/vanish_webcam) foi referência técnica inicial.
Não distribuímos seu código ou recursos. Os efeitos são procedurais próprios; não
incluímos áudio ou mídia oficial de personagens. As ilustrações e a identidade
visual foram fornecidas pelo mantenedor para uso no aplicativo e na documentação.

## Efeitos sonoros

Os sons em `assets/sounds/` vêm de gravações e efeitos publicados em domínio público
(Creative Commons 0, CC0 1.0), cortados e normalizados para o aplicativo. Título, autor e
endereço de cada fonte estão em `assets/sounds/CREDITS.md`. Nada foi tirado de anime, série,
jogo ou filme. Para trocar qualquer som, coloque um arquivo com o mesmo nome (por exemplo
`goku.wav`) na pasta `sons/` dos dados do usuário.
