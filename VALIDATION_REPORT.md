# Relatório de validação — PRIME AI TRADER 0.6.0

Data: 21/08/2026

## Auditoria concluída

| Área | Verificação |
|---|---|
| Interface | Todos os botões visíveis possuem comando/handler válido; workers usam fila segura e não chamam Tkinter diretamente. |
| IA | Contexto completo, persistência por ativo e seleção por desempenho seletivo fora da amostra. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | Tendência, pullback, rompimento/reteste, liquidez/rejeição, engolfo, timeframe superior e motivo explícito para aguardar. |
| Perfis | Conservador 86/5/ADX20, equilibrado 73/4/ADX15, rápido 57/2/ADX10; momentum, IA e volatilidade independentes. |
| Áudio | Avisos não bloqueantes ficam silenciosos; leitura rápida em formação e sinais confirmados têm prioridade; bloqueios reais têm cooldown de 300 segundos. |
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
- Resultado local: **103 testes aprovados, 0 falhas**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, estrutura, Fibonacci, schema/invariância temporal das features, labels, purga dos folds, treino, probabilidade, contexto do modelo, backtest, banco, calibração, perfis independentes, leitura antecipada, prioridade de voz, cooldown, risco, providers, cache, WebSocket, gráfico e comandos da interface.

Em 80 cenários sintéticos compartilhados, o perfil rápido produziu 74 leituras, o equilibrado 66 e o conservador 44. Trata-se de uma verificação de frequência relativa, não de uma promessa de lucro ou acerto.

## Interpretação correta

O motor foi tornado mais seletivo para tentar reduzir sinais frágeis. Isso pode melhorar a qualidade da amostra, mas não cria uma taxa de acerto garantida. A evidência válida é sempre o backtest fora da amostra do contexto atual e, depois, o histórico real acumulado sem misturar ativos.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.

Identificador do candidato validado: `0.6.0`.

O candidato Windows deve repetir obrigatoriamente os 103 testes antes da publicação.
