# Release notes

## 1.3.2 — 31/08/2026

### Persistência e conexão da conta Demo

- Corrige o formulário que interpretava o servidor padrão da conta Real como cadastro parcial e interrompia o salvamento antes de gravar a Demo.
- Real e Demo são validadas completamente antes de uma única gravação; um erro em uma seção não deixa a outra parcialmente atualizada.
- Novos botões **SALVAR E USAR DEMO** e **SALVAR E USAR REAL** gravam, verificam a releitura protegida e selecionam o ambiente correto antes de conectar.
- O arquivo de segredos passa a ser substituído atomicamente. Se o Windows não conseguir reler o cadastro protegido por DPAPI, o aplicativo mostra falha em vez de declarar que salvou.
- A senha continua mascarada, não entra em logs, status ou diagnóstico e não é necessária nos testes automatizados.

### Carregamento de candles do MT5

- Quando a consulta inicial entrega menos de 200 barras, o PRIME TRADER solicita ao servidor da corretora um intervalo histórico maior para o mesmo ativo/timeframe.
- Enquanto o MT5 carrega o histórico, o programa repete a leitura automaticamente e mostra o progresso no rodapé sem abrir a mesma caixa de erro a cada tentativa.
- O mínimo de 200 candles continua obrigatório. Se o ativo realmente ainda não possuir essa quantidade, nenhuma análise ou ordem é fabricada.
- Validação local: 415 testes aprovados, zero falhas e um smoke test visual reservado para o runner Windows.

## 1.3.1 — 30/08/2026

### Contas Clear Real e Demo

- Adiciona botões diretos **CONTA REAL** e **CONTA DEMO**, com caminho do terminal, credenciais, histórico e limites financeiros independentes por ambiente.
- Corrige o erro em que o PRIME TRADER esperava a conta Real enquanto o MT5 estava autenticado no Simulador: agora o diálogo permite trocar para a sessão detectada, revisar o cadastro ou cancelar.
- Login, servidor e senha das duas contas podem ser cadastrados uma vez; no Windows, as senhas permanecem protegidas por DPAPI e nunca entram em logs ou mensagens de erro.
- O login automático continua usando o terminal oficial do MT5. O PRIME TRADER não altera arquivos internos nem substitui a autenticação da corretora.

### Execução e gestão de risco

- A conta **Demo** permite execução automática depois que o usuário arma a sessão. A conta **Real** exige confirmação manual para cada ordem, inclusive se uma configuração antiga tentar restaurar o modo automático.
- Entrada, SL e TP automáticos vêm do plano técnico adaptativo existente: ATR, pivôs, suporte/resistência, gestão Scalp/Intraday e R:R mínimo. Uma meta diária nunca força trade, aumento de lote ou alvo artificial.
- Meta diária e stop monetário bloqueiam novas ordens pelo resultado realizado. Nova trava, configurada por padrão em 2, interrompe entradas depois de duas perdas consecutivas no dia; `0` desativa essa regra.
- Os limites são separados entre Real e Demo. A análise e os sinais continuam visíveis quando a execução está bloqueada.
- Validação local: 406 testes aprovados, zero falhas e um smoke test visual reservado para o runner Windows.

## 1.2.6 — 26/08/2026

### Contexto do ativo e 200 candles analíticos

- A janela de decisão passa a exigir exatamente 200 candles analíticos. Se existir uma vela aberta, o controlador busca até 201 registros e usa as 200 velas anteriores fechadas.
- O gráfico continua limitado aos 200 candles mais recentes, enquanto o histórico maior permanece disponível para treinamento e backtest.
- Feed genérico deixa de ser tratado como contexto específico: as manchetes são classificadas como notícia do ativo, notícia ampla do mercado ou irrelevante para o ativo selecionado.
- O contexto auditável inclui notícias recentes, sentimento, alto risco, fontes e idade. Conflito forte em criptomoedas gera aviso ou bloqueio conforme a proteção rigorosa; Forex não recebe direção artificial por sentimento genérico.
- Atualização automática das fontes públicas passa para 60 segundos, sem alegar latência que o provedor externo não garante.

### Sinais manuais e simulação automática

- Novo controle **Simulação automática (sem ordens reais)** pode ser ligado ou desligado sem pausar análise, alertas e sinais.
- Valor por sinal, stop de perda e meta de lucro da sessão simulada são campos livres e persistentes.
- Cada sinal confirmado da simulação é identificado separadamente no SQLite; o resultado é inferido pelo feed público e não é misturado com resultado observado manualmente.
- Ao alcançar `-stop` ou `+meta`, nenhuma nova posição simulada é registrada. O sinal técnico continua visível para uso manual.
- Um botão reinicia a sessão simulada e seus limites sem apagar o histórico anterior.
- VEX e BullEx permanecem integrações visuais somente leitura, sem senha, saldo, cliques ou ordens.
- Validação local: 344 testes aprovados, zero falhas e um smoke test visual reservado para o runner Windows.

## 1.2.5 — 26/08/2026

### Confirmação no início da próxima vela

- A atualização incremental de Forex passa a marcar a vela anterior como fechada quando a primeira cotação do minuto seguinte chega.
- Durante a janela curta de entrada, indicadores, estrutura e sinal são calculados pela última vela concluída; a vela nova permanece aberta no gráfico e não é usada como confirmação.
- Sinais recém-confirmados por candle fechado deixam de ser anulados pelos 1–2 segundos ainda visíveis do ciclo anterior na VEX/BullEx e são associados explicitamente à próxima vela.
- O cronômetro da interface projeta o ciclo seguinte somente para essa confirmação nova; uma leitura comum nos segundos finais continua bloqueada.
- Preço contrário, stop técnico cruzado, sinal antigo, candle aberto, fonte atrasada, estrutura contrária, pullback incompleto e risco de reversão continuam invalidando a entrada.
- Schema 9 e estratégias `pullback-v10` permanecem compatíveis; esta correção de timing não exige novo treinamento.
- Validação local: 337 testes aprovados, zero falhas e um smoke test visual reservado para o runner Windows.

## 1.2.4 — 25/08/2026

### Correção da direção de pullbacks

- A tendência principal passa a ser determinada pela estrutura e pelas EMAs 21/50; o cruzamento temporário da EMA 9 durante a correção não inverte mais compra e venda.
- Uma tendência de alta com correção vendedora aguarda retomada de compra; uma tendência de baixa com correção compradora aguarda retomada de venda.
- A regra simplificada de pullback deixou de conceder pontos ao lado contrário quando as EMAs 21/50 e a estrutura preservam a direção original.
- O contexto explicita tendência principal, direção da correção, quantidade de candles, profundidade em ATR, fase da retomada e invalidação.
- CHOCH confirmado e perda relevante da EMA 50 continuam autorizando a hipótese de mudança estrutural; reversão real não é rotulada como simples pullback.
- Schema 9 adiciona direção estrutural, direção da correção e força de retomada; a profundidade do pullback passa a usar a EMA 21 no sentido correto.
- O backtest reproduz a mesma proteção contra correção invertida e só aceita mudança contrária quando existe rompimento relevante.
- Estratégias `crypto-structure-orderflow-pullback-v10` e `forex-session-priceaction-pullback-v10` separam modelos antigos; após instalar, treine novamente o contexto utilizado.

### Histórico auditável e Excel

- Adiciona tabela SQLite `decision_history` por migração aditiva e índices por data, ativo/timeframe e sinal, sem apagar sinais anteriores.
- Registra configurações alteradas, análise/aguardar, sinal em formação, sinal confirmado, bloqueios, resultado inferido e resultado observado manualmente.
- Cada decisão contém mercado, ativo, timeframe, expiração, perfil, modo, estratégia, payout, entrada, plataforma visível, scores de compra/venda e justificativas dos dois lados.
- Preserva RSI, MACD, EMAs, ADX, ATR, volume disponível, todas as features, padrões, estrutura, Fibonacci, risco de reversão, contexto de notícias/calendário e oito velas recentes.
- Novo botão **HISTÓRICO COMPLETO / EXCEL** apresenta filtros, tabela, detalhamento completo e exportação em thread separada para preservar a fluidez da interface.
- Exporta `.xlsx` real com abas de resumo, operações, decisões, indicadores/features, configurações, velas/pullbacks e notícias/eventos.
- Acerto, equilíbrio financeiro e P&L observado usam somente resultados informados pelo usuário; dados inferidos permanecem separados.
- Notícias externas não são interpretadas como fórmulas Excel. API keys, senhas, cookies, tokens e saldo não entram no histórico.

## 1.2.3 — 25/08/2026

### Auditoria de falsos sinais e entradas próximas do vencimento

- Pullbacks ainda em formação deixam de contar como confluências positivas e não podem confirmar entrada em M1/M3; no modo Confirmação, a retomada é obrigatória em qualquer timeframe.
- A matriz antiga aceitava sete pullbacks incompletos entre dez leituras rápidas sintéticas. A cobertura continua positiva e progressiva, mas nenhuma oportunidade é mantida apenas para cumprir uma meta artificial de quantidade.
- Nova análise causal e simétrica de reversão combina mudança dos fechamentos, desaceleração simultânea de MACD/RSI, rejeição por pavio, perda da EMA 9, divergência recente e fluxo real contrário da Binance.
- Taker buy ausente em Coinbase/Kraken e em velas sem esse dado não é mais confundido com pressão vendedora de 100%.
- Schema 8 adiciona microtendência normalizada por ATR, virada de momentum, distância da EMA 9, validade do taker e desequilíbrio real de agressão; Forex continua sem volume fictício.
- Backtest passa a rejeitar combinações equivalentes de microtendência, momentum, fechamento e fluxo contrário.
- Sinal confirmado deixa de ser preservado quando a nova cotação ultrapassa a invalidação técnica ou se move materialmente contra a entrada.
- VEX e BullEx recusam entradas nos últimos segundos do vencimento real quando a sincronização visual estiver habilitada.
- Pré-sinal por voz só é anunciado quando a opção correspondente estiver explicitamente ativada; sinais confirmados continuam prioritários.
- Novas estratégias `crypto-structure-orderflow-reversal-v9` e `forex-session-priceaction-reversal-v9` isolam modelos antigos. Após instalar, treine novamente o contexto selecionado.
- Interface aprovada, cartão de voz compacto, plataformas somente leitura, fontes públicas, histórico, notícias e controles existentes permanecem preservados.

## 1.2.2 — 24/08/2026

### Níveis técnicos e gráfico estrutural limpo

- Adiciona stop técnico de invalidação e alvo técnico a sinais de compra e venda em todos os modos, sensibilidades e timeframes.
- Os níveis combinam ATR, duração da expiração, pivôs confirmados e suporte/resistência oposta; em expiração fixa são referências visuais e não ordens de encerramento.
- Entrada, stop e alvo aparecem no gráfico e no cartão da operação, com chave `S/A` para ocultar/exibir.
- O SQLite recebe `technical_stop`, `technical_target` e `technical_room_ratio` por migração aditiva, preservando sinais antigos.
- Suporte/resistência visual passa a mostrar no máximo `S1/S2/R1/R2`, escolhendo proximidade, força e recência. Marcadores de pivô visíveis caem de oito para quatro por lado.
- Análise ao vivo exige 100 candles e limita o contexto operacional aos 200 mais recentes; os até 2.000 candles de treino/backtest ficam preservados em histórico separado.
- Entrada contrária à estrutura aguarda CHOCH. Uma mudança antecipada só é aceita quando o regime recente está estável, tem eficiência mínima de 0,60 e pelo menos três confirmações de momentum.
- Espaço reduzido até a zona oposta aparece como aviso e no gráfico sem virar veto duplicado, preservando a progressão Rápido ≥ Equilibrado ≥ Conservador.
- Estratégias passam a `crypto-structure-volume-candles-levels-v8` e `forex-session-priceaction-candles-levels-v8`; modelos anteriores não são misturados.
- Suíte ampliada para 285 testes automatizados, incluindo níveis simétricos, todos os timeframes, janela de candles, gráfico, SQLite e migração 0.9.0.

## 1.2.1 — 24/08/2026

### Recalibração com o instalador 0.9.0 correto

- O novo instalador anexado possui `FileVersion`/`ProductVersion` 0.9.0 e SHA-256 `e8e2e0bc...c881f`.
- O hash coincide exatamente com o segundo build oficial 0.9.0 do commit `a16d551d`, workflow `32508062287`; não é apenas um arquivo diferente com o mesmo número de versão.
- Em quarenta cenários determinísticos sem modelo, o 0.9.0 produziu 30/12/9 leituras por modo nos perfis rápido/equilibrado/conservador. Com modelo sintético alinhado, produziu 27/12/10 em Price Action, 29/12/9 em Confirmação e 29/12/8 em Quantitativo.
- A comparação mostrou que a biblioteca moderna estava transformando toda indecisão confirmada em veto, inclusive quando tendência, momentum e estrutura permaneciam alinhados.
- Doji/indecisão agora é contextual nos perfis compatíveis: continua bloqueando lateralização, transição, exaustão, estrutura oposta, timeframe superior contrário e momentum insuficiente; em tendência alinhada gera aviso de risco sem apagar isoladamente a leitura.
- Price Action rápido/equilibrado, Confirmação rápida e Quantitativo rápido recebem a exceção contextual. Conservador permanece rígido; Confirmação/Quantitativo equilibrados também mantêm o veto.
- O suporte mínimo de transição rápida foi aproximado do comportamento do 0.9.0, mantendo CHOCH, fechamento, momentum e padrão confirmado como evidência principal.
- Estratégias passam a `crypto-structure-volume-candles-v7` e `forex-session-priceaction-candles-v7`, exigindo novo treinamento por contexto.
- A biblioteca de candles, filtros críticos, fontes separadas, VEX/BullEx, histórico, métricas, segurança e layout permanecem preservados.

## 1.2.0 — 24/08/2026

### Política global de sinais baseada na referência estável

- O instalador de referência anexado foi identificado por hash como o build oficial 0.7.0 (`718280a`), apesar de ter sido lembrado como versão 0.9.
- A comparação mostrou que a versão estável usava indicadores e contexto principalmente na pontuação; versões novas acumularam bloqueios de transição, pullback, vela, divergência, S/R, timeframe superior e IA.
- Uma matriz explícita passa a governar os nove cruzamentos de modo e sensibilidade, com exigência progressiva em vez de um filtro M1 isolado.
- Price Action não recebe veto isolado do modelo; Confirmação combina modelo e categorias técnicas; Quantitativo exige modelo treinado e mantém piso/vantagem do modelo.
- Padrão em vela aberta é aviso de formação, nunca confirmação nem veto automático da direção em formação.
- Transição pode prosseguir quando fechamento, momentum ou padrão confirmado superam o mínimo do perfil; CHOCH continua sendo a confirmação estrutural mais forte.
- Penalidades profissionais secundárias viram avisos nos perfis compatíveis; estrutura oposta recém-confirmada, retração profunda e espaço criticamente curto continuam bloqueando.
- Sinais confirmados ficam visíveis por 8 a 12 segundos em todos os modos/timeframes; candle fechado sempre é reprocessado e sinal antigo não é prolongado.
- Estratégias passam a `crypto-structure-volume-candles-v6` e `forex-session-priceaction-candles-v6`.
- Teste determinístico com vinte cenários compartilhados impede que qualquer uma das nove combinações volte a cobertura zero e confirma progressão rápido ≥ equilibrado ≥ conservador.

## 1.1.1 — 24/08/2026

### Correção do excesso de `AGUARDAR` no M1 rápido

- No perfil `RÁPIDO + CONFIRMAÇÃO`, divergência isolada do modelo passa a ser consultiva: ainda reduz o score combinado e gera aviso, mas não anula sozinha uma leitura técnica forte.
- O veto do modelo permanece nos perfis equilibrado/conservador e no modo quantitativo.
- Um sinal confirmado no fechamento fica visível por uma janela de 8 segundos e não é apagado pelo primeiro tick da vela seguinte.
- Vela aberta continua proibida de confirmar sinal; padrão contrário, doji forte, exaustão, fonte atrasada, estrutura e momentum continuam ativos.
- Motivos de veto do modelo recebem prioridade visual; a interface diferencia `Score combinado`, `score técnico` e distribuição não calibrada da IA.
- Expectativa financeira deixou de ser inferida da saída bruta não calibrada do classificador; o indicador financeiro continua baseado nos resultados observados.
- Estratégias passam a `crypto-structure-volume-candles-v5` e `forex-session-priceaction-candles-v5`.
- Sete testes de regressão cobrem a janela M1, expiração da janela, reprocessamento de candle fechado e prioridade consultiva/bloqueante do modelo.

## 1.1.0 — 24/08/2026

### Biblioteca causal de padrões de candles

- Detector normalizado por range/ATR funciona em 1m, 3m, 5m, 15m, 30m, 1h e 4h.
- Padrões de uma vela: doji, spinning top, martelo/pin bar, estrela cadente e marubozu.
- Padrões de duas velas: engolfos, linha de perfuração, nuvem negra, harami, inside/outside bar e tweezers.
- Padrões de três velas: estrelas da manhã/tarde, três soldados brancos e três corvos negros.
- Vela aberta mostra somente padrão em formação; nenhum padrão ou sinal é confirmado antes do fechamento original do feed.

### Correções dirigidas pelas 36 operações demo

- M1/expiração M1 bloqueia padrão contrário, doji/indecisão e sequência exaurida.
- Pullback M1/M3 exige fechamento direcional aprovado pela biblioteca, além de retomada, momentum e rejeição/estrutura.
- Venda sobre pavio inferior e compra sobre pavio superior recebem conflito explícito quando há pin bar/rejeição contrária.
- Backtest usa os mesmos filtros de reversão, indecisão, viés e exaustão das novas features.
- A amostra operacional usada no diagnóstico permanece privada; nenhuma taxa de acerto ou dado de banca é publicado no repositório.

### Modelos, compatibilidade e preservação

- Schema 7 adiciona sete features causais de candle e exige novo treinamento por contexto.
- Estratégias passam a `crypto-structure-volume-candles-v4` e `forex-session-priceaction-candles-v4`.
- Layout, VEX, BullEx opt-in, fontes públicas, segurança loopback, banco, voz, radar, backtest e instalador foram preservados.
- Suíte ampliada para 266 testes, incluindo ausência de look-ahead e bloqueios de padrões no M1.

## 1.0.0 — 22/08/2026

### BullEx segura e preservação da VEX

- Seletor VEX/BULLEX adicionado sem remover a integração existente.
- BullEx desabilitada por padrão, com aceite explícito do alerta da CVM e link para o Ato Declaratório CVM 23.539.
- Perfil de navegador independente, leitura somente de textos visíveis, endpoint CDP aleatório limitado a `127.0.0.1` e hosts explicitamente permitidos.
- Nenhuma senha, cookie, token, saldo, carteira, clique, ordem ou API privada é usada.

### Estratégias, M1 e modelos

- Schema 6 separa features de cripto e Forex. VWAP, OBV e volume relativo são zerados no Forex; cripto preserva volume/taker real da Binance.
- Sessões de Tóquio, Londres e Nova York usam fusos IANA e horário de verão; ATR é normalizado pelo histórico do próprio par.
- Confirmação 1m/1m recusa vela aberta, fonte atrasada, transição sem CHOCH e pullback sem rejeição/estrutura.
- Contextos de modelo agora incluem mercado, ativo, timeframe, expiração, estratégia, sensibilidade, modo e versão de features.
- Walk-forward, purga temporal e proibição de look-ahead foram preservados.

### Métricas e Windows

- P&L por operação usa payout e valor da entrada; profit factor financeiro usa lucro bruto dividido por perda bruta.
- Resultado manual observado substitui, sem confusão, o desfecho inferido pelo gráfico. Histórico agrupado por plataforma, ativo e estratégia.
- Migração SQLite adiciona as novas colunas sem apagar histórico.
- Build testa `tkinter.filedialog`, `messagebox` e `ttk`; o instalador final continua sendo Inno Setup nativo.
- Suíte ampliada para 252 testes, mais o smoke test visual executado no runner Windows.

## 0.9.0 — 21/08/2026

### Leitura estrutural profissional em todos os perfis

- Identificação de regime: tendência de alta/baixa, transição, lateralização, compressão e exaustão com base em EMAs, ADX, eficiência, ATR, RSI e MACD.
- BOS confirma continuação de estrutura; CHOCH identifica mudança de direção somente após fechamento e deslocamento mínimo em ATR.
- Pullback comprador/vendedor verifica impulso anterior, retração, EMA 21/50, Fibonacci, zona estrutural, rejeição e retomada de momentum.
- Correções profundas, falsos rompimentos, resistência/suporte próximos e divergência regular contrária deixam de ser tratados como entradas equivalentes.
- Divergências regulares e ocultas de RSI/MACD utilizam pivôs já confirmados; nenhuma informação futura participa da decisão.
- Perfis rápido, equilibrado e conservador preservados; regras estruturais aplicadas aos modos price action, confirmação e quantitativo e a todos os sete timeframes.
- Doze novas features causais qualificam o treinamento; schema atualizado para exigir retreinamento honesto do ativo e timeframe após a instalação.
- Backtest rejeita extensão excessiva, tendência contraditória, compressão sem rompimento e pressão oposta de reversão.

### Gráfico VEX e desempenho

- Preço real visível no traderoom da VEX atualiza a vela atual sem inventar histórico, ticks, volume ou cotação de ativos OTC.
- Fechamento de vela vindo da Binance continua autêntico; o preço VEX em formação não gera confirmação fictícia.
- Atualização/reanálise calibrada pelo timeframe e pela sensibilidade, mantendo o desenho incremental e reduzindo atraso perceptível.
- Mantidos layout aprovado, cartão de voz compacto, sincronização de ativo/payout/tempo, APIs públicas, notícias e limpeza segura de versões antigas.
- Empacotamento Windows atualizado para remover uma referência obsoleta do scikit-learn.
- Validação expandida para 232 testes automatizados, com 58 novos cenários de estrutura, pullback, reversão, regime, features causais, cotação VEX e empacotamento.

## 0.8.0 — 21/08/2026

### Sincronização local com a VEX Invest

- Novo botão **CONECTAR VEX INVEST** abre o traderoom em Chrome/Edge com perfil exclusivo e conexão restrita ao próprio computador.
- Login é feito diretamente no navegador; o aplicativo não coleta senha, cookies, saldo, campos digitados nem envia ordens.
- Ativo, mercado, payout, expiração, preço e tempo restante são sincronizados somente quando aparecem visivelmente na plataforma.
- As dez criptomoedas prioritárias e pares Forex são normalizados para os provedores públicos existentes.
- Divergência de ativo/preço e mercados OTC são explicados antes de sugerir uma operação incompatível.

### Cronômetro e qualidade da análise

- Corrigido o relógio que reiniciava a cada atualização de candles ou notícias.
- Quando conectada, a VEX fornece a contagem regressiva; sem conexão, o horário original do sinal é preservado.
- Perfil equilibrado/confirmação e conservador recusam direção contrária ao timeframe superior e exigem confirmação independente de tendência/momentum/price action.
- Fechamento contrário da vela é explicado; rejeições profissionais válidas continuam permitidas.
- Força técnica sem IA treinada deixa de ser apresentada como probabilidade calibrada.
- Layout aprovado, cartão de voz reduzido, Binance, Forex público, notícias, APIs e comportamento do modo rápido preservados.
- Conexões SQLite agora são efetivamente fechadas, evitando arquivos bloqueados e falhas de limpeza no Windows.
- O empacotamento interrompe obrigatoriamente se ícone, testes ou instalador apresentarem erro.
- 174 testes automatizados, incluindo 37 cenários dedicados à integração e seis verificações extras de confiabilidade Windows.

## 0.7.2 — 21/08/2026

### Ajuste pontual no cartão de voz da versão aprovada

- A versão 0.7.0 fornecida pelo usuário foi restaurada integralmente como base.
- Apenas o cartão inferior de alertas de voz foi reduzido: alto-falante, texto e onda de áudio ocupam menos espaço.
- A explicação da IA e os últimos sinais recebem prioridade na distribuição horizontal.
- Sensibilidade equilibrada, modo confirmação, estratégias, Forex, criptomoedas, notícias e sinais continuam sem alterações.
- 131 testes, incluindo confirmação do perfil equilibrado e smoke test visual em Windows.

## 0.7.0 — 21/08/2026

### Interface premium, mesmo motor operacional

- Visual redesenhado conforme a referência fornecida: fundo escuro, cabeçalho moderno, status de conexão e distribuição em três colunas.
- Painel lateral com mercado, ativo, gráfico, expiração, sensibilidade, modo, iniciar, pausar, backtest, treinar IA e radar.
- Gráfico maior, timeframes selecionáveis diretamente e cards horizontais para todos os 15 indicadores originais.
- Sinal da IA em destaque com direção, confiança, cenários, calibração, entrada, pagamento, cronômetro e motivos da análise.
- Novos cards de explicação contextual, últimos sinais reais do banco de dados e alertas de voz.
- Ajustes avançados preservam payout, bloqueio por notícias/eventos, atualização de ativos, APIs, logs, desempenho, saúde e limpeza.
- Nenhuma mudança nas estratégias, nos modelos, nas APIs, no Forex, nas notícias ou na lógica dos sinais.
- 129 testes, incluindo smoke test da interface completa no Windows.

## 0.6.1 — 21/08/2026

- Cotação pública de Forex consultada a cada dez segundos, sem usar créditos das APIs opcionais.
- Atualização parcial da vela, precisão apropriada para pares cambiais e remoção de volume inexistente.
- 116 testes automatizados aprovados.

## 0.6.0 — 21/08/2026

### Perfis calibrados por categoria

- CONSERVADOR: alta confirmação, score mínimo 86, cinco confluências e ADX mínimo 20.
- EQUILIBRADO: exigência intermediária, score mínimo 73, quatro confluências e ADX mínimo 15.
- RÁPIDO: leitura imediata, score mínimo 57, duas confluências, ADX mínimo 10 e peso reduzido da IA.
- Momentum, vantagem direcional, extensão do preço, volatilidade, payout e peso da IA agora são configurados separadamente por perfil.
- O backtest utiliza o mesmo ADX, regime de volatilidade, ponto de equilíbrio do payout e exigência direcional do perfil ativo.
- Em 80 cenários sintéticos idênticos: rápido emitiu 74 sinais, equilibrado 66 e conservador 44; esses números validam a separação dos perfis e não representam taxa de acerto.

### Áudio e alertas de risco

- Avisos de notícia/evento não bloqueantes permanecem visíveis, mas não disparam mais a mensagem repetitiva de risco.
- A voz somente anuncia risco quando existe um bloqueio real e a opção de bloqueio automático está ligada.
- Alertas bloqueantes iguais têm intervalo mínimo de cinco minutos, mesmo que outros sinais de voz aconteçam entre eles.
- Sinais confirmados são priorizados; no perfil rápido, uma leitura direcional durante a vela é anunciada como "em formação", sem fingir confirmação.
- Novas notícias e mudanças de aviso não repetem um sinal já anunciado.

### Validação

- 103 testes automatizados aprovados, incluindo 18 novos testes para perfis, áudio, alerta, payout, cooldown e consistência do backtest.

## 0.5.0 — 20/08/2026

### Fontes públicas e ativos da plataforma

- Binance com hosts públicos alternativos, além de Coinbase Exchange e Kraken como fallback gratuito.
- Forex pode iniciar sem chave pelo feed público; Twelve Data e Alpha Vantage são opcionais.
- Frankfurter fornece referência cambial diária, explicitamente separada dos candles intraday.
- Calendário econômico público com cache de uma hora; Finnhub opcional.
- BTC, LTC, ADA, BNB, XRP, ETH, SOL, DOGE, SUI e XLM aparecem no início da lista e no radar.
- Painel visível de notícias com atualização automática/manual, GDELT, Google Notícias e feeds RSS cripto/Forex.

### Estratégias e validação

- Setups de continuação, pullback na EMA 21, rompimento/reteste, liquidez/rejeição, engolfo e timeframe superior.
- IA e leitura técnica combinadas sem esmagar artificialmente um cenário concordante.
- Sensibilidades rápido, equilibrado e conservador possuem exigências distintas e mostram os motivos de AGUARDAR.
- Pagamento da plataforma configurável; ponto de equilíbrio, expectativa e intervalo de Wilson aparecem na análise/backtest.
- Histórico de treino/backtest ampliado para até 2.000 candles; novos sinais e resultados ao vivo alimentam o histórico.
- Amostras pequenas deixaram de gerar aviso amarelo; apenas riscos efetivos permanecem destacados.
- Schema de features atualizado com momentum, rejeição, breakout, contexto macro e sessão operacional.

### Validação

- 85 testes automatizados aprovados, incluindo provedores públicos, fallback, notícias, payout e gravação ao vivo.

## 0.4.1 — 20/08/2026

Versão estável reconstruída a partir do comportamento da v0.3.0.

### Estabilidade e desempenho

- Atualizações de rede e tarefas em segundo plano usam uma fila segura; nenhuma thread chama o Tkinter diretamente.
- Limiares de sinal e backtest foram recalibrados para recuperar cobertura útil sem remover as confirmações principais.
- Treino e backtest carregam até 1.500 candles para aumentar a amostra fora da amostra.
- Aviso de amostra pequena explica que o resultado parcial não é erro e não bloqueia a análise.

### Funções e instalador

- Novo botão **ATUALIZAR GRÁFICO AGORA**.
- Novo botão **LIMPAR CACHE / MODELOS ANTIGOS**.
- Arquivo `Limpar-Cache-PrimeAITrader.cmd` incluído na instalação e no menu Iniciar.
- O instalador oferece limpeza segura de cache/modelos antigos, preservando API keys, configurações e banco de sinais.
- Radar Forex consulta lotes rotativos de 6 pares para respeitar o plano gratuito.
- Auditoria reforçada verifica comandos, existência dos handlers e isolamento das threads da interface.

### Validação

- 56 testes automatizados aprovados no ambiente local.

## 0.4.0 — 20/08/2026

Auditoria funcional e atualização do motor de sinais.

### Correções

- Corrigido o contexto incompleto que impedia a IA treinada de ser usada na primeira análise.
- Backtest e operação ao vivo agora usam os mesmos limites de probabilidade e vantagem sobre o cenário oposto.
- Corrigida a classificação de notícias para não confundir `SEC` com trechos de outras palavras.
- Países do calendário econômico são normalizados para as moedas dos pares Forex.
- Avisos e bloqueios antigos expiram quando saem da janela de risco.
- Calibração não mistura ativos/contextos e exclui `DRAW` da acertividade direcional.
- Botão Desempenho não consulta mais o SQLite na thread da interface.
- Janelas de desempenho e saúde receberam botão FECHAR.

### Qualidade dos sinais

- 1.000 candles no treinamento/backtest quando disponíveis.
- Purga entre treino e teste conforme o horizonte, reduzindo vazamento temporal.
- Modelo escolhido por acerto direcional seletivo com limite inferior de Wilson e cobertura mínima.
- Novas features de retorno intermediário, tendência macro, regime ATR e eficiência de tendência.
- Filtros de volatilidade, extensão do preço, liquidez, espaço até S/R, tendência e momentum.
- RSI comprador e vendedor não possuem mais faixa sobreposta.
- Rótulos neutros usam um limiar adaptado ao ATR e ao mercado.

### Validação

- 49 testes automatizados aprovados localmente.
- Novos testes de contexto completo do modelo, purga temporal, palavras de risco, moedas Forex, features e calibração contextual.

## 0.3.2 — 20/08/2026

- Corrigido o erro do pandas `Unalignable boolean Series provided as indexer` ao treinar.
- Features e rótulos passaram a ser alinhados pelo horário do candle.
- Mensagens de falha deixaram de atribuir erros internos automaticamente à internet/API.

## 0.3.1 — 20/08/2026

- APIs públicas/gratuitas documentadas e bloqueios de risco tornados configuráveis.
- Backtest fraco, notícias e eventos passaram a gerar aviso por padrão.

## 0.3.0 — 20/08/2026

- Features vetorizadas, gráfico ao vivo parcial, mais criptomoedas e 28 pares Forex.
- Modelos separados por contexto e backtest com WIN/LOSS/DRAW coerentes.

## 0.2.0 — 20/08/2026

- Novo dashboard, troca segura de ativo, cache, polling Forex e voz sem repetição.

## 0.1.0 — 20/08/2026

- Primeira versão funcional do aplicativo e instalador Windows.
