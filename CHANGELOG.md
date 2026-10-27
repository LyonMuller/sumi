# Histórico de versões

## 0.7.0 — atualizações dentro do app

- **Atualizações automáticas no Mac.** O app procura versões novas uma vez por dia e em
  **Sumi › Verificar atualizações…**; baixa, confere a assinatura, instala e reabre.
- **Contagem do fundo na câmera.** Número grande, anel de progresso e flashes, com flash de
  foto na captura. Duração de 3, 5 ou 10 segundos nos ajustes da câmera.
- **Pausa depois do estalo.** De 0 a 3 segundos entre o estalo e o sumiço, para dar tempo
  de uma fala antes do efeito.

## 0.6.0 — energia, sons e Meet automático

- **Onda de energia.** Junte as mãos em concha na frente do peito para carregar e abra
  as mãos empurrando para disparar. Você continua na imagem.
- **Esfera de energia.** Erga as duas mãos acima da cabeça para reunir uma esfera
  gigante; baixe os braços para lançá-la na direção da câmera, com clarão e onda de choque.
- **Sons dos efeitos.** Cada efeito tem som, também na chamada do Meet (opcional).
  Sons próprios em `sons/`, na pasta de dados, substituem os embutidos.
- **Meet automático.** A extensão encontra e vincula a reunião aberta sozinha, sem código.

## 0.5.0 — primeira versão do Sumi

Suma da webcam com um gesto, com efeitos de ninja e anime, e reapareça quando quiser.

- **macOS e Windows.** App nativo em SwiftUI para Mac (Apple Silicon, macOS 15 ou
  superior), com boas-vindas, permissão de câmera, prévia, atalho global e ícone na
  barra de menus, distribuído em `.dmg`. No Windows, instalador por usuário e
  executável único (x64). O motor de visão e de efeitos é o mesmo nos dois sistemas.
- **Efeitos novos e mais rápidos.** Portal, Kawarimi (fumaça e um tronco no seu lugar)
  e clones de sombra: os clones ficam na imagem, o selo de uma mão chama mais (até 8)
  e cruzar os dedos de novo dispensa todos. Teleporte, poeira, saída digital e saída
  de cena foram otimizados para manter a prévia fluida.
- **Gestos.** Testa, selo de uma mão, selo dos clones, estalo visual, pinça, palma e
  portal. Ajuda ilustrada por efeito, restauração manual e atalho de restauração.
- **Fundo estático por padrão.** Atualização de fundo em movimento como opção experimental.
- **Câmera virtual.** Programa independente de saída de vídeo (BGR24 local, com
  confirmação por quadro e recuperação de falhas) para OBS Virtual Camera.
- **Meet.** Extensão opcional que fecha somente a aba vinculada depois do desaparecimento.
- **Processamento local.** Sem áudio, sem telemetria e sem APIs pagas. Modelos oficiais
  verificados por hash; fontes correspondentes e licenças acompanham os downloads.
- **Dados do usuário.** Configurações e chave do Meet ficam em `%LOCALAPPDATA%\Sumi`
  (Windows) e `~/Library/Application Support/Sumi` (macOS).

Em breve: efeito de onda de energia.
