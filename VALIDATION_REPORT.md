# Relatório de validação — PRIME AI TRADER 0.2.0

Data: 20/08/2026

## Fases concluídas e verificadas

| Fase | Implementação verificada |
|---|---|
| 1. Arquitetura desktop | Ponto de entrada, controlador, interface Tkinter e módulos separados compilam sem erro. |
| 2. Interface responsiva | Layout premium em três áreas, gráfico central priorizado, painéis laterais roláveis e suporte a 1366×768 ou superior. |
| 3. Binance | REST, paginação histórica de até 5.000 candles, símbolos USDT, book ticker, WebSocket e reconexão testada. |
| 4. Gráfico | Candles, volume, zoom, arraste, crosshair leve, OHLC, preço ao vivo, overlays e redesenho agrupado. |
| 5. Indicadores | Fórmulas automatizadas testadas para todos os indicadores exigidos. |
| 6. Price Action/Fibonacci | Pivôs, zonas, estrutura, rompimentos, retestes e níveis automáticos testados. |
| 7. IA | Quatro modelos CPU, comparação walk-forward, persistência e vínculo ao contexto de treino. |
| 8. Backtest | Previsões fora da amostra, matriz, cobertura, sequências e desempenho por horário. |
| 9. Notícias | GDELT real, classificação local, cache, cooldown de falha e bloqueio de risco. |
| 10. Forex | Provider Twelve Data ativo, 10 pares iniciais, polling a cada 15 segundos, chave protegida e calendário Finnhub opcional. |
| 11. Radar | Score auditável e botão para mudar/analisar ativo. |
| 12. Voz | Windows Speech pt-BR, volume, categorias e antirrepetição. |
| 13. Histórico/estatísticas | SQLite, resultados WIN/LOSS/DRAW observados, calibração e profit factor quando calculável. |
| 14. Instalador | Spec PyInstaller, metadados de versão e script Inno Setup com atalhos/desinstalador. |

## Testes executados

- Comando: `python -m unittest discover -s tests -v`
- Resultado: **34 testes aprovados, 0 falhas**.
- Tempo da última execução: 55,836 segundos.

Cobertura funcional dos testes:

- EMA, RSI, MACD, Bollinger, Stochastic, ADX, ATR, VWAP, OBV, CCI e Williams %R;
- Fibonacci, pivôs e zonas de suporte/resistência;
- schema de features e teste de invariância contra inclusão de candles futuros;
- labels por número de candles e por horizonte exato em minutos;
- folds temporais sem sobreposição, treino dos quatro candidatos e probabilidades;
- backtest apenas fora da amostra;
- bloqueio de risco e impossibilidade de confirmar vela aberta;
- SQLite, calibração e estatísticas;
- parsing Binance e Twelve Data, ausência de chave Forex e contrato de ações dos botões;
- cache e cooldown de notícias para evitar travamento da interface;
- crosshair sem redesenhar todo o gráfico a cada movimento do mouse;
- troca de ativo/timeframe e reconexão WebSocket após falha transitória.

## Limite da validação neste ambiente

O código e os testes unitários foram executados primeiro em ambiente Linux. O executável `.exe` e o instalador Inno Setup são compilados em um executor Windows, que repete a bateria de testes antes de empacotar a versão entregue.

Em Windows, `build_windows.ps1` executa novamente todos os testes antes de criar `PrimeAITrader.exe` e `PrimeAITrader-Setup-x64.exe`.
