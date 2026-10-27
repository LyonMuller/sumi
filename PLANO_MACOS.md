# Plano de ação — Sumi no macOS

Levantamento feito em 2026-10-27, num Mac Apple Silicon
(macOS 27.0.1, arm64) com Python 3.14.10 do Homebrew e Swift 6.4 (Command Line
Tools, sem Xcode).

## 1. Diagnóstico

### O que já funciona no Mac sem mudar nada

- **Todas as dependências do lock instalam** em macOS arm64 com Python 3.14
  (`pip check` sem erros).
- **Suíte de testes: 110 de 113 passam.** As 3 falhas são só `No module named
  '_tkinter'` (o Python do Homebrew vem sem Tk). Os testes da extensão (Node) passam 7/7.
- **Enumeração de câmeras funciona** com `cv2.CAP_AVFOUNDATION`.
- **O programa de saída (`camera_output/`) roda sem mudança.** O PyVirtualCam 0.15.0
  já tem backend `obs` para macOS 13+ (Camera Extension do OBS 30+).
- **Núcleo de visão, gestos e efeitos é portável**: MediaPipe, NumPy, OpenCV
  (imgproc), protocolo BGR24 por pipe, ponte local do Meet e extensão do Chrome.

### Restrições de plataforma

- **Só Apple Silicon** (`mediapipe==1.1.1` só tem wheel macOS arm64).
- **macOS 13 (Ventura) ou superior** (OpenCV e Camera Extension do PyVirtualCam).
- **OBS Studio 30+** para a câmera virtual, com *System Extension* aprovada pelo
  usuário em Ajustes do Sistema.
- **Unity Capture não existe no Mac.**

### Riscos específicos do Mac

1. **Licença do OpenCV.** O wheel macOS traz FFmpeg com x264, x265 e libpostproc
   (GPL), linkados direto no `cv2.abi3.so`. **Não afeta uso pessoal**: as obrigações
   da GPL só nascem na distribuição. Para distribuir, ver seção 5.
2. **Permissão de câmera (TCC).** O pedido nativo com o texto do app só aparece num
   `.app` com `NSCameraUsageDescription`. Rodando pelo Terminal, a permissão fica com
   o Terminal. Com assinatura ad-hoc, o macOS pode pedir de novo a cada rebuild.
3. **App Nap.** Em segundo plano (usuário na reunião), o macOS pode reduzir timers do
   processo e travar o vídeo da chamada.
4. **F8 em teclado Apple** é tecla de mídia; só chega ao app com `fn`.
5. **Índice da câmera.** A ordem da enumeração precisa bater com o índice aberto pelo
   `VideoCapture(…, CAP_AVFOUNDATION)`.

## 2. Decisões

| # | Decisão | Situação |
|---|---|---|
| D1 | Interface no Mac | **Decidido: app SwiftUI nativo + motor Python como processo auxiliar.** |
| D2 | Uso | **Pessoal, neste Mac.** Distribuição fica como etapa futura (seção 5). |
| D3 | OpenCV com FFmpeg GPL | Sem ação para uso pessoal. Para distribuir: OpenCV próprio sem FFmpeg. |
| D4 | Atalho de restauração | Proposta: F8 (com `fn`) + combinação alternativa configurável, ex.: ⌃⌥R. |
| D5 | Windows | Continua com a interface CustomTkinter atual, compartilhando o motor Python. |
| D6 | Assinatura | Uso pessoal: ad-hoc ou certificado gratuito "Apple Development" (exige Xcode e Apple ID). Distribuição: Developer ID + notarização. |

## 3. Arquitetura escolhida

```
┌─────────────────────────── Sumi.app ────────────────────────────┐
│ SwiftUI (processo principal)                                    │
│  • Onboarding e permissões   • Janela principal e prévia        │
│  • Ajustes (⌘,)              • Atalho global, ⌘Q, App Nap       │
│        │ comandos/estado: JSON por linha (stdin/stdout)         │
│        │ prévia: memória compartilhada (BGRA, buffer duplo)     │
│        ▼                                                         │
│ Contents/Helpers/SumiEngine  (Python congelado, MIT)            │
│  • Captura (AVFoundation via OpenCV) • MediaPipe • efeitos      │
│  • Ponte do Meet (loopback)          • preferências             │
│        │ quadros BGR24 por pipe (protocolo atual, sem mudança)  │
│        ▼                                                         │
│ Contents/Helpers/SumiVideoOutput  (GPL, sem mudança)            │
│        ▼                                                         │
│ OBS Virtual Camera (Camera Extension) ──► Meet / Teams / Zoom   │
└─────────────────────────────────────────────────────────────────┘
```

Por que assim:

- **Permissão de câmera fica no app.** Processos auxiliares dentro do bundle herdam
  o "app responsável" para o TCC, então o motor Python usa a permissão concedida ao
  `Sumi.app`. O Swift faz o pedido com `AVCaptureDevice.requestAccess` na tela
  de boas-vindas, antes de o motor abrir a câmera.
- **Gestos, efeitos e protocolo de saída são reaproveitados** sem reescrita.
- **A separação MIT/GPL continua igual**: o processo de saída segue independente.
- **O Swift cuida do que é do sistema**: atalho global, ⌘Q, App Nap, links para
  Ajustes do Sistema, detecção do OBS.

### Protocolo Swift ↔ motor

- **Comandos** (Swift → motor, uma linha JSON cada): `start_camera`, `stop_camera`,
  `capture_background`, `confirm_background`, `retry_background`, `set_effect`,
  `set_background_mode`, `set_output`, `activate`, `reappear`, `restore`,
  `reconnect_output`, `set_leave_meet`, `list_cameras`, `shutdown`.
- **Eventos** (motor → Swift): `ready`, `state` (fase, dicas, progresso do gesto,
  FPS, status da saída e do Meet), `cameras`, `error`, `preview_frame` (só o índice
  do buffer pronto).
- **Prévia**: arquivo mapeado em memória (ou `shm_open`) com dois buffers BGRA e um
  cabeçalho com largura, altura e índice. O Swift monta um `CVPixelBuffer`/`CGImage`
  e mostra numa `NSView` com `CALayer`, sem copiar pelo pipe.
- **Segurança**: só stdin/stdout do processo filho; nada de porta nova. O motor encerra
  sozinho se o stdin fechar (app morreu), liberando câmera e saída.

### Telas

1. **Boas-vindas / onboarding** (só na primeira vez, reabrível pelo menu Ajuda):
   - Câmera: botão "Permitir câmera" → `requestAccess`; se negada, botão que abre
     `x-apple.systempreferences:com.apple.preference.security?Privacy_Camera`.
   - OBS: detecta `OBS.app` e o dispositivo "OBS Virtual Camera"
     (`AVCaptureDevice.DiscoverySession`). Passos: baixar OBS, abrir uma vez,
     "Iniciar Câmera Virtual", aprovar a extensão em Ajustes → Geral → Itens de
     Início e Extensões. A tela atualiza o status sozinha.
   - Extensão do Meet (opcional): mostra a pasta no Finder e o passo a passo do Chrome.
   - Fundo: leva para a calibração.
2. **Janela principal**: prévia grande, seletor de efeito com ilustração do gesto,
   modo de fundo, "Ativar efeito" / "Reaparecer", "Restaurar", barra de progresso do
   gesto, status da saída e do Meet.
3. **Calibração**: contagem de 4 s, confirmação da imagem vazia, refazer.
4. **Ajustes (⌘,)**: câmera, resolução, tempo de pose, saída (Só prévia / OBS),
   atalho, saída automática do Meet.
5. **Barra de menus (opcional)**: ícone com Restaurar e status, para usar durante a
   reunião sem voltar para a janela.

## 4. Fases

Tamanho: **P** = até meio dia · **M** = 1–2 dias · **G** = 3+ dias.

### Fase 0 — Ambiente (P)

- `brew install python-tk@3.14` (para rodar a interface Tk e os 113 testes).
- venv do projeto, `setup_models.py`, meta de 113/113 testes e `--self-test` ok.
- SwiftUI compila com Swift 6.4 das Command Line Tools via SwiftPM. Xcode é
  opcional (previews e certificado gratuito "Apple Development").

### Fase 1 — Camada de plataforma no Python (M)

Módulo `sumi/platform.py` com o que varia por sistema: pasta de dados
(`~/Library/Application Support/Sumi`), backends de câmera
(`CAP_AVFOUNDATION`), backends de saída (só OBS no Mac), abrir arquivo/pasta,
caminho do executável de saída sem `.exe`. Aplicar em `paths.py`, `devices.py`,
`engine.py`, `virtual_output.py`. Testes simulando cada sistema.

### Fase 2 — Controlador sem interface (M)

Hoje parte da orquestração (calibração, contagem do Meet, preferências, lista de
câmeras, fases e textos) está dentro de `app.py` (Tk). Extrair para
`sumi/controller.py`, sem nenhum import de Tk:

- O app Tk do Windows passa a usar o controlador (sem mudança visível).
- Testes do controlador com motor simulado.

### Fase 3 — Motor como processo auxiliar (M)

- `sumi/service.py` + `--service` no `launcher.py`: lê comandos JSON do
  stdin, publica eventos no stdout, escreve a prévia na memória compartilhada.
- Encerramento limpo quando o stdin fecha. Prazo de resposta para cada comando.
- Testes de protocolo como os de `test_virtual_output.py` (processo real, sem câmera).

### Fase 4 — App SwiftUI (G)

Pasta `macos/` com pacote SwiftPM (`Sumi`):

- `EngineClient`: inicia o motor, envia comandos, decodifica eventos, reinicia se cair.
- `PreviewView`: lê a memória compartilhada e desenha a 30 FPS.
- Telas da seção 3, em português, com as ilustrações de `assets/gestures/`.
- Atalho global com Carbon `RegisterEventHotKey` (sem permissão de Acessibilidade).
- `ProcessInfo.beginActivity` durante a sessão de câmera (App Nap).
- ⌘Q e fechar janela enviam `shutdown` e esperam o motor liberar câmera e saída.
- Modo de desenvolvimento: o app aponta para `.venv/bin/python main.py --service`,
  sem congelar o Python a cada mudança.

### Fase 5 — Montagem do `.app` local (M)

- `tools/build_macos.py`: `swift build -c release`, PyInstaller do motor (onedir) e
  do programa de saída, montagem de `Sumi.app` com `Info.plist`
  (`NSCameraUsageDescription`, `LSMinimumSystemVersion=13.0`, `NSAppSleepDisabled`),
  ícone `.icns` gerado de `assets/brand/app-icon.png`.
- Assinatura de dentro para fora (dylibs, auxiliares, app) com entitlement
  `com.apple.security.device.camera`. Ad-hoc ou "Apple Development".
- `--self-test` do motor congelado dentro do bundle.

### Fase 6 — Validação real (M)

Roteiro manual no Mac: primeira abertura e permissão, câmera negada e depois
liberada, OBS ausente → presente, calibração, todos os gestos, efeitos no Meet
(Chrome), Teams e Zoom, atalho com app em segundo plano, ⌘Q no meio do efeito,
30 minutos em segundo plano (App Nap), câmera USB desconectada durante o uso.

### Fase 7 — Testes e CI (P)

- Separar `tests/test_windows_package.py` em comum e por sistema.
- Testes do controlador, do serviço e da plataforma.
- Testes Swift do decodificador de eventos (`swift test`).
- Opcional: GitHub Actions `macos-15` + `windows-latest`.

### Fase 8 — Documentação (P)

`DESENVOLVIMENTO.md` com seção Mac, `macos/README.md`, `COMO_USAR.md` com OBS no Mac
e permissões, local dos dados em `PRIVACY.md`.

## 5. Futuro: distribuição

Só necessário se o app for entregue a outras pessoas.

1. **OpenCV sem FFmpeg (recomendado).** O app usa só `imgproc` e `VideoCapture`;
   no Mac a captura é AVFoundation, não FFmpeg. Gerar o wheel com
   `CMAKE_ARGS="-DWITH_FFMPEG=OFF"`, sem contrib, fixado por versão e hash.
   O `mediapipe` declara `opencv-contrib-python` como dependência: instalar com
   `--no-deps` ou dar ao wheel próprio esse nome. Reduz ~75 MB.
2. **Tirar o OpenCV do motor no Mac.** Captura via AVFoundation (já disponível no
   lado Swift) e operações com NumPy/Core Image. Mais trabalho.
3. **Aceitar GPL no binário Mac.** O código continua MIT, mas o `.app` vira GPL,
   exige publicar fontes de FFmpeg/x264/x265 e só funciona como GPLv3 por causa do
   MediaPipe (Apache-2.0). Patentes de H.264/HEVC continuam um problema. Não recomendado.

Além disso: Developer ID + notarização (`notarytool`, `stapler`), `.dmg`, avisos de
terceiros atualizados (licença do Python em `lib/python3.14/LICENSE.txt` no
framework do Mac), versão 0.5.0.

## 6. Marcos

| Marco | Fases | Resultado |
|---|---|---|
| M1 — Motor portável ✅ | 0, 1, 2, 3 | Motor roda como serviço no Mac; Windows segue funcionando |
| M2 — App nativo em desenvolvimento 🚧 | 4 | App SwiftUI com onboarding, permissões, prévia e efeitos, usando o venv |
| M3 — `.app` local | 5, 6 | App montado e validado no Meet neste Mac |
| M4 — Acabamento | 7, 8 | Testes, CI e documentação |
| Futuro | 5 (seção) | Distribuição assinada e licenças resolvidas |

## 7. Andamento

**M1 concluído:**

- `sumi/system.py`: pasta de dados, APIs de câmera, opções de saída, abrir
  arquivo, alerta de erro e fonte por sistema.
- `sumi/controller.py`: lógica da sessão extraída de `app.py`, sem Tk.
  `app.py` agora só desenha o estado do controlador; ⌘Q fecha câmera e saída no Mac.
- `sumi/service.py` + `main.py --service [--preview ARQUIVO] [--no-meet]`:
  motor sem janela, comandos JSON por linha, prévia BGRA em memória compartilhada.
- `instalar.command` / `iniciar.command`; seção macOS em `DESENVOLVIMENTO.md`.
- Correção de comportamento: a escolha de fundo "Em movimento" não volta mais para
  "Estático" a cada abertura depois de iniciar a câmera.
- Testes: 135/135 no Mac (eram 113); `smoke_test.py` ok; serviço real lista as
  câmeras e encerra limpo.

Pendente de validação manual: abrir a câmera de verdade no Mac (vai pedir permissão
ao Terminal) e conferir a interface Tk no Windows.

**M2 em andamento** (pasta `macos/`, pacote SwiftPM, macOS 15+):

- `SumiCore`: `EngineClient` (inicia o motor do `.venv`, comandos com resposta,
  estado observável, encerra liberando câmera e saída, App Nap desligado com a câmera
  ligada), `PreviewReader` (lê a prévia com a verificação de quadro incompleto),
  `EngineState`/`EngineEvent`/`EngineCommand` espelhando `service.py`.
- App: boas-vindas com câmera e OBS, janela principal (prévia, ação principal,
  refazer fundo, restaurar, efeito com ilustração do gesto, fundo, saída), Ajustes
  (⌘,) com câmera, Meet e atalhos, menu Câmera, ícone na barra de menus, atalho
  global F8 / ⌃⌥R via Carbon, ⌘Q espera o motor fechar.
- `macos/build-app.sh` monta `Sumi.app` com `Info.plist` e assina com
  "Apple Development" quando existir (senão, ad-hoc).
- Testes Swift: 13/13, incluindo leitura de um quadro escrito pelo Python e o ciclo
  real iniciar → comando → encerrar do motor.
- Mínimo subiu para macOS 15 (barreira de memória do módulo `Synchronization`).

Falta: certificado "Apple Development", permissão de câmera concedida ao app, sessão
real com câmera (calibração, gestos, prévia a 30 FPS) e validação do OBS e do Meet (M3).
