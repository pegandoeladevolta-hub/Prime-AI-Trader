# Estratégia e validação

## Objetivo

O motor tenta selecionar operações com evidência convergente e prefere `AGUARDAR` quando o contexto é ambíguo. Nenhuma técnica produz alta acertividade de forma permanente em todos os regimes.

## Filtros usados

1. **Tendência em mais de uma escala** — alinhamento das EMAs 9/21/50, inclinação da EMA 50, estrutura HH/HL ou LH/LL e timeframe superior calculado somente com barras concluídas.
2. **Momentum** — MACD e sua aceleração, RSI e sua inclinação, estocástico, ADX e direção de +DI/-DI.
3. **Regime de volatilidade** — ATR relativo à própria mediana; extremos de baixa ou alta volatilidade são evitados.
4. **Setups auditáveis** — pullback validado na EMA 21/50, rompimento de estrutura BOS, mudança de tendência CHOCH, rompimento com reteste, rejeição em suporte/resistência, varredura de liquidez, engolfo e retração de Fibonacci.
5. **Qualidade da entrada** — rejeição de preço excessivamente distante da EMA 21, VWAP, amplitude da vela e espaço até a zona contrária.
6. **Liquidez** — volume relativo e impulso de volume para criptomoedas; sessões de Londres e Nova York como contexto para Forex.
7. **Confluência e sensibilidade** — os perfis rápido, equilibrado e conservador exigem quantidades progressivas de confirmações técnicas.
8. **Probabilidade e payout** — a decisão considera o ponto de equilíbrio `1 / (1 + payout)`, a probabilidade estimada e a expectativa matemática; payout de 80% exige mais de 55,56% de acerto para expectativa positiva.
9. **Confiança do modelo** — regras e modelo são combinados sem apagar uma confluência técnica legítima quando o histórico ainda está em formação.
10. **Regime estrutural** — tendência, transição, lateralização, compressão e exaustão recebem tratamentos diferentes; o mesmo indicador não representa várias confirmações independentes.
11. **Divergências confirmadas** — divergência regular antecipa perda de força; divergência oculta favorece continuação, sempre a partir de pivôs já conhecidos.
12. **Contexto do timeframe** — deslocamento mínimo, espaço até a zona contrária, janela do pullback e frequência de atualização são ajustados para 1m, 3m, 5m, 15m, 30m, 1h e 4h.

## Calibração por perfil

| Perfil | Objetivo | Score | Confluências | Momentum | ADX |
|---|---|---:|---:|---:|---:|
| CONSERVADOR | Alta confirmação e menor frequência. | 86 | 5 | 3 | 20 |
| EQUILIBRADO | Compromisso entre confirmação e frequência. | 73 | 4 | 2 | 15 |
| RÁPIDO | Direção ágil com leitura antecipada. | 57 | 2 | 1 | 10 |

Os perfis também possuem faixas próprias de volatilidade, distância máxima da EMA 21, peso da IA, vantagem sobre a direção oposta e margem acima do ponto de equilíbrio do payout. O perfil rápido pode anunciar uma leitura durante a vela atual; essa leitura é apresentada honestamente como **em formação**, e somente o fechamento da vela produz um sinal confirmado.

Notícias e eventos permanecem informativos quando o bloqueio automático está desligado. Nessa situação, não devem interromper a análise nem gerar alertas de voz repetidos.

## Treinamento sem atalhos

- Features usam somente dados presentes e passados.
- A separação é temporal walk-forward.
- Entre treino e teste existe uma purga proporcional ao horizonte previsto.
- O modelo é escolhido pelo limite inferior de Wilson do acerto direcional seletivo, com requisitos de amostra e cobertura.
- Cada mercado, ativo, timeframe, horizonte e versão das features possui modelo próprio.
- O schema 5 inclui profundidade do pullback, impulso em ATR, posição estrutural, divergências, compressão, força do rompimento, varredura de liquidez e pressão de reversão; modelos antigos precisam ser treinados novamente.
- A calibração real também é contextual e exige pelo menos 30 operações direcionais; uma amostra menor é mostrada como informativa, nunca como desempenho comprovado.
- O backtest apresenta intervalo de confiança de Wilson, ponto de equilíbrio e expectativa compatível com o payout escolhido.

## Base metodológica

- Trend following/time-series momentum: https://doi.org/10.1016/j.jfineco.2011.11.003
- Volatility-managed portfolios: https://doi.org/10.1111/jofi.12513
- Deflated Sharpe Ratio: https://doi.org/10.2139/ssrn.2460551
- Probability of Backtest Overfitting: https://scholarworks.wmich.edu/math_pubs/42/

Essas pesquisas orientam princípios de tendência, controle de regime e validação. Elas não demonstram que os parâmetros específicos deste aplicativo terão desempenho futuro positivo.

## Como avaliar

1. Treine separadamente o ativo/timeframe/horizonte.
2. Execute o backtest fora da amostra.
3. Desconfie de amostra pequena, cobertura mínima ou resultado concentrado em um horário.
4. Use o histórico real do próprio contexto; não misture BTC, altcoins e Forex.
5. Escolha exatamente o payout exibido pela sua plataforma para aquele ativo.
6. Considere custos, spread, slippage e diferenças entre o feed público e a cotação da sua corretora antes de operar manualmente.
7. Quando conectada, a VEX pode atualizar apenas a vela em formação com o preço efetivamente visível; o histórico completo continua vindo das fontes públicas e não deve ser confundido com um feed oficial privado da corretora.
