# Relatório de validação — PRIME AI TRADER 1.2.2

Data: 24/08/2026

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
| IA | Contexto completo por mercado/ativo/timeframe/expiração/estratégia/sensibilidade/modo/schema e seleção fora da amostra; saída bruta não é expectativa financeira calibrada. |
| Schema profissional | Features causais estruturais, específicas por mercado e padrões OHLC; schema 7 exige novo treinamento. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | BOS, CHOCH, pullback, divergências, rompimento/reteste, liquidez e biblioteca de padrões de uma, duas e três velas. |
| Padrões de candles | Doji, spinning top, pin bars, marubozu, engolfos, perfuração/nuvem, harami, inside/outside, tweezers, estrelas e sequências de três velas; somente candle fechado confirma. |
| Regime | Alta, baixa, transição, lateralização, compressão e exaustão usam tratamento distinto; correção profunda e preço sem espaço são explicitamente recusados. |
| Timeframes | Políticas próprias para 1m, 3m, 5m, 15m, 30m, 1h e 4h em todos os perfis e modos; atualização incremental calibrada. |
| Janela ao vivo | Mínimo de 100 e máximo de 200 candles para sinais; até 2.000 candles preservados separadamente para treino/backtest. |
| Stop/alvo | Invalidação e alvo técnicos simétricos por ATR, pivôs, timeframe, expiração e S/R; referências visuais sem execução de ordens. |
| Suporte/resistência | Até dois níveis úteis de cada lado no gráfico, selecionados por distância, força e recência; análise interna preservada. |
| Mudança de tendência | Contraestrutura exige CHOCH ou regime recente estável com eficiência ≥ 0,60 e três votos de momentum. |
| Perfis | Conservador 86/5/ADX20, equilibrado 73/4/ADX15, rápido 57/2/ADX10; os nove cruzamentos com Price Action/Confirmação/Quantitativo possuem políticas progressivas explícitas. |
| Cobertura | Matriz determinística com vinte cenários mantém cobertura não nula nos nove cruzamentos e ordem rápido ≥ equilibrado ≥ conservador. |
| Referência 0.9.0 | O SHA-256 do instalador anexado coincide com o build oficial do commit `a16d551d`; cobertura e filtros foram comparados diretamente com esse código-fonte. |
| Timing | Sinal confirmado permanece visível por 8 a 12 segundos em todos os modos/timeframes; candle aberto nunca confirma e candle fechado sempre é reprocessado. |
| Áudio | Avisos não bloqueantes ficam silenciosos; leitura rápida em formação e sinais confirmados têm prioridade; bloqueios reais têm cooldown de 300 segundos. |
| Backtest | Walk-forward, filtros de extensão/eficiência/compressão/reversão/padrões, payout, equilíbrio, expectativa e Wilson. |
| Estatísticas | WIN/LOSS/DRAW, payout, entrada, P&L, profit factor financeiro, equilíbrio, expectativa, Wilson e origem manual/inferida. |
| Cripto | Binance pública com espelhos oficiais; fallback Coinbase/Kraken; ativos da plataforma incluindo XLM. |
| Forex | Sem volume centralizado fictício; sessões IANA/DST, ATR por par, cotação/atraso/spread quando disponíveis e referência diária separada. |
| Notícias | GDELT, Google Notícias, Cointelegraph, CoinDesk, FXStreet e ForexLive; painel visível e atualização automática. |
| Calendário | Eventos econômicos públicos com cache de uma hora e Finnhub opcional. |
| Gráfico | Entrada/stop/alvo, S1/S2/R1/R2, menos pivôs, redesenho parcial da última vela, crosshair e precisão cambial. |
| Últimos sinais | Leitura real do banco em thread dedicada; sem operações inventadas e sem bloquear o Tkinter. |
| SQLite / Windows | Conexões fechadas após cada operação, arquivos liberados e diretório temporário de testes corretamente isolado. |
| Build seguro | Pillow, testes, compileall, import completo do Tkinter e verificação do código de saída antes do Inno Setup. |
| Limpeza | Cache/modelos antigos removíveis pelo app, instalador e arquivo externo, sem excluir chaves/configurações/banco. |

## Testes executados

- Comando: `python -m unittest discover -s tests -v`
- Resultado local: **284 testes aprovados, 0 falhas; 1 smoke test reservado para Windows**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, BOS/CHOCH, falsos pullbacks, exaustão, M1, janela 100–200, níveis técnicos simétricos, S/R compacto, biblioteca de candles em múltiplas escalas, padrões em formação/confirmados, schema/invariância causal, purga, modelos separados, backtest, payout, migração SQLite, VEX, BullEx, loopback, providers, interface e instalador.

Na matriz determinística atual de vinte cenários com modelo alinhado, Price Action produziu 11/9/4 leituras, Confirmação 10/3/3 e Quantitativo 10/4/3, respectivamente nos perfis rápido/equilibrado/conservador. A redução controlada vem do novo bloqueio de direção contrária sem mudança confirmada; a ordem Rápido ≥ Equilibrado ≥ Conservador e a cobertura mínima continuam testadas. Trata-se de regressão de cobertura, não de taxa de acerto, desempenho financeiro ou promessa de lucro.

## Interpretação correta

As políticas globais restauram parte da cobertura observada no 0.9.0 onde filtros secundários cumulativos causavam excesso de `AGUARDAR`. Indecisão isolada dentro de tendência alinhada pode virar aviso nos perfis compatíveis, enquanto lateralização, conflito estrutural, candle aberto, fonte atrasada, retração profunda e falta crítica de espaço continuam bloqueando. Isso não cria uma taxa de acerto garantida. A evidência válida é sempre o backtest fora da amostra do contexto atual e, depois, o histórico real acumulado sem misturar ativos.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.

Identificador do candidato validado: `1.2.2`.

O candidato Windows deve repetir obrigatoriamente os 285 testes (284 locais + smoke visual Windows), validar o Tkinter completo e somente então gerar os dois executáveis com Inno Setup.
