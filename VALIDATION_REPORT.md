# Relatório de validação — PRIME AI TRADER 0.9.0

Data: 21/08/2026

## Auditoria concluída

| Área | Verificação |
|---|---|
| Interface | Interface aprovada da versão 0.7.0 preservada, incluindo cartão de voz compacto da 0.7.2 e botão opcional CONECTAR VEX INVEST. |
| Smoke test Windows | A interface completa é instanciada em Windows; conexão VEX, alto-falante compacto, onda de áudio, indicadores, controles avançados e timeframes são conferidos. |
| VEX Invest | Navegador dedicado, perfil separado, endpoint loopback e leitura somente de ativo, payout, preço, expiração e tempo visíveis. |
| Privacidade | Sem leitura de senha, cookies, armazenamento local, saldo, campos digitados ou execução de ordens. |
| Alinhamento | Divergência de ativo, mercado, preço público e ativos OTC recebe motivo explícito antes de qualquer sinal. |
| Preço VEX | Somente o preço realmente visível atualiza a vela corrente; histórico público, volume real e fechamento confirmado são preservados. |
| Cronômetro | Usa relógio real visível na VEX ou criação original do sinal; atualizar gráfico/notícias não reinicia o vencimento. |
| IA | Contexto completo, persistência por ativo e seleção por desempenho seletivo fora da amostra. |
| Schema profissional | Doze features causais de pullback, estrutura, impulso, divergência, compressão, liquidez e reversão; schema 5 exige novo treinamento do contexto. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | BOS, CHOCH, pullback comprador/vendedor, divergências regulares/ocultas, rompimento/reteste, liquidez/rejeição, engolfo e confirmação independente. |
| Regime | Alta, baixa, transição, lateralização, compressão e exaustão usam tratamento distinto; correção profunda e preço sem espaço são explicitamente recusados. |
| Timeframes | Políticas próprias para 1m, 3m, 5m, 15m, 30m, 1h e 4h em todos os perfis e modos; atualização incremental calibrada. |
| Perfis | Conservador 86/5/ADX20, equilibrado 73/4/ADX15, rápido 57/2/ADX10; momentum, IA e volatilidade independentes. |
| Áudio | Avisos não bloqueantes ficam silenciosos; leitura rápida em formação e sinais confirmados têm prioridade; bloqueios reais têm cooldown de 300 segundos. |
| Backtest | Walk-forward, filtros de extensão/eficiência/compressão/reversão, payout configurável, ponto de equilíbrio, expectativa e intervalo de Wilson. |
| Estatísticas | DRAW excluído do acerto direcional; sinais WebSocket registrados e liquidados no vencimento. |
| Cripto | Binance pública com espelhos oficiais; fallback Coinbase/Kraken; ativos da plataforma incluindo XLM. |
| Forex | Fonte pública sem chave, cotação incremental aproximadamente a cada dez segundos, Twelve Data/Alpha Vantage opcionais, referência Frankfurter diária e 28 pares. |
| Notícias | GDELT, Google Notícias, Cointelegraph, CoinDesk, FXStreet e ForexLive; painel visível e atualização automática. |
| Calendário | Eventos econômicos públicos com cache de uma hora e Finnhub opcional. |
| Gráfico | Redesenho parcial da última vela, crosshair sem redesenho integral, precisão cambial e atalhos de timeframe. |
| Últimos sinais | Leitura real do banco em thread dedicada; sem operações inventadas e sem bloquear o Tkinter. |
| SQLite / Windows | Conexões fechadas após cada operação, arquivos liberados e diretório temporário de testes corretamente isolado. |
| Build seguro | Pillow instalado para o ícone e verificação obrigatória do código de saída após dependências, ícone, testes e empacotamento. |
| Limpeza | Cache/modelos antigos removíveis pelo app, instalador e arquivo externo, sem excluir chaves/configurações/banco. |

## Testes executados

- Comando: `python -m unittest discover -s tests -v`
- Resultado local: **231 testes aprovados, 0 falhas; 1 smoke test reservado para Windows**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, estrutura, BOS/CHOCH, pullbacks compradores/vendedores, divergências regulares/ocultas, regimes, exaustão, todos os timeframes/perfis/modos, Fibonacci, schema/invariância temporal das features, labels, purga dos folds, treino, probabilidade, contexto do modelo, backtest, banco, calibração, prioridade de voz, risco, providers, cache, WebSocket, gráfico, cotação real visível da VEX e comandos da interface.

Em 80 cenários sintéticos compartilhados, o perfil rápido produziu 74 leituras, o equilibrado 66 e o conservador 44. Trata-se de uma verificação de frequência relativa, não de uma promessa de lucro ou acerto.

## Interpretação correta

O motor foi tornado mais seletivo para tentar reduzir sinais frágeis. Isso pode melhorar a qualidade da amostra, mas não cria uma taxa de acerto garantida. A evidência válida é sempre o backtest fora da amostra do contexto atual e, depois, o histórico real acumulado sem misturar ativos.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.

Identificador do candidato validado: `0.9.0`.

O candidato Windows deve repetir obrigatoriamente os 232 testes, incluindo 58 cenários estruturais novos, a montagem completa da interface, o cartão de voz compacto, a sincronização local segura da VEX, a remoção do import obsoleto e a liberação real das conexões SQLite, antes da publicação.
