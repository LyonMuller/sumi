# Privacidade

- A webcam só abre ao clicar em Iniciar câmera.
- Captura, gesto, recorte, fundo e efeitos são processados localmente.
- Este código não grava nem envia frames, fotos ou áudio. Não usa telemetria,
  anúncios, APIs pagas ou modelos em nuvem. O aplicativo não abre o microfone.
- O fundo preparado fica em memória durante a sessão. Não é salvo como foto.
- user_settings.json guarda escolhas de câmera/qualidade/efeito; pode incluir
  o identificador local da webcam. Não faz parte do Git ou pacote.
- .meet_pairing_key guarda o segredo de conexão local. Não compartilhe esse
  arquivo ou seu conteúdo. Apagá-lo com o aplicativo fechado gera uma nova
  chave na próxima abertura e exige novo vínculo com a extensão.
- No executável, esses arquivos ficam em `%LOCALAPPDATA%\Sumi` (Windows) ou
  `~/Library/Application Support/Sumi` (macOS), separados da instalação e
  preservados ao desinstalar. Executando os fontes, continuam na
  pasta do projeto. O pacote nunca inclui as preferências ou a chave do criador.
- O executável único extrai recursos em uma pasta temporária e remove essa pasta
  ao encerrar normalmente. A extensão opcional é exportada para a pasta de dados
  somente quando você solicita abrir sua pasta; não é instalada no navegador.
- Uma falha ao abrir pode gerar `startup-error.log` nessa pasta, com detalhes
  técnicos e caminhos locais. Confira o conteúdo antes de compartilhar esse log.
- A extensão guarda a chave e a aba vinculada no armazenamento local do
  navegador. Não usa sincronização. Desinstalar a extensão remove esses dados.
- A extensão não solicita câmera ou microfone; seu código não lê chat, áudio,
  vídeo ou DOM da reunião. A permissão de domínio Meet é mais ampla que o uso
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
