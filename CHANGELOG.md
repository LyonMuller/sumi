# Histórico de versões

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
