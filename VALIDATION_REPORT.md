# Relatório de validação — PRIME AI TRADER 1.2.3

Data: 25/08/2026

## Auditoria concluída

| Área | Verificação |
|---|---|
| Interface | Layout aprovado e cartão de voz compacto preservados; seletor VEX/BULLEX e registro manual foram adicionados sem remover ações. |
| Smoke test Windows | A interface completa é instanciada em Windows; plataformas, áudio, indicadores, controles e timeframes são conferidos. |
| VEX Invest | Navegador dedicado, perfil separado, endpoint loopback e leitura somente de ativo, payout, preço, expiração e tempo visíveis. |
| BullEx | Opt-in, perfil separado, hosts permitidos, alerta CVM obrigatório e mesma leitura visual sem execução. |
| Privacidade | Sem leitura de senha, cookies, armazenamento local, saldo, campos digitados ou execução de ordens. |
| Alinhamento | Divergência de ativo, mercado, preço público, ativos OTC e vencimento nos segundos finais recebe motivo explícito antes de qualquer sinal. |
| Preço VEX | Somente o preço realmente visível atualiza a vela corrente; histórico público, volume real e fechamento confirmado são preservados. |
| Cronômetro | Usa relógio real visível na VEX ou criação original do sinal; atualizar gráfico/notícias não reinicia o vencimento. |
| IA | Contexto completo por mercado/ativo/timeframe/expiração/estratégia/sensibilidade/modo/schema e seleção fora da amostra; saída bruta não é expectativa financeira calibrada. |
| Schema profissional | Features causais estruturais, microtendência por ATR, virada de momentum, EMA 9 e order flow validado; schema 8 exige novo treinamento. |
| Validação temporal | Walk-forward sem random split e com purga conforme o horizonte do rótulo. |
| Sinais | BOS, CHOCH, pullback realmente confirmado, divergências, rompimento/reteste, liquidez, proteção de reversão e padrões de uma, duas e três velas. |
| Pullback incompleto | Não vira confluência positiva; não confirma em M1/M3 e permanece bloqueado no modo Confirmação em todos os timeframes. |
| Reversão iminente | Fechamentos, MACD/RSI, rejeição, perda da EMA 9, divergência e agressão real são votos independentes e simétricos para compra/venda. |
| Padrões de candles | Doji, spinning top, pin bars, marubozu, engolfos, perfuração/nuvem, harami, inside/outside, tweezers, estrelas e sequências de três velas; somente candle fechado confirma. |
| Regime | Alta, baixa, transição, lateralização, compressão e exaustão usam tratamento distinto; correção profunda e preço sem espaço são explicitamente recusados. |
| Timeframes | Políticas próprias para 1m, 3m, 5m, 15m, 30m, 1h e 4h em todos os perfis e modos; atualização incremental calibrada. |
| Janela ao vivo | Mínimo de 100 e máximo de 200 candles para sinais; até 2.000 candles preservados separadamente para treino/backtest. |
| Stop/alvo | Invalidação e alvo técnicos simétricos por ATR, pivôs, timeframe, expiração e S/R; referências visuais sem execução de ordens. |
| Suporte/resistência | Até dois níveis úteis de cada lado no gráfico, selecionados por distância, força e recência; análise interna preservada. |
| Mudança de tendência | Contraestrutura exige CHOCH ou regime recente estável com eficiência ≥ 0,60 e três votos de momentum. |
| Perfis | Conservador 86/5/ADX20, equilibrado 73/4/ADX15, rápido 57/2/ADX10; os nove cruzamentos com Price Action/Confirmação/Quantitativo possuem políticas progressivas explícitas. |
| Cobertura | Matriz determinística mantém cobertura progressiva sem exigir que sinais com pullback incompleto sejam aprovados para atingir uma meta artificial. |
| Referência 0.9.0 | O SHA-256 do instalador anexado coincide com o build oficial do commit `a16d551d`; cobertura e filtros foram comparados diretamente com esse código-fonte. |
| Timing | Janela máxima de 8 a 12 segundos; preço contrário, stop técnico atingido ou últimos segundos da plataforma invalidam o sinal imediatamente. |
| Áudio | Pré-sinal somente com autorização explícita; sinais confirmados têm prioridade, avisos informativos ficam silenciosos e bloqueios reais têm cooldown de 300 segundos. |
| Backtest | Walk-forward com filtros de extensão, eficiência, compressão, reversão, microtendência, momentum, fluxo validado, payout, equilíbrio, expectativa e Wilson. |
| Estatísticas | WIN/LOSS/DRAW, payout, entrada, P&L, profit factor financeiro, equilíbrio, expectativa, Wilson e origem manual/inferida. |
| Cripto | Binance pública com espelhos oficiais e fallback Coinbase/Kraken; taker buy ausente nunca é confundido com 100% de força vendedora. |
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
- Resultado local: **302 testes aprovados, 0 falhas; 1 smoke test reservado para Windows**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- A suíte completa é repetida pelo GitHub Actions em Windows antes de empacotar o instalador.

Os testes cobrem indicadores, BOS/CHOCH, falsos pullbacks, virada simétrica de compra/venda, fluxo taker ausente, invalidação imediata, últimos segundos do vencimento, áudio opt-in, exaustão, M1, janela 100–200, níveis técnicos, biblioteca causal, purga, modelos separados, backtest, payout, SQLite, VEX/BullEx, loopback, providers, interface e instalador.

Na matriz determinística atual de vinte cenários com modelo alinhado, Price Action produz 4/3/3 leituras, Confirmação 3/3/3 e Quantitativo 3/3/2, respectivamente nos perfis rápido/equilibrado/conservador. Antes da auditoria, sete das dez leituras rápidas de Confirmação continham pullback explicitamente não confirmado. A remoção dessas falsas confirmações preserva a ordem Rápido ≥ Equilibrado ≥ Conservador e a cobertura positiva. Essa matriz mede regressão e segurança, não taxa de acerto futura, desempenho financeiro ou promessa de lucro.

## Interpretação correta

Indecisão isolada dentro de tendência alinhada ainda pode virar aviso nos perfis compatíveis, desde que não exista pullback incompleto ou múltiplas evidências causais de reversão. Lateralização, conflito estrutural, candle aberto, fonte atrasada, retração profunda, invalidação de preço e vencimento tardio continuam impedindo confirmação. Menos sinais não significa precisão garantida: a evidência válida continua sendo backtest fora da amostra e histórico manual por ativo, timeframe, expiração, payout, sensibilidade e modo.

## Empacotamento

`build_windows.ps1` repete os testes, cria `PrimeAITrader.exe`, compila `PrimeAITrader-Setup-x64.exe` e publica o artefato somente após sucesso.

Identificador do candidato validado: `1.2.3`.

O candidato Windows deve repetir obrigatoriamente os 303 testes (302 locais + smoke visual Windows), validar o Tkinter completo e somente então gerar os dois executáveis com Inno Setup.
