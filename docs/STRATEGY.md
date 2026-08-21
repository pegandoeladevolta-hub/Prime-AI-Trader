# Estratégia e validação

## Objetivo

O motor tenta selecionar operações com evidência convergente e prefere `AGUARDAR` quando o contexto é ambíguo. Nenhuma técnica produz alta acertividade de forma permanente em todos os regimes.

## Filtros usados

1. **Tendência em mais de uma escala** — alinhamento das EMAs 9/21/50, inclinação da EMA 50, estrutura HH/HL ou LH/LL e timeframe superior calculado somente com barras concluídas.
2. **Momentum** — MACD e sua aceleração, RSI e sua inclinação, estocástico, ADX e direção de +DI/-DI.
3. **Regime de volatilidade** — ATR relativo à própria mediana; extremos de baixa ou alta volatilidade são evitados.
4. **Setups auditáveis** — pullback na EMA 21, rompimento com confirmação, rompimento com reteste, rejeição em suporte/resistência, varredura de liquidez, engolfo e retração de Fibonacci.
5. **Qualidade da entrada** — rejeição de preço excessivamente distante da EMA 21, VWAP, amplitude da vela e espaço até a zona contrária.
6. **Liquidez** — volume relativo e impulso de volume para criptomoedas; sessões de Londres e Nova York como contexto para Forex.
7. **Confluência e sensibilidade** — os perfis rápido, equilibrado e conservador exigem quantidades progressivas de confirmações técnicas.
8. **Probabilidade e payout** — a decisão considera o ponto de equilíbrio `1 / (1 + payout)`, a probabilidade estimada e a expectativa matemática; payout de 80% exige mais de 55,56% de acerto para expectativa positiva.
9. **Confiança do modelo** — regras e modelo são combinados sem apagar uma confluência técnica legítima quando o histórico ainda está em formação.

## Treinamento sem atalhos

- Features usam somente dados presentes e passados.
- A separação é temporal walk-forward.
- Entre treino e teste existe uma purga proporcional ao horizonte previsto.
- O modelo é escolhido pelo limite inferior de Wilson do acerto direcional seletivo, com requisitos de amostra e cobertura.
- Cada mercado, ativo, timeframe, horizonte e versão das features possui modelo próprio.
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
