# Release notes

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

