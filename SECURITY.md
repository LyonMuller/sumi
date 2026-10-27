# Segurança

Esta é uma versão de teste local para macOS e Windows. Não há certificação de segurança
ou garantia de ocultação perfeita. A validação automatizada não substitui o
teste com câmera, driver e navegador reais.

## Fronteiras que devem permanecer

- Frames ficam no app, no processo independente de saída e na câmera virtual
  escolhida; comunicação por pipes anônimos locais, sem serviço de rede adicional.
- A saída é iniciada por caminho fixo do pacote, sem shell, comandos externos ou
  código recebido pela rede. Os canais têm formato/tamanho definidos, um quadro
  em trânsito e prazo de resposta. Um travamento encerra o filho e mantém prévia.
- O evento que permite sair do Meet exige confirmação do quadro pelo componente,
  após o envio real à câmera virtual; falha/timeout não confirma o desaparecimento.
- Extensão não recebe frames e não pede câmera ou microfone. O script no Meet só
  mistura os sons dos efeitos ao microfone que o Meet já abriu; não lê o áudio.
- Ponte HTTP somente em loopback; exige Host exato e Origin igual ao ID fixo da
  extensão (chave pública no manifest). Páginas web não forjam Origin. Não adicionar CORS permissivo ou escuta em 0.0.0.0.
- A saída automática começa desligada, exige vínculo e saída virtual ativa,
  e só começa depois de enviar o frame final do desaparecimento.
- Um comando é de uso único, tem prazo curto e identifica sala e aba. A extensão
  confere novamente o endereço antes de fechar. Não fechar outras abas/janelas.
- Restauração, parada, desvínculo ou perda de conexão cancelam a contagem.
- A atualização de dependências/modelos é explícita. Modelos são conferidos
  contra hashes fixados no código, também durante instalação. O instalador não
  deve regenerar uma linha de confiança a partir de um arquivo alterado.
- Não publicar segredos, preferências, capturas, ambientes virtuais ou arquivos
  de trabalho. O ZIP de fontes exclui modelos. O candidato binário inclui somente
  os três modelos oficiais com hashes fixados e os avisos documentados em
  THIRD_PARTY_NOTICES.md. Configurações e chave são criadas por usuário, fora da instalação.
- O instalador não deve exigir administrador, registrar drivers, instalar
  extensão, iniciar com Windows ou abrir a câmera automaticamente. O OBS é
  instalado separadamente pelo usuário. Não orientar a desativar antivírus.

O segredo não protege contra malware ou outro processo com acesso à mesma
conta do sistema. O atalho de restauração pode estar ocupado por outro aplicativo; a interface
informa o fallback e mantém o botão Restaurar. Após a extensão receber um
pedido de saída, cancelar pode ser tarde demais; o aplicativo não reabre abas.

## Relatar um problema

Para vulnerabilidades, use **Security → Report a vulnerability** em
[github.com/LyonMuller/sumi](https://github.com/LyonMuller/sumi).
Não publique tokens, imagens de reuniões ou passos exploráveis em issues públicas.
Informe versão, impacto e uma reprodução sem dados pessoais pelo canal privado.
Somente a versão mais recente será mantida inicialmente.

## Evidência desta entrega

Testes locais cobrem recusa de token/Origin/Host, expiração, uso único, vínculo,
troca de URL, cancelamento e fallback. Não houve teste de navegador ou câmera
real nesta etapa. A auditoria anterior não certifica alterações futuras.
