# Relatório de validação — PRIME AI TRADER 0.4.0

Data: 20/08/2026

## Auditoria concluída

| Área | Verificação |
|---|---|
| Interface | Todos os botões visíveis possuem comando; tarefas pesadas ficam fora da thread da UI. |
| IA | Contexto completo, persistência por ativo e seleção por desempenho seletivo fora da amostra. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | Confluência de tendência, momentum, volatilidade, liquidez, extensão e espaço para S/R. |
| Backtest | Mesmos limites de probabilidade do sinal ao vivo; WIN/LOSS/DRAW coerentes. |
| Estatísticas | DRAW excluído do acerto direcional; calibração separada por contexto. |
| Cripto | Binance pública, lista líquida, WebSocket e reconexão. |
| Forex | Twelve Data, 28 pares, cache, mensagens de cota e normalização de moedas de eventos. |
| Notícias | GDELT, cache, cooldown e correspondência de termos por palavra completa. |
| Gráfico | Redesenho parcial da última vela e crosshair sem redesenho integral. |

## Testes executados

- Comando: `python -m unittest discover -s tests -v`
- Resultado local: **49 testes aprovados, 0 falhas**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, estrutura, Fibonacci, schema/invariância temporal das features, labels, purga dos folds, treino, probabilidade, contexto do modelo, backtest, banco, calibração, risco, providers, cache, WebSocket, gráfico e comandos da interface.

## Interpretação correta

O motor foi tornado mais seletivo para tentar reduzir sinais frágeis. Isso pode melhorar a qualidade da amostra, mas não cria uma taxa de acerto garantida. A evidência válida é sempre o backtest fora da amostra do contexto atual e, depois, o histórico real acumulado sem misturar ativos.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.
