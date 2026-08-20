# Release notes

## 0.3.0 — 20/08/2026

Atualização focada em fluidez, qualidade dos sinais e cobertura de mercados.

### Desempenho

- Cálculo de features históricas vetorizado: benchmark local de 180 candles caiu de aproximadamente 3,66 s para 0,03 s.
- A cada tick, somente a última vela e a linha de preço são redesenhadas; grid, histórico e overlays permanecem intactos.
- Análise pesada da Binance ocorre no fechamento da vela ou a cada 30 segundos, sem interromper o preço visual.

### Qualidade e backtest

- Limiares mais seletivos, diferença mínima entre compra/venda e confirmação de tendência, momentum e ADX.
- Backtest agora contabiliza `WIN + LOSS + DRAW = operações` e calcula acerto direcional sem tratar DRAW como LOSS.
- Contextos com qualidade fraca ou amostra insuficiente são bloqueados após o backtest, em vez de continuar emitindo sinal.
- Modelos passam a ser salvos separadamente por ativo, timeframe, horizonte e versão das features.

### Mercados

- 30 criptomoedas iniciais e carregamento de até 100 pares USDT líquidos disponíveis na Binance.
- 28 pares Forex visíveis mesmo antes da consulta de candles.
- Cache da Twelve Data, mensagens específicas de chave/créditos/par e atualização a cada 125 segundos para respeitar o plano gratuito.

## 0.2.0 — 20/08/2026

Atualização de interface, desempenho e experiência Forex.

### Melhorias

- Novo dashboard dark premium com hierarquia visual, sinal em card, barra de score e painéis laterais roláveis.
- Gráfico ao vivo separado dos cálculos pesados: preço visual atualizado em cerca de 120 ms e análise quantitativa a cada 10 segundos ou no fechamento da vela.
- Crosshair otimizado sem redesenhar o gráfico inteiro a cada movimento do mouse.
- Troca automática de ativo/timeframe com cancelamento do feed anterior e proteção contra resultados atrasados.
- Cache curto de snapshots e notícias para reduzir espera ao alternar ativos.
- Forex guiado pela chave Twelve Data, com atualização periódica a cada 15 segundos e nova descrição das duas APIs.
- Alertas de voz sem repetição a cada atualização.
- Monitor de saúde sem tarefas duplicadas em segundo plano.

### Correções

- Eliminados WebSockets antigos que podiam permanecer ativos após trocar o ativo.
- Resultados de tarefas anteriores não substituem mais o ativo selecionado atualmente.
- Painel direito agora possui rolagem e não corta confluências em telas menores.

## 0.1.0 — 20/08/2026

Primeira versão funcional do PRIME AI TRADER.

### Implementado

- Dashboard desktop dark responsivo e gráfico de candles próprio.
- Binance Spot REST/WebSocket e Forex por Twelve Data.
- Quinze cards quantitativos com valores derivados dos candles.
- Price Action, zonas de S/R e Fibonacci automático.
- Pipeline de IA local com comparação de quatro modelos e walk-forward.
- Sinais COMPRA/VENDA/AGUARDAR, pré-sinal, confirmação e bloqueios de risco.
- Notícias, calendário econômico, radar, backtest, voz, SQLite, desempenho e logs.
- Build PyInstaller e instalador Inno Setup x64.
- Suíte automatizada de regressão.

### Decisões de segurança

- Nenhuma ordem é executada.
- Nenhuma API Key está embutida.
- Nenhuma taxa de acerto é simulada.
- AGUARDAR é a saída padrão sem confluência suficiente.

### Próximas versões

- Streaming Forex por provedor compatível.
- Suporte opcional a OANDA e Alpha Vantage.
- Resultado por stop/target configurável e métricas de retorno/risco mais completas.
