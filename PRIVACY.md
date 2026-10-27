# Privacidade

- A webcam só abre ao clicar em Iniciar câmera.
- Captura, gesto, recorte, fundo e efeitos são processados localmente.
- Este código não grava nem envia frames, fotos ou áudio. Não usa telemetria,
  anúncios, APIs pagas ou modelos em nuvem. O aplicativo não abre o microfone.
- O fundo preparado fica em memória durante a sessão. Não é salvo como foto.
- user_settings.json guarda escolhas de câmera/qualidade/efeito; pode incluir
  o identificador local da webcam. Não faz parte do Git ou pacote.
- No executável, esses arquivos ficam em `%LOCALAPPDATA%\Sumi` (Windows) ou
  `~/Library/Application Support/Sumi` (macOS), separados da instalação e
  preservados ao desinstalar. Executando os fontes, continuam na
  pasta do projeto. O pacote nunca inclui as preferências do criador.
- O executável único extrai recursos em uma pasta temporária e remove essa pasta
  ao encerrar normalmente. A extensão opcional é exportada para a pasta de dados
  somente quando você solicita abrir sua pasta; não é instalada no navegador.
- Uma falha ao abrir pode gerar `startup-error.log` nessa pasta, com detalhes
  técnicos e caminhos locais. Confira o conteúdo antes de compartilhar esse log.
- A extensão guarda só o último estado da conexão (app aberto, código da
  reunião) no armazenamento local do navegador. Não usa sincronização.
- A extensão não pede permissão de câmera ou microfone e não lê chat, vídeo ou
  DOM da reunião. Quando o próprio Meet abre o seu microfone, a extensão mistura
  os sons dos efeitos a ele no navegador, para que entrem na chamada. O áudio
  não é gravado, lido nem enviado a outro lugar. Desligue em Sons → Tocar os
  sons na chamada.
- Os sons dos efeitos também tocam no seu Mac/PC. São sons originais gerados
  pelo projeto; você pode trocá-los pondo arquivos com o mesmo nome em `sons/`
  na pasta de dados. A permissão de domínio Meet é mais ampla que o uso
  atual: futuras alterações precisam de revisão, não de confiança automática.
- A ponte escuta somente em 127.0.0.1:49321. O navegador consulta essa ponte
  local; não há servidor externo nosso. A instalação dos fontes usa internet para
  baixar pacotes/modelos; o candidato empacotado já os inclui. O download opcional
  do OBS usa o site oficial. A chamada transmite pelo serviço escolhido.
- O programa independente de saída recebe apenas quadros BGR24 por pipes locais
  privados do sistema operacional. Não recebe chave Meet, gestos, chat ou áudio.
  Não abre servidor ou grava quadros. É iniciado/encerrado com a saída virtual.
- A câmera virtual entrega o vídeo ao programa que você selecionar. A política
  de gravação, transmissão e retenção do Meet/Teams/Discord é a desse serviço.

Segmentação pode falhar e mostrar partes da pessoa. Desaparecer não é um
recurso de anonimização ou proteção de informação sensível.
