# Como usar o Sumi

## Abrir

### macOS

1. Baixe o `.dmg` em [Releases](https://github.com/LyonMuller/sumi/releases/latest) e arraste o **Sumi** para a pasta **Aplicativos**.
2. Abra o Sumi. Como o app ainda não é notarizado, o macOS bloqueia a primeira abertura:
   vá em **Ajustes do Sistema › Privacidade e Segurança** e clique em **Abrir mesmo assim**.
3. Permita o acesso à **câmera** quando o Sumi pedir. Para mudar depois, use
   **Ajustes do Sistema › Privacidade e Segurança › Câmera**.

### Windows

- **Executável único:** abra `Sumi-Portatil-0.5.0.exe`. Não precisa instalar Python ou extrair pastas manualmente.
- **Instalador:** execute `Sumi-Setup-0.5.0.exe`, conclua e abra pelo menu Iniciar.

Feche a versão anterior antes de abrir outra. A versão portátil salva preferências
no seu usuário; mover ou apagar o .exe não apaga essas preferências.

## Preparar a câmera

1. Vá a Configurar → Câmera (no Mac, Ajustes ⌘,) e selecione sua webcam pelo nome.
2. Inicie a câmera, clique em Capturar fundo (4 s) e saia do enquadramento.
3. Confirme a imagem vazia, volte e escolha o efeito.
4. Use o botão Ativar efeito ou o gesto ensinado em Como fazer.
5. Reaparecer devolve sua imagem; Restaurar interrompe a animação (F8 no Windows; fn+F8 ou ⌃⌥R no Mac).

O fundo Estático é o padrão. Depois, sua escolha manual é lembrada. Em movimento é
experimental. A calibração precisa ser refeita a cada sessão e quando a câmera for movida.

## Enviar vídeo à chamada

1. Instale [OBS Studio pelo site oficial](https://obsproject.com/download) uma vez.
   No Mac, abra o OBS, clique em Iniciar Câmera Virtual e aprove a extensão em
   Ajustes do Sistema › Geral › Itens de Início e Extensões.
2. No app, em Configurar → Câmera, clique em Atualizar lista após instalar o OBS.
3. No Windows, em Configurar → Meet, clique em Preparar vídeo para o Meet. No Mac, escolha
   OBS Virtual Camera como saída.
4. Inicie a câmera no Sumi e escolha **OBS Virtual Camera** nas configurações de vídeo da chamada.
5. Desative desfoque ou outros fundos virtuais da chamada.

Não precisa manter o OBS aberto. Se estiver aberto, deixe a câmera virtual
parada nele para não disputar a saída. Use Reconectar saída no Sumi se necessário.
Meet, Teams e Discord dependem do suporte e das permissões do programa/dispositivo.
No Mac, a opção Só prévia funciona sem o OBS.

## Sair do Meet automaticamente (opcional)

A extensão não participa do vídeo; ela só fecha a aba que você vinculou.

1. No app, abra Configurar → Meet → Abrir pasta da extensão (no Mac, Ajustes › Meet › Mostrar pasta da extensão).
2. No Chrome, abra `chrome://extensions`; no Edge, `edge://extensions`.
3. Ative Modo do desenvolvedor, escolha Carregar sem compactação e selecione a pasta aberta pelo app.
4. No app, copie o código de conexão. Na aba da reunião, abra a extensão, cole o código e clique em Vincular.
5. Ative Sair do Meet após desaparecer e escolha a espera de 2, 3 ou 5 segundos.

Restaurar cancela durante a contagem. Depois que a extensão recebe o pedido,
pode ser tarde para cancelar. A extensão fecha somente a aba vinculada; não encerra
a reunião dos outros participantes. O recurso começa desligado a cada abertura.

Ao atualizar o app, abra a pasta da extensão da nova versão e recarregue-a no
navegador. Os arquivos ficam numa pasta permanente do seu usuário, mesmo no .exe único.
A extensão não está publicada na Chrome Web Store ou na loja do Edge.

## Dados locais e remoção

Configurações, chave e eventual log de falha ficam em `%LOCALAPPDATA%\Sumi` no Windows
e em `~/Library/Application Support/Sumi` no macOS.
Não compartilhe a chave ou as preferências. Para redefinir o app, feche-o e remova
somente `user_settings.json`; para refazer o vínculo, remova `.meet_pairing_key` e vincule de novo.

No Windows, a versão instalada pode ser removida em Configurações → Aplicativos.
O desinstalador preserva as preferências. Na versão de arquivo único, basta fechar
e apagar o .exe. No Mac, arraste o Sumi da pasta Aplicativos para o Lixo. A extensão
e o OBS são gerenciados separadamente por você.
