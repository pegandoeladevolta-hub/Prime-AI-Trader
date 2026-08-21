# Release notes

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
