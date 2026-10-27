# Sumi para macOS

App nativo (SwiftUI) que roda o motor Python do Sumi como processo auxiliar. Exige
**Apple Silicon** e **macOS 15 ou superior**.

```
Sumi.app
├─ Contents/MacOS/Sumi                          interface SwiftUI
├─ Contents/Resources/engine/                   motor Python congelado (PyInstaller)
│  ├─ SumiEngine                                executável do motor
│  └─ _internal/                                bibliotecas, modelos, ilustrações, meet_extension
│     └─ video_output/SumiVideoOutput           programa GPL separado, envia o vídeo ao OBS
└─ Contents/Resources/Licenses/                 avisos de terceiros
```

O app e o motor conversam por JSON em linhas no stdin/stdout, e a prévia passa por um
arquivo em memória compartilhada (protocolo em `sumi/service.py`).

## Desenvolvimento

Precisa do `.venv` do repositório (veja a seção macOS de `DESENVOLVIMENTO.md`), Xcode 26 ou
superior e o certificado "Apple Development" para o macOS lembrar a permissão da câmera entre
builds.

```bash
macos/build-app.sh                 # macos/build/Sumi.app, debug, motor do .venv do repositório
macos/build-app.sh --dev release   # o mesmo, otimizado
open macos/build/Sumi.app
swift test --package-path macos
```

No modo `--dev` o app não é autônomo: ele grava o caminho do repositório no `Info.plist`
(`SumiRepository`) e roda `main.py --service` com o `.venv`, então mudanças no Python não exigem
gerar o app de novo. Para apontar para outra cópia do repositório, defina `SUMI_REPOSITORY`.
O app procura o motor nesta ordem: embutido em `Contents/Resources/engine`, `SUMI_REPOSITORY`,
`SumiRepository` do `Info.plist`.

O log do motor fica em `~/Library/Logs/Sumi/engine.log`.

## Gerar o DMG

```bash
macos/release.sh 0.5.0       # macos/dist/Sumi-0.5.0.dmg e Sumi-0.5.0.dmg.sha256
```

Requisitos extras: `brew install uv cmake` e as Command Line Tools. Na primeira vez o script:

1. baixa o Python 3.14 "standalone" (compatível com macOS 11+, ao contrário do Python do Homebrew,
   que exige a versão do macOS da máquina de build) e cria o ambiente de empacotamento em
   `macos/.cache/` (o `.venv` do repositório não é tocado);
2. compila o OpenCV 4.14.0 do código-fonte **sem FFmpeg** (cerca de 10 minutos) e guarda o wheel em
   `macos/.cache/wheels/`;
3. congela o motor com o PyInstaller (`packaging/sumi-engine.spec`) e confere que o OpenCV não tem
   FFmpeg e que nenhuma biblioteca GPL de mídia entrou;
4. monta e assina o `Sumi.app` de dentro para fora (`packaging/sign.sh`), gera os avisos de terceiros,
   audita todos os binários Mach-O (`packaging/audit_bundle.py`);
5. cria o DMG com atalho para Aplicativos, assina e grava o SHA-256.

As próximas execuções reaproveitam o cache. Passos soltos:

| Comando | O que faz |
|---|---|
| `macos/packaging/bootstrap.sh` | Python, ambiente de empacotamento e wheel do OpenCV |
| `macos/packaging/build-opencv.sh --force` | recompila o OpenCV |
| `macos/packaging/build-engine.sh` | congela o motor e o programa de saída |
| `macos/packaging/verify-engine.sh` | roda, dentro do motor congelado e sem câmera: modelos, inferência, todos os efeitos, programa de saída |
| `macos/build-app.sh --bundle` | monta e assina o `Sumi.app` autônomo |

Fundo do DMG (opcional): `assets/brand/dmg-background.png` (660×400) e, para telas Retina,
`assets/brand/dmg-background@2x.png` (1320×800). O layout da janela é gravado direto no `.DS_Store`
pelo `dmgbuild`, sem automação do Finder. Sem as imagens, o DMG sai sem fundo.

### Assinatura e notarização

Sem conta paga da Apple, o DMG é assinado com o certificado "Apple Development" (ou ad-hoc, se não
houver certificado) e **não é notarizado**: quem instala precisa de "Abrir mesmo assim" (abaixo).
Para passar a Developer ID com notarização, defina antes de rodar o `release.sh`:

```bash
export SUMI_SIGN_IDENTITY="Developer ID Application: Seu Nome (TEAMID)"
xcrun notarytool store-credentials sumi-notary      # uma vez; guarda as credenciais no chaveiro
export SUMI_NOTARY_PROFILE=sumi-notary
macos/release.sh 0.5.0
```

Com `SUMI_NOTARY_PROFILE` o script notariza e grampeia (`stapler`) o app e depois o DMG. O hardened
runtime, o carimbo de tempo da Apple e o entitlement de câmera (`com.apple.security.device.camera`)
já estão ligados para identidades reais; veja `packaging/sign.sh` para `SUMI_TIMESTAMP` e
`SUMI_HARDENED`.

### Licenças

- O OpenCV do PyPI para macOS traz FFmpeg com x264 e x265 (GPL). O Sumi usa um OpenCV próprio, sem
  FFmpeg e só com `core`, `imgproc`, `imgcodecs` e `videoio`. A câmera usa o AVFoundation.
- `SumiVideoOutput` (PyVirtualCam) é GPL-2.0-only e roda como programa separado. Publique junto de cada
  versão o pacote de fontes `Sumi-Fontes-Saida-VERSAO.zip` (o mesmo do Windows).
- `Sumi.app/Contents/Resources/Licenses/THIRD_PARTY_NOTICES.md` lista os componentes que de fato foram
  empacotados, com os textos de licença.

## Como instalar (para quem recebe o DMG)

1. Abra `Sumi-VERSAO.dmg` e arraste o **Sumi** para **Aplicativos**.
2. Abra o Sumi pela pasta Aplicativos. Como o app ainda não é notarizado pela Apple, o macOS mostra
   "o Sumi não pôde ser aberto". Clique em **Concluído** (ou **OK**).
3. Abra **Ajustes do Sistema › Privacidade e Segurança** e role até a seção **Segurança**.
4. Ao lado de "O Sumi foi bloqueado para proteger o Mac", clique em **Abrir mesmo assim**,
   confirme com a senha ou o Touch ID e clique em **Abrir**.

Isso só é preciso na primeira vez. Se preferir o Terminal:
`xattr -dr com.apple.quarantine /Applications/Sumi.app`.

Na primeira abertura o Sumi pede acesso à câmera. Para enviar o vídeo a uma chamada, instale o OBS
Studio 30 ou superior, ative a câmera virtual uma vez e aprove a extensão em Ajustes do Sistema
(a tela de boas-vindas do Sumi mostra o passo a passo). A opção "Só prévia" funciona sem OBS.

## Verificar um build

```bash
codesign --verify --deep --strict --verbose=2 macos/build/Sumi.app
spctl -a -vv macos/build/Sumi.app          # "rejected" é esperado sem notarização
python3 macos/packaging/audit_bundle.py macos/build/Sumi.app --max-minos 15.0
shasum -a 256 -c macos/dist/Sumi-0.5.0.dmg.sha256   # dentro de macos/dist
```
