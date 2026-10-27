# Gerar e distribuir o Sumi para Windows

## Executáveis prontos

A [Release 0.7.0](https://github.com/LyonMuller/sumi/releases/tag/v0.7.0) ainda não
inclui os executáveis do Windows; gere-os com os passos abaixo. Quando publicados, o
instalador por usuário e o executável único incluem Python, modelos, interface e o
programa independente de saída. O OBS é instalado separadamente pelo usuário para
disponibilizar a câmera virtual. A extensão do Meet é opcional.

Os executáveis ainda não possuem assinatura digital. Não desative as proteções
do Windows para executá-los. Confira os hashes da versão publicada.

## Ambiente de build

Use Windows x64, Python 3.14 x64 com Tcl/Tk e Git. Primeiro prepare o ambiente
seguindo [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md), incluindo modelos e dependências
de `requirements-build.txt`.

Para o instalador, instale o compilador Inno Setup pelo site oficial. O projeto
foi empacotado com Inno Setup 6.7.3; informe o caminho de `ISCC.exe` com `--iscc`.
O executável único não precisa desse compilador.

Na raiz do repositório:

```powershell
.venv\Scripts\python.exe -B tools/fetch_distribution_sources.py
.venv\Scripts\python.exe -B tools/build_windows.py --single-file
.venv\Scripts\python.exe -B tools/build_windows.py --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

O primeiro comando baixa os fontes oficiais do PyVirtualCam 0.15.0, seu submódulo
libyuv e as fichas dos modelos. Os commits e hashes são fixados e conferidos.
Tudo fica em `work/`, fora do Git. Não são instalados drivers por esse comando.
O script não deve precisar de tokens de GitHub.

O build compila o programa independente primeiro, coleta licenças e gera o app.
Confere os modelos, recusa dependências indevidas no agregado e executa diagnósticos
sintéticos dos binários, inclusive em caminhos com espaços e acentos. Não abre a
webcam, não instala o produto e não publica no GitHub.

Os arquivos ficam em `dist/windows/`:

- `Sumi-Portatil-0.7.0.exe`: arquivo único, com extração automática ao abrir.
- `Sumi-Setup-0.7.0.exe`: instalador por usuário, atalhos e desinstalador.
- `Sumi-Fontes-Saida-0.7.0.zip`: fontes correspondentes do programa GPL e de
  suas dependências PyVirtualCam/libyuv.
- `Sumi-Licencas-0.7.0.zip`: avisos, licenças e atribuição dos modelos.
- Arquivos `.sha256`: integridade de cada artefato.

O ZIP com uma pasta de executáveis também é gerado como intermediário local.
O script usa as versões instaladas indicadas nos locks; não promete builds
idênticos bit a bit em outros ambientes.

## Pacote completo de fontes

```powershell
.venv\Scripts\python.exe -B tools/package_release.py
```

Gera `dist/sumi-0.7.0-source.zip` e seu checksum. Inclui código principal,
saída de vídeo, extensão, testes, recursos necessários, dependências declaradas,
receitas e documentação de desenvolvimento. Exclui dados locais, dependências
baixadas, prompts, relatórios e rascunhos internos.

Para preparar uma pasta de revisão local com esses mesmos fontes:

```powershell
.venv\Scripts\python.exe -B tools/prepare_distribution.py
```

Isso não modifica permissões, Git, Releases ou arquivos remotos. Os executáveis
são construídos e publicados separadamente. Para obter todos os fontes de uma
versão, use a tag correspondente ou o pacote completo de fontes oferecido junto
da Release.

## Licenças e publicação

O app principal MIT envia BGR24 por pipes locais ao programa independente GPL;
não importa PyVirtualCam. O processo de saída não importa os módulos de visão ou
da interface. O protocolo genérico está em [camera_output/README.md](camera_output/README.md).
Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) para a análise e condições.

Mantenha os fontes correspondentes e os avisos disponíveis com o mesmo acesso dos
executáveis. Ter fontes do app no Git não dispensa os fontes dos componentes GPL.
Revise arquivos e checksums antes de publicar. Novos builds precisam de seus
próprios testes físicos; aprovação de uma versão anterior não valida uma nova.
Não publique chaves, dados de usuário, ambientes virtuais ou pastas de trabalho.

## macOS

O app do Mac é distribuído em `.dmg` pelas Releases. O build ainda não é assinado com
Developer ID nem notarizado; por isso a primeira abertura exige **Ajustes do Sistema ›
Privacidade e Segurança › Abrir mesmo assim**. A assinatura, a notarização e as licenças
do OpenCV estão em [PLANO_MACOS.md](PLANO_MACOS.md), seção 5.
O app se atualiza sozinho pelo Sparkle a partir do `appcast.xml` da release mais recente; como
publicar está em [macos/README.md](macos/README.md#atualizações-dentro-do-app-sparkle).
