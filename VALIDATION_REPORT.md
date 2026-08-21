# Relatório de validação — PRIME AI TRADER 0.5.0

Data: 20/08/2026

## Auditoria concluída

| Área | Verificação |
|---|---|
| Interface | Todos os botões visíveis possuem comando/handler válido; workers usam fila segura e não chamam Tkinter diretamente. |
| IA | Contexto completo, persistência por ativo e seleção por desempenho seletivo fora da amostra. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | Tendência, pullback, rompimento/reteste, liquidez/rejeição, engolfo, timeframe superior e motivo explícito para aguardar. |
| Backtest | Walk-forward, payout configurável, ponto de equilíbrio, expectativa e intervalo de confiança de Wilson. |
| Estatísticas | DRAW excluído do acerto direcional; sinais WebSocket registrados e liquidados no vencimento. |
| Cripto | Binance pública com espelhos oficiais; fallback Coinbase/Kraken; ativos da plataforma incluindo XLM. |
| Forex | Fonte pública sem chave, Twelve Data/Alpha Vantage opcionais, referência Frankfurter diária e 28 pares. |
| Notícias | GDELT, Google Notícias, Cointelegraph, CoinDesk, FXStreet e ForexLive; painel visível e atualização automática. |
| Calendário | Eventos econômicos públicos com cache de uma hora e Finnhub opcional. |
| Gráfico | Redesenho parcial da última vela e crosshair sem redesenho integral. |
| Limpeza | Cache/modelos antigos removíveis pelo app, instalador e arquivo externo, sem excluir chaves/configurações/banco. |

## Testes executados

- Comando: `python -m unittest discover -s tests -v`
- Resultado local: **85 testes aprovados, 0 falhas**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, estrutura, Fibonacci, schema/invariância temporal das features, labels, purga dos folds, treino, probabilidade, contexto do modelo, backtest, banco, calibração, risco, providers, cache, WebSocket, gráfico e comandos da interface.

## Interpretação correta

O motor foi tornado mais seletivo para tentar reduzir sinais frágeis. Isso pode melhorar a qualidade da amostra, mas não cria uma taxa de acerto garantida. A evidência válida é sempre o backtest fora da amostra do contexto atual e, depois, o histórico real acumulado sem misturar ativos.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.

Identificador do candidato validado: `0.5.0`.

O candidato Windows deve repetir obrigatoriamente os 85 testes antes da publicação.
