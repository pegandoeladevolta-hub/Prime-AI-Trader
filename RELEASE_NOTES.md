# Release notes

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
- Atualização incremental do vetor de features em vez de recomputação parcial.
