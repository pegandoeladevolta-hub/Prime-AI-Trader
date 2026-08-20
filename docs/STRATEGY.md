# Estratégia e validação

## Objetivo

O motor tenta selecionar operações com evidência convergente e prefere `AGUARDAR` quando o contexto é ambíguo. Nenhuma técnica produz alta acertividade de forma permanente em todos os regimes.

## Filtros usados

1. **Tendência em mais de uma escala** — alinhamento das EMAs, inclinação da EMA 50, estrutura HH/HL ou LH/LL e retorno de 12 candles.
2. **Momentum** — MACD, RSI sem faixas sobrepostas, ADX e direção de +DI/-DI.
3. **Regime de volatilidade** — ATR relativo à própria mediana; extremos de baixa ou alta volatilidade são evitados.
4. **Qualidade da entrada** — rejeição de preço mais de 2,2 ATR distante da EMA 21 e de entrada sem 0,7 ATR de espaço até a zona contrária.
5. **Liquidez** — volume relativo mínimo para criptomoedas.
6. **Confluência** — quantidade mínima de confirmações e diferença mínima entre compra e venda.
7. **Confiança do modelo** — probabilidade mínima e vantagem mínima sobre a direção oposta, ajustadas pela sensibilidade.

## Treinamento sem atalhos

- Features usam somente dados presentes e passados.
- A separação é temporal walk-forward.
- Entre treino e teste existe uma purga proporcional ao horizonte previsto.
- O modelo é escolhido pelo limite inferior de Wilson do acerto direcional seletivo, com requisitos de amostra e cobertura.
- Cada mercado, ativo, timeframe, horizonte e versão das features possui modelo próprio.
- A calibração real também é contextual e exige pelo menos 30 operações direcionais.

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
5. Considere custos, spread e slippage antes de operar manualmente.
