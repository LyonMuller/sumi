# Executar, estudar e testar

Este repositório contém os fontes completos do Sumi: aplicativos para macOS e
Windows, programa independente de saída de vídeo, extensão opcional, testes e
ferramentas de empacotamento. Para apenas usar o aplicativo no Mac, baixe o `.dmg` na
[Release](https://github.com/LyonMuller/sumi/releases/tag/v0.7.0).

## Preparar o ambiente

Requisitos: Windows x64 ou macOS 13+ em Apple Silicon, Python **3.14 com Tcl/Tk**
e Git para clonar. Linux ainda não é suportado. Node.js 22 ou superior é necessário
somente para os testes da extensão; não faz parte do aplicativo distribuído.

```powershell
git clone https://github.com/LyonMuller/sumi.git
cd sumi
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe setup_models.py
.venv\Scripts\python.exe main.py
```

O download inicial traz três modelos oficiais do Google, com hashes verificados.
Não são necessários tokens nem contas de APIs. Depois de instalar dependências e
modelos, o reconhecimento e os efeitos funcionam localmente.

Como alternativa aos comandos de ambiente, `INSTALAR.bat` usa o comando `python`
e exige que ele aponte para Python 3.14 x64. Depois execute `INICIAR.bat`.
Para gerar pacotes ou executar a suíte completa de testes, instale também
`requirements-build.txt` conforme mostrado acima.

### macOS (Apple Silicon)

O MediaPipe publica o pacote para macOS somente em arm64; Macs Intel não são
suportados. O Python do Homebrew vem sem Tk, então instale os dois:

```bash
brew install python@3.14 python-tk@3.14
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt -r requirements-build.txt
.venv/bin/python setup_models.py
.venv/bin/python main.py
```

`instalar.command` e `iniciar.command` fazem o mesmo com um duplo clique. Rodando
pelo Terminal, a permissão de câmera do macOS fica com o Terminal.

#### App nativo (SwiftUI)

A pasta `macos/` tem o app SwiftUI. Ele inicia o motor como serviço
(`main.py --service`; o protocolo está em `sumi/service.py`) usando o
`.venv` deste repositório, então mudanças no Python não exigem gerar o app de novo.
Exige Xcode 26 ou superior e macOS 15 ou superior.

```bash
macos/build-app.sh            # gera macos/build/Sumi.app (use "release" para otimizar)
open macos/build/Sumi.app
swift test --package-path macos
```

O app pede a câmera com o texto dele e passa a permissão ao motor. Com um
certificado "Apple Development" (Xcode → Settings → Accounts → Manage
Certificates), o macOS lembra a permissão entre builds; com a assinatura ad-hoc,
pede de novo a cada build. Se o Xcode mostrar o certificado mas
`security find-identity -v -p codesigning` listar 0 identidades válidas, falta o
intermediário da Apple: importe `AppleWWDRCAG3.cer` de
apple.com/certificateauthority no chaveiro de login. O log do motor fica em
`~/Library/Logs/Sumi/engine.log`. Para apontar o app para outra cópia do
repositório, defina `SUMI_REPOSITORY`.

No Mac, a saída virtual exige
OBS Studio 30 ou superior com a câmera virtual ativada uma vez e a extensão de
sistema aprovada em Ajustes do Sistema.

Para enviar o resultado a uma chamada, instale o OBS Studio separadamente e
selecione OBS Virtual Camera no serviço de vídeo. A opção Só prévia funciona sem
OBS. Veja [COMO_USAR.md](COMO_USAR.md) para calibrar o fundo e vincular a extensão.

## Por onde começar a leitura

| Arquivo ou pasta | Responsabilidade |
|---|---|
| `main.py`, `sumi/launcher.py` | Entrada do aplicativo e diagnóstico sem câmera |
| `sumi/controller.py` | Lógica da sessão compartilhada pelas interfaces, sem Tk |
| `sumi/app.py`, `theme.py`, `gesture_guides.py` | Interface CustomTkinter, tema e ajuda dos gestos |
| `sumi/service.py` | Motor sem janela para o app nativo: comandos JSON e prévia em memória compartilhada |
| `sumi/system.py` | Diferenças entre sistemas: pastas (e a cópia única da pasta de dados de nome legado), APIs de câmera, saídas e textos |
| `sumi/engine.py` | Captura, processamento e coordenação da sessão |
| `sumi/gesture.py`, `recognition.py` | Geometria, duração das poses e movimentos |
| `sumi/vision.py`, `model_assets.py` | MediaPipe e modelos oficiais com hashes fixados |
| `sumi/scene.py`, `background.py` | Calibração, fundo estático e atualização experimental |
| `sumi/effects.py`, `creative_effects.py` | Composição e animação procedural dos efeitos |
| `sumi/virtual_output.py` | Cliente do processo independente de saída |
| `camera_output/` | Programa GPL de vídeo BGR24 para a câmera virtual |
| `sumi/meet.py`, `meet_extension/` | Vínculo local e saída opcional da aba do Meet |
| `tests/` | Casos sintéticos de gestos, efeitos, protocolo, segurança e distribuição |
| `packaging/`, `tools/` | Receitas de build, avisos, fontes e preparação local |

Fluxo de vídeo: webcam → processamento local e efeitos → quadros BGR24 por pipe
anônimo → programa de saída independente → OBS Virtual Camera → chamada.

A interface permanece na thread principal; o motor executa captura/inferência
fora dela. A saída tem um quadro em trânsito, prazo de resposta e confirmação
após envio à câmera virtual. A extensão não recebe quadros, áudio ou acesso à
webcam: usa uma ponte local autenticada para fechar somente a aba vinculada.
Consulte [SECURITY.md](SECURITY.md) antes de alterar esse protocolo.

## Testes automatizados

Na raiz do repositório, depois de instalar as dependências:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -v
node --test tests/meet_extension.test.mjs
.venv\Scripts\python.exe -m pip check
```

A suíte padrão usa imagens e dados sintéticos e APIs simuladas. Não exige baixar
modelos, abrir a webcam, instalar OBS nem entrar em uma reunião. Algumas provas
iniciam processos e um servidor apenas em loopback, usando portas temporárias.

Depois de baixar os modelos, este diagnóstico adicional executa inferência e
verifica o protocolo do processo de saída sem abrir janela, webcam ou câmera virtual:

```powershell
.venv\Scripts\python.exe -B main.py --self-test --report work/self-test.json
```

O comando não testa o driver real. `smoke_test.py` é outro teste opcional: ele
inicializa a interface, enumera câmeras e pode registrar F8. Não o execute quando
precisar evitar interferência com outros programas.

Para medir somente o compositor com dados sintéticos:

```powershell
.venv\Scripts\python.exe -m tools.benchmark_effects
```

Esses testes não comprovam desempenho ou qualidade em todos os dispositivos.
Valide gestos, calibração, restauração, driver OBS e chamada na máquina de destino.

## Gerar executáveis

As etapas e os requisitos do instalador e do executável único estão em
[DISTRIBUIR.md](DISTRIBUIR.md). O aplicativo não exige Python no computador de quem
baixar os executáveis prontos.

## Arquivos mantidos fora do Git

Modelos baixados, ambientes virtuais, binários, dependências, configurações da
sessão, a chave local do Meet, capturas de webcam, relatórios, prompts de geração
de imagens e rascunhos internos não são necessários para estudar os fontes e não
acompanham o repositório. A instalação gera seus próprios dados locais.

O código principal está sob MIT. O programa independente `camera_output/` está
sob GPL-2.0-only. As dependências preservam suas próprias licenças; consulte
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
