# Release notes

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
