# Trabalhar nos fontes

Veja [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md) para instalar dependências, entender
os módulos e executar os testes. Veja [DISTRIBUIR.md](DISTRIBUIR.md) para os builds.

O código está público para estudo e reutilização conforme suas licenças. Pull
requests estão desativados em [github.com/LyonMuller/sumi](https://github.com/LyonMuller/sumi).
Você pode trabalhar na sua própria cópia; isso não concede acesso de escrita ao
repositório do mantenedor.

Ao modificar os fontes:

- Preserve as licenças e os avisos dos componentes.
- Use tempo transcorrido nas animações; preserve os buffers de entrada.
- Mantenha a interface na thread principal e evite filas de vídeo atrasado.
- Preserve o comando manual de restauração e a opção de fundo estático.
- Não adicione recursos oficiais de personagens, gravação de reuniões ou serviços
  externos sem tratar explicitamente os termos, permissões e privacidade.
- Alterações no protocolo do Meet precisam manter os limites de SECURITY.md.

Execute a suíte Python, os testes JavaScript e `pip check` antes de distribuir uma
alteração. A instalação real e as chamadas precisam de testes separados.

Nunca publique arquivos `.env`, tokens, chaves, configurações de usuário, vídeos,
modelos baixados ou relatórios com dados pessoais. O empacotador de fontes usa uma
lista restrita de arquivos; ainda assim, revise cada commit e pacote produzido.
Para vulnerabilidades, use o canal privado descrito em [SECURITY.md](SECURITY.md).
