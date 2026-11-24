# Terminais locais

Direção: console utilitário com tons de oliva, tipografia quente e um único
acento âmbar. O principal gesto visual é o nome do projeto como seletor no topo,
com abas grandes imediatamente abaixo. DFII: 14 (impacto 4, contexto 4,
viabilidade 4, desempenho 4, risco 2).

Space Grotesk organiza navegação e títulos; IBM Plex Mono atende terminal e
metadados. Ambas são servidas localmente, com as licenças OFL em `web/vendor/`.
As cores usam variáveis CSS; o ritmo é de 8 px. A única animação é a entrada
curta dos seletores, desativada quando o usuário prefere menos movimento.

Desde 22/10/2026 a interface é compacta para dar altura ao terminal: abas com 34 px,
teclas com 36 px, ícones do topo sem borda e o status online reduzido a um ponto
verde. O rótulo "TERMINAIS / LOCAL" saiu do topo. Folhas (sheets) e listas mantêm 44 px ou mais. O terminal usa 8 px inicialmente,
com ajuste de 8 a 28 px salvo no dispositivo. O seletor de projeto, a barra de
abas e os controles de fonte ficam fora da emulação do terminal. O ajuste de fonte
fica num botão discreto `Aa` no topo, que abre um popover; a barra inferior é só
para teclas do terminal. Cada cliente
usa uma sessão agrupada do tmux para permitir abas independentes por aparelho.

A entrada acontece diretamente no terminal. A barra auxiliar preserva seu foco
ao enviar teclas e ajustar a fonte. O viewport acompanha a abertura do teclado,
e o terminal ajusta as colunas ao espaço disponível. A textarea invisível do
xterm usa 16 px para evitar zoom automático do iOS; o texto visível mantém 8 px.

Alertas usam uma faixa âmbar compacta abaixo das abas e uma lista sob demanda.
O nome do agente e o projeto identificam o destino; indicadores estáticos nas
abas ajudam a localizar pendências. A lista permite abrir o terminal ou dispensar
o aviso, sem abrir diálogos nem mover o foco automaticamente. Reutiliza os tokens,
fontes e ritmo do console utilitário (DFII 14); não há pisca-pisca ou som.

Quotas seguem o mesmo console utilitário (DFII 14): oliva, âmbar, Space e Plex,
ritmo de 8 px e barras finas para o saldo. Um ícone de medidor no topo (desde 22/10/2026; antes era uma aba fixa) abre as contas agrupadas
por provedor; a numeração âmbar mostra a prioridade. Alças e setas têm 44 px e o
arraste usa Pointer Events para funcionar no celular, com rolagem nas bordas.
O terminal permanece conectado enquanto sua área e suas teclas ficam ocultas.

Logos dos agentes (22/10/2026): Claude vem do Simple Icons (CC0, cor #d97757) e
Codex do LobeHub Icons (símbolo atual do app, na cor do texto). Ficam inline em
`AGENT_LOGOS` (web/app.js) e no index.html; aparecem nas abas, na folha de novo
terminal, no estado vazio e nos cabeçalhos das Quotas. Shell usa `>_`. A tela de
Quotas também foi compactada: e-mails mostram o domínio esmaecido sem quebrar.

Arquivos (25/10/2026): console utilitário, DFII 14; mantém Space/Plex, os tokens
oliva/âmbar e o ritmo de 8 px. A entrada é um único ícone de pasta sem borda na
barra de abas, ao lado do `+`. A folha de leitura ocupa 92dvh; no celular lista e
arquivo alternam com `←`; a partir de 720 px ficam lado a lado. Pastas têm ícones
âmbar, documentos ficam esmaecidos e metadados usam Plex. Os controles internos
têm pelo menos 44 px. Sem novas animações. Markdown usa a mesma tipografia e
HTML preserva o estilo do documento. O terminal continua conectado sob a folha.

Transferências (29/10/2026): mantém a direção utilitária, DFII 14, Space/Plex,
tokens oliva/âmbar e ritmo de 8 px. “Enviar arquivos” fica abaixo do filtro;
progresso e destino usam texto anunciado, com botão de cancelar de 44 px.
Uma seta âmbar de 44 px em cada linha e no cabeçalho baixa o original, inclusive
formatos sem prévia. Nomes longos quebram na lista e truncam no cabeçalho.
Sem novas animações ou dependências.

Anexos (25/10/2026): mesma direção utilitária, DFII 14, tokens oliva/âmbar e
Space/Plex. Um clipe âmbar fica fixo à esquerda das teclas, sem depender da
rolagem horizontal. A folha reutiliza o padrão existente, com duas ações
(arquivos/área de transferência), prévias de 48 px, nomes truncados e remoção
em alvos de 44 px. A ação principal adiciona ao rascunho, sem enviar a mensagem.
Não há nova animação. Estado de envio e falhas usam texto anunciado por leitor
de tela; a prévia é mantida quando há falha para permitir nova tentativa.
