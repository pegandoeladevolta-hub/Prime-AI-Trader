# PRIME AI TRADER

Build automático da versão 0.5.0 para Windows x64 configurado no GitHub Actions.

Assistente quantitativo desktop para análise de criptomoedas e Forex. O aplicativo gera cenários de **COMPRA**, **VENDA** ou **AGUARDAR**, mas **não envia ordens** a corretoras.

## Destaques da versão 0.5.0

- As 10 criptomoedas identificadas na plataforma aparecem primeiro: BTC, LTC, ADA, BNB, XRP, ETH, SOL, DOGE, SUI e XLM/Stellar.
- Binance com hosts públicos oficiais alternativos e fallback automático para Coinbase Exchange e Kraken.
- Forex público sem chave, com Twelve Data e Alpha Vantage opcionais; Frankfurter fornece referência diária sem simular candles intraday.
- Notícias visíveis no painel e atualizadas automaticamente por GDELT, Google Notícias, Cointelegraph, CoinDesk, FXStreet e ForexLive.
- Calendário econômico público sem chave, com cache de uma hora; Finnhub permanece opcional.
- Estratégias de pullback na EMA 21, rompimento/reteste, varredura de liquidez, rejeição, engolfo e confirmação do timeframe superior.
- Score técnico e score da IA aparecem separadamente; quando houver AGUARDAR, o motivo concreto é mostrado.
- Pagamento configurável da plataforma: cálculo de ponto de equilíbrio, expectativa e intervalo de confiança no backtest.
- Sinais confirmados durante o WebSocket são gravados; resultados vencidos alimentam corretamente a calibração real.
- Amostra de backtest em formação aparece como informação discreta, sem aviso amarelo e sem bloqueio.
- Correção do contexto do modelo: a IA treinada agora é carregada também na primeira análise completa.
- Comportamento fluido da v0.3.0 restaurado, mantendo as correções das versões posteriores.
- Mais histórico no treinamento e backtest (até 2.000 candles por contexto).
- Seleção de modelo pela precisão direcional seletiva com limite inferior de Wilson, cobertura mínima e validação walk-forward.
- Purga temporal entre treino e teste para evitar vazamento causado pelo horizonte do rótulo.
- Limites de sinais recalibrados para não reduzir o backtest a poucas operações; tendência, momentum, volatilidade extrema e preço excessivamente estendido continuam filtrados.
- Probabilidade mínima e vantagem mínima sobre o cenário oposto iguais no sinal ao vivo e no backtest.
- Calibração separada por mercado, ativo, timeframe, horizonte e modo; `DRAW` não entra na taxa de acerto.
- Notícias classificadas por palavras completas, correção de moedas de eventos Forex e expiração de bloqueios antigos.
- Threads de rede e cálculo não acessam mais o Tkinter diretamente; treinamento, backtest, desempenho e diagnósticos ficam fora da interface.
- Botões para atualizar o gráfico e limpar cache/modelos antigos com preservação de chaves, configurações e histórico.
- Radar Forex em lotes rotativos compatíveis com o limite da API gratuita.
- 31 criptomoedas iniciais, até 100 pares USDT líquidos e 28 pares de Forex.

## Recursos

- Interface nativa Tkinter, sem navegador ou servidor web local.
- Binance Spot REST/WebSocket, Coinbase Exchange e Kraken para criptomoedas, sem chave.
- Forex público sem chave, Twelve Data gratuita e Alpha Vantage gratuita opcional, com cache e controle de consumo.
- GDELT e feeds RSS para notícias sem chave; calendário econômico público e Finnhub opcional.
- Gráfico próprio de candles/volume com zoom, arraste, crosshair, EMAs, Bollinger, S/R e Fibonacci.
- EMA 9/21/50, RSI, MACD, Bollinger, Stochastic, ADX/+DI/-DI, ATR, VWAP, OBV, CCI, Williams %R, volume relativo e volatilidade histórica.
- Price Action com HH/HL/LH/LL, zonas, rompimento, falso rompimento e reteste.
- Quatro modelos locais leves, persistidos por ativo/timeframe/horizonte/schema.
- Radar, backtest fora da amostra, SQLite, desempenho observado, voz pt-BR e logs rotativos.
- Chaves protegidas pelo Windows DPAPI e nunca incluídas no código-fonte.

## Requisitos

- Windows 10/11 x64.
- 8 GB de RAM.
- Internet para dados ao vivo.
- Python 3.11–3.13 somente para executar o código-fonte; o instalador final inclui o runtime.

## APIs

| Fonte | Uso | Chave | Custo obrigatório |
|---|---|---|---|
| Binance Spot + espelhos oficiais | Criptomoedas e WebSocket | Não | Nenhum |
| Coinbase Exchange | Backup de criptomoedas em USD | Não | Nenhum |
| Kraken | Backup de criptomoedas em USD | Não | Nenhum |
| Yahoo Finance Forex público | Candles Forex | Não | Nenhum |
| Frankfurter | Referência cambial diária, nunca intraday | Não | Nenhum |
| Twelve Data Basic | Forex principal opcional | Sim, gratuita | Nenhum |
| Alpha Vantage | Forex alternativo opcional | Sim, gratuita | Nenhum |
| GDELT + Google Notícias + RSS | Notícias cripto/Forex | Não | Nenhum |
| Calendário econômico público | Eventos de alto impacto | Não | Nenhum |
| Finnhub | Calendário extra | Opcional | Nenhum |

Por padrão, notícias, eventos e backtest fraco aparecem como avisos. O bloqueio automático de notícia/evento pode ser ativado no painel esquerdo.

## Executar pelo código-fonte

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

## Gerar o EXE e o instalador

Em Windows x64 com Python e Inno Setup 6:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

Saídas:

- `release\PrimeAITrader.exe`
- `release\PrimeAITrader-Setup-x64.exe`

## Testes

```powershell
python -m unittest discover -s tests -v
```

A versão 0.5.0 possui 85 testes automatizados cobrindo matemática, ausência de look-ahead, purga temporal, modelos, backtest, payout, sinais, banco, feeds públicos, fallback, calendário, notícias, limpeza segura, reconexão, threads da interface, desempenho do gráfico e comandos dos botões.

## Dados locais

Em Windows, o programa grava em `%APPDATA%\PrimeAITrader`:

- `settings.json` — preferências sem segredos;
- `secrets.dat` — chaves protegidas por DPAPI;
- `prime_ai_trader.db` — sinais e resultados;
- `models\` — modelos e relatórios separados por contexto;
- `logs\app.log` — logs rotativos.

## Limitações honestas

- Não executa ordens nem promete lucro ou taxa fixa de acerto.
- Os filtros mais rigorosos reduzem a quantidade de sinais; `AGUARDAR` é uma decisão válida.
- Cada ativo/timeframe/horizonte precisa de treinamento próprio para usar a IA.
- Twelve Data e Alpha Vantage exigem chaves gratuitas apenas se forem configuradas; o Forex público não exige chave, mas sua disponibilidade não é garantida.
- Frankfurter publica referência diária; ela nunca é apresentada como cotação intraday.
- O Forex é atualizado entre aproximadamente 60 e 120 segundos; o streaming contínuo é da Binance.
- Coinbase/Kraken podem usar par USD como referência para o ativo USDT; compare o preço com o da plataforma.
- Ativos OTC/sintéticos e preços internos de corretoras podem divergir das APIs públicas e não devem ser tratados como feeds equivalentes.
- Backtest e desempenho passado não garantem resultado futuro.

Consulte `docs/STRATEGY.md` para a lógica dos filtros e os limites da validação.

## Aviso de risco

Este software é uma ferramenta de análise e educação. Criptomoedas e Forex envolvem risco elevado, inclusive perda integral do capital. Verifique os dados e faça sua própria gestão de risco antes de operar.
