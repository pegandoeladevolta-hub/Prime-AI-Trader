# Estratégia e validação

## Objetivo

O motor tenta selecionar operações com evidência convergente e prefere `AGUARDAR` quando o contexto é ambíguo. Nenhuma técnica produz alta acertividade de forma permanente em todos os regimes.

## Filtros usados

1. **Tendência em mais de uma escala** — alinhamento das EMAs 9/21/50, inclinação da EMA 50, estrutura HH/HL ou LH/LL e um segundo conjunto de 200 barras concluídas buscado diretamente no timeframe superior público.
2. **Momentum** — MACD e sua aceleração, RSI e sua inclinação, estocástico, ADX e direção de +DI/-DI.
3. **Regime de volatilidade** — ATR relativo à própria mediana; extremos de baixa ou alta volatilidade são evitados.
4. **Setups auditáveis** — pullback validado na EMA 21/50, rompimento de estrutura BOS, mudança de tendência CHOCH, rompimento com reteste, rejeição em suporte/resistência, varredura de liquidez, engolfo e retração de Fibonacci.
5. **Qualidade da entrada** — rejeição de preço excessivamente distante da EMA 21, VWAP, amplitude da vela e espaço até a zona contrária.
6. **Liquidez** — volume relativo e impulso de volume para criptomoedas; sessões de Londres e Nova York como contexto para Forex.
7. **Confluência e sensibilidade** — os perfis rápido, equilibrado e conservador exigem quantidades progressivas de confirmações técnicas.
8. **Payout e equilíbrio** — o ponto de equilíbrio `1 / (1 + payout)` qualifica resultados observados; a saída bruta do classificador não é apresentada como probabilidade calibrada nem como expectativa financeira.
9. **Score do modelo** — regras e modelo são combinados. Em Price Action e Confirmação, divergência isolada reduz o score e gera aviso; no Quantitativo, modelo treinado é obrigatório e piso/vantagem podem vetar.
10. **Regime estrutural** — tendência, transição, lateralização, compressão e exaustão recebem tratamentos diferentes; o mesmo indicador não representa várias confirmações independentes.
11. **Divergências confirmadas** — divergência regular antecipa perda de força; divergência oculta favorece continuação, sempre a partir de pivôs já conhecidos.
12. **Contexto do timeframe** — deslocamento mínimo, espaço até a zona contrária, janela do pullback e frequência de atualização são ajustados para 1m, 3m, 5m, 15m, 30m, 1h e 4h.
13. **Padrões de candles** — padrões de uma, duas e três velas são normalizados por range/ATR, usados em qualquer timeframe e só entram como confirmação depois do fechamento.
14. **Janela operacional** — a análise ao vivo exige exatamente 200 candles analíticos fechados; quando existe vela aberta, um 201º registro preserva essa base. Treino/backtest mantêm histórico separado e maior.
15. **Níveis da operação** — stop técnico e alvo combinam ATR, expiração, pivôs e zona oposta. Espaço curto é avisado; os níveis não representam ordens executadas pela plataforma.
16. **Reversão de curto horizonte** — a última vela concluída é confrontada com microtendência, MACD/RSI, pavio contrário, EMA 9, divergência e agressão real. Duas evidências independentes já suspendem uma entrada com vencimento curto.
17. **Validade temporal** — o sinal perde validade se a nova cotação inverter materialmente, cruzar a invalidação técnica ou chegar realmente tarde ao vencimento. No primeiro tick da vela nova, os últimos segundos ainda exibidos do ciclo anterior podem ser projetados somente para um sinal recém-confirmado pela vela fechada.
18. **Direção real do pullback** — EMAs 21/50 e estrutura definem a tendência principal; a correção temporária tem direção oposta e só libera entrada após retomada fechada. Cruzamento isolado da EMA 9 não transforma pullback em reversão.
19. **Timeframe superior real** — `1m→5m`, `3m/5m→15m`, `15m→1h` e `30m/1h→4h`. A leitura exige 200 candles fechados, cruza EMA 21/50, +DI/-DI, ADX e estrutura e bloqueia uma entrada que esteja contra uma tendência superior confirmada.

## Pullback, correção e mudança de tendência

- Em tendência de alta, um deslocamento vendedor pode ser somente a correção. A entrada coerente é **COMPRA após retomada**; a correção por si só não autoriza VENDA.
- Em tendência de baixa, um deslocamento comprador pode ser somente a correção. A entrada coerente é **VENDA após retomada**; a correção por si só não autoriza COMPRA.
- A retomada exige corpo na direção principal, posição de fechamento adequada, recuperação mínima normalizada por ATR, ausência de rejeição contrária e estabilização do momentum.
- A fase da correção é auditável: direção principal, direção temporária, número de candles contrários, profundidade por ATR e confirmação ou invalidação.
- Um CHOCH concluído ou a perda relevante da EMA 50 descaracteriza a hipótese de correção saudável e permite investigar uma mudança estrutural real.
- O modo rápido continua mais ágil, mas não ignora inversão evidente entre a direção do pullback e a direção da tendência.

## Stop técnico, alvo e suporte/resistência

- Compra: a invalidação fica abaixo do suporte/pivô confirmado ou, quando a estrutura está distante, usa proteção por ATR; o alvo fica antes da resistência relevante ou na projeção ATR.
- Venda: a mesma regra é aplicada de forma espelhada acima da resistência/pivô e antes do suporte relevante.
- A projeção cresce de forma limitada com a quantidade de candles contida na expiração, evitando usar o mesmo deslocamento em 1m e 4h.
- `technical_room_ratio` mede somente o espaço técnico entre a entrada e as referências do gráfico; não é payout, probabilidade nem relação financeira garantida.
- O gráfico escolhe até dois níveis de cada lado: o mais próximo e o mais forte/recente dentro de uma distância útil. A análise estrutural mantém as demais zonas internamente.
- Em contratos de expiração fixa, o stop não encerra a operação. Ele mostra onde a leitura deixou de fazer sentido e serve para cancelar uma entrada ainda não realizada ou avaliar o sinal.

## Biblioteca de padrões de candles

- Uma vela: doji, spinning top, martelo/pin bar, estrela cadente e marubozu.
- Duas velas: engolfo comprador/vendedor, linha de perfuração, nuvem negra, harami, inside bar, outside bar e tweezers.
- Três velas: estrela da manhã, estrela da tarde, três soldados brancos e três corvos negros.
- Padrão direcional soma no máximo uma confluência de price action; nunca substitui tendência, momentum, estrutura ou volume válido.
- Padrão contrário forte cancela a confirmação; doji/indecisão exige novo rompimento e fechamento; sequência esticada com perda de corpo/pavio contrário é marcada como exaustão.
- Em M1/M3, um pullback precisa de retomada, momentum, rejeição/estrutura e fechamento aprovado pela biblioteca. Um pavio momentâneo não é tratado como retomada confirmada.
- Pullback em formação não soma confluência positiva. Em M1/M3 ele nunca confirma entrada; no modo Confirmação, a retomada validada é obrigatória também nos demais timeframes.
- Durante WebSocket, a biblioteca pode informar `EM FORMAÇÃO`; esses dados não são gravados como sinal confirmado.

## Separação por mercado

### Criptomoedas

- Volume real, volume relativo e taker buy da Binance são usados quando a Binance é a fonte.
- Taker buy ausente ou inválido permanece neutro; Coinbase/Kraken não são apresentados como se informassem 100% de agressão vendedora.
- VWAP/OBV só participam com volume válido; fontes alternativas sem esse dado não o inventam.
- EMAs 9/21/50, RSI, MACD, ADX, ATR, BOS/CHOCH, pullback, rompimento/reteste, liquidez, divergência, exaustão e S/R têm regras simétricas para compra/venda.
- Timeframe superior usa 200 barras já concluídas obtidas diretamente da fonte pública; o reagrupamento local permanece apenas como evidência interna secundária.

### Forex

- Forex não recebe peso de volume centralizado ou VWAP fictício.
- Tóquio, Londres e Nova York são calculadas em `Asia/Tokyo`, `Europe/London` e `America/New_York`, respeitando horário de verão.
- ATR é comparado ao regime recente do próprio par. Eventos econômicos são filtrados pelas duas moedas do par.
- Spread só aparece quando bid/ask reais existem na resposta da fonte; cotações atrasadas bloqueiam confirmação M1.
- A referência diária Frankfurter não é transformada em candle de um minuto.

## Calibração por perfil

| Perfil | Objetivo | Score | Confluências | Momentum | ADX |
|---|---|---:|---:|---:|---:|
| CONSERVADOR | Alta confirmação e menor frequência. | 86 | 5 | 3 | 20 |
| EQUILIBRADO | Compromisso entre confirmação e frequência. | 73 | 4 | 2 | 15 |
| RÁPIDO | Direção ágil com leitura antecipada. | 57 | 2 | 1 | 10 |

Os perfis também possuem faixas próprias de volatilidade, distância máxima da EMA 21, peso da IA, vantagem sobre a direção oposta e margem acima do ponto de equilíbrio do payout. O perfil rápido pode anunciar uma leitura durante a vela atual; essa leitura é apresentada honestamente como **em formação**, e somente o fechamento da vela produz um sinal confirmado.

Um sinal recém-confirmado permanece visível por uma janela máxima de 8 a 12 segundos, conforme timeframe, em todos os modos e perfis. A preservação termina imediatamente se o preço contrariar a entrada em aproximadamente 0,18 ATR ou se o stop técnico for cruzado. Uma leitura comum nos segundos finais continua bloqueada; a única projeção para o ciclo seguinte ocorre no início da nova vela, quando o sinal acabou de ser confirmado pela vela anterior já fechada. Candle aberto continua sem poder confirmar uma nova entrada.

## Matriz de decisão

| Modo | Papel da IA | Estrutura e candles | Confirmações independentes |
|---|---|---|---|
| PRICE ACTION | Consultiva; reduz o score, sem veto isolado. | Elemento principal; padrão aberto é somente formação. | A pontuação e o perfil controlam a cobertura. |
| CONFIRMAÇÃO | Consultiva; concordância aumenta o score. | Padrões contrários e contexto recebem severidade progressiva. | Rápido 1, equilibrado 2, conservador 3 categorias. |
| QUANTITATIVO | Obrigatória; piso e vantagem podem vetar. | Filtros críticos continuam protegendo a entrada. | Rápido/equilibrado 1, conservador 2 categorias. |

Em todos os modos, fonte atrasada, candle ainda aberto como confirmação, estrutura contrária sem CHOCH/regime recente confirmado, retração profunda, conflito crítico de candle e tendência contrária no timeframe superior real continuam sendo bloqueios. Divergência, compressão, pullback em observação e proximidade moderada de S/R podem ser avisos ou vetos conforme a matriz, evitando acumular filtros secundários indiscriminadamente.

Na versão 1.2.5, a primeira cotação do novo período encerra a vela incremental anterior. Durante a janela curta de entrada, essa vela fechada governa a decisão e a vela corrente permanece apenas em formação. A projeção do contador da plataforma exige um sinal novo, direcional e confirmado por candle fechado; ela não libera sinais antigos ou entradas realmente tardias.

Desde a versão 1.2.4, uma leitura contra o último par de pivôs só antecipa a mudança quando o regime recente já está alinhado, não está em transição ou exaustão, possui eficiência mínima de 0,60 e pelo menos três votos de momentum. Além disso, ela não pode representar a correção temporária de um pullback preservado, apresentar retomada incompleta nem acumular sinais independentes de reversão iminente.

A versão 1.2.1 usa como referência o build oficial 0.9.0 do commit `a16d551d`. Nos perfis marcados como contextuais, um doji fechado só deixa de ser veto isolado quando o regime concorda e a estrutura não contradiz a direção, a eficiência mínima e o momentum são suficientes, o timeframe superior não está contrário e não existe transição ou exaustão. Price Action rápido/equilibrado, Confirmação rápida e Quantitativo rápido usam essa regra; o Quantitativo também exige apoio do modelo. Os demais cruzamentos permanecem rígidos.

Notícias e eventos permanecem informativos quando o bloqueio automático está desligado. Nessa situação, não devem interromper a análise nem gerar alertas de voz repetidos.

## Treinamento sem atalhos

- Features usam somente dados presentes e passados.
- A separação é temporal walk-forward.
- Entre treino e teste existe uma purga proporcional ao horizonte previsto.
- O modelo é escolhido pelo limite inferior de Wilson do acerto direcional seletivo, com requisitos de amostra e cobertura.
- Cada mercado, ativo, timeframe, horizonte, estratégia, sensibilidade, modo e versão das features possui modelo próprio.
- O schema 9 preserva os indicadores causais anteriores e adiciona direção principal, direção temporária da correção e força da retomada; a profundidade passa a respeitar as EMAs 21/50. Modelos antigos precisam ser treinados novamente.
- A calibração real também é contextual e exige pelo menos 30 operações direcionais; uma amostra menor é mostrada como informativa, nunca como desempenho comprovado.
- O backtest apresenta intervalo de confiança de Wilson, ponto de equilíbrio e expectativa compatível com o payout escolhido.

## Base metodológica

- Trend following/time-series momentum: https://doi.org/10.1016/j.jfineco.2011.11.003
- Volatility-managed portfolios: https://doi.org/10.1111/jofi.12513
- Deflated Sharpe Ratio: https://doi.org/10.2139/ssrn.2460551
- Probability of Backtest Overfitting: https://scholarworks.wmich.edu/math_pubs/42/

Essas pesquisas orientam princípios de tendência, controle de regime e validação. Elas não demonstram que os parâmetros específicos deste aplicativo terão desempenho futuro positivo.

## Como avaliar

1. Comece pelo protocolo **EQUILIBRADO + CONFIRMAÇÃO + 5m/5m** e não compare configurações antes de acumular pelo menos 100 sinais concluídos.
2. Treine separadamente o ativo/timeframe/horizonte.
3. Execute o backtest fora da amostra.
4. Desconfie de amostra pequena, cobertura mínima ou resultado concentrado em um horário.
5. Use o histórico real do próprio contexto; não misture BTC, altcoins e Forex.
6. Escolha exatamente o payout exibido pela sua plataforma para aquele ativo.
7. Considere custos, spread, slippage e diferenças entre o feed público e a cotação da sua corretora antes de operar manualmente.
8. Quando conectada, a VEX pode atualizar apenas a vela em formação com o preço efetivamente visível; o histórico completo continua vindo das fontes públicas e não deve ser confundido com um feed oficial privado da corretora.
9. VEX e BullEx nunca confirmam o fechamento: preço visual apenas atualiza a vela corrente. O encerramento confirmado continua vindo do feed de mercado.
10. O gráfico identifica resultado calculado pelo preço público como `PÚB`; use `OBS`/registro manual quando quiser medir o resultado efetivamente visto na plataforma. O saldo de avaliação nunca é apresentado como saldo da conta.
