# Relatório de validação — PRIME AI TRADER 1.0.0

Data: 22/08/2026

## Auditoria concluída

| Área | Verificação |
|---|---|
| Interface | Layout aprovado e cartão de voz compacto preservados; seletor VEX/BULLEX e registro manual foram adicionados sem remover ações. |
| Smoke test Windows | A interface completa é instanciada em Windows; plataformas, áudio, indicadores, controles e timeframes são conferidos. |
| VEX Invest | Navegador dedicado, perfil separado, endpoint loopback e leitura somente de ativo, payout, preço, expiração e tempo visíveis. |
| BullEx | Opt-in, perfil separado, hosts permitidos, alerta CVM obrigatório e mesma leitura visual sem execução. |
| Privacidade | Sem leitura de senha, cookies, armazenamento local, saldo, campos digitados ou execução de ordens. |
| Alinhamento | Divergência de ativo, mercado, preço público e ativos OTC recebe motivo explícito antes de qualquer sinal. |
| Preço VEX | Somente o preço realmente visível atualiza a vela corrente; histórico público, volume real e fechamento confirmado são preservados. |
| Cronômetro | Usa relógio real visível na VEX ou criação original do sinal; atualizar gráfico/notícias não reinicia o vencimento. |
| IA | Contexto completo por mercado/ativo/timeframe/expiração/estratégia/sensibilidade/modo/schema e seleção fora da amostra. |
| Schema profissional | Features causais estruturais e específicas por mercado; schema 6 exige novo treinamento. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | BOS, CHOCH, pullback comprador/vendedor, divergências regulares/ocultas, rompimento/reteste, liquidez/rejeição, engolfo e confirmação independente. |
| Regime | Alta, baixa, transição, lateralização, compressão e exaustão usam tratamento distinto; correção profunda e preço sem espaço são explicitamente recusados. |
| Timeframes | Políticas próprias para 1m, 3m, 5m, 15m, 30m, 1h e 4h em todos os perfis e modos; atualização incremental calibrada. |
| Perfis | Conservador 86/5/ADX20, equilibrado 73/4/ADX15, rápido 57/2/ADX10; momentum, IA e volatilidade independentes. |
| Áudio | Avisos não bloqueantes ficam silenciosos; leitura rápida em formação e sinais confirmados têm prioridade; bloqueios reais têm cooldown de 300 segundos. |
| Backtest | Walk-forward, filtros de extensão/eficiência/compressão/reversão, payout configurável, ponto de equilíbrio, expectativa e intervalo de Wilson. |
| Estatísticas | WIN/LOSS/DRAW, payout, entrada, P&L, profit factor financeiro, equilíbrio, expectativa, Wilson e origem manual/inferida. |
| Cripto | Binance pública com espelhos oficiais; fallback Coinbase/Kraken; ativos da plataforma incluindo XLM. |
| Forex | Sem volume centralizado fictício; sessões IANA/DST, ATR por par, cotação/atraso/spread quando disponíveis e referência diária separada. |
| Notícias | GDELT, Google Notícias, Cointelegraph, CoinDesk, FXStreet e ForexLive; painel visível e atualização automática. |
| Calendário | Eventos econômicos públicos com cache de uma hora e Finnhub opcional. |
| Gráfico | Redesenho parcial da última vela, crosshair sem redesenho integral, precisão cambial e atalhos de timeframe. |
| Últimos sinais | Leitura real do banco em thread dedicada; sem operações inventadas e sem bloquear o Tkinter. |
| SQLite / Windows | Conexões fechadas após cada operação, arquivos liberados e diretório temporário de testes corretamente isolado. |
| Build seguro | Pillow, testes, compileall, import completo do Tkinter e verificação do código de saída antes do Inno Setup. |
| Limpeza | Cache/modelos antigos removíveis pelo app, instalador e arquivo externo, sem excluir chaves/configurações/banco. |

## Testes executados

- Comando: `python -m unittest discover -s tests -v`
- Resultado local: **251 testes aprovados, 0 falhas; 1 smoke test reservado para Windows**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, BOS/CHOCH, falsos pullbacks, exaustão, M1, timeframe superior, schema/invariância causal, purga, modelos separados, backtest, payout, exemplo financeiro 7/3, migração SQLite, resultado manual/inferido, VEX, BullEx, loopback, atraso, sessões Forex, providers, interface e instalador.

Em 80 cenários sintéticos compartilhados, o perfil rápido produziu 74 leituras, o equilibrado 66 e o conservador 44. Trata-se de uma verificação de frequência relativa, não de uma promessa de lucro ou acerto.

## Interpretação correta

O motor foi tornado mais seletivo para tentar reduzir sinais frágeis. Isso pode melhorar a qualidade da amostra, mas não cria uma taxa de acerto garantida. A evidência válida é sempre o backtest fora da amostra do contexto atual e, depois, o histórico real acumulado sem misturar ativos.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.

Identificador do candidato validado: `1.0.0`.

O candidato Windows deve repetir obrigatoriamente os 252 testes (251 locais + smoke visual Windows), validar o Tkinter completo e somente então gerar os dois executáveis com Inno Setup.
