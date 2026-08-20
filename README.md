# PRIME AI TRADER

Build automático da versão 0.4.1 para Windows x64 configurado no GitHub Actions.

Assistente quantitativo desktop para análise de criptomoedas e Forex. O aplicativo gera cenários de **COMPRA**, **VENDA** ou **AGUARDAR**, mas **não envia ordens** a corretoras.

## Destaques da versão 0.4.1

- Correção do contexto do modelo: a IA treinada agora é carregada também na primeira análise completa.
- Comportamento fluido da v0.3.0 restaurado, mantendo as correções das versões posteriores.
- Mais histórico no treinamento e backtest (até 1.500 candles por contexto).
- Seleção de modelo pela precisão direcional seletiva com limite inferior de Wilson, cobertura mínima e validação walk-forward.
- Purga temporal entre treino e teste para evitar vazamento causado pelo horizonte do rótulo.
- Limites de sinais recalibrados para não reduzir o backtest a poucas operações; tendência, momentum, volatilidade extrema e preço excessivamente estendido continuam filtrados.
- Probabilidade mínima e vantagem mínima sobre o cenário oposto iguais no sinal ao vivo e no backtest.
- Calibração separada por mercado, ativo, timeframe, horizonte e modo; `DRAW` não entra na taxa de acerto.
- Notícias classificadas por palavras completas, correção de moedas de eventos Forex e expiração de bloqueios antigos.
- Threads de rede e cálculo não acessam mais o Tkinter diretamente; treinamento, backtest, desempenho e diagnósticos ficam fora da interface.
- Botões para atualizar o gráfico e limpar cache/modelos antigos com preservação de chaves, configurações e histórico.
- Radar Forex em lotes rotativos compatíveis com o limite da API gratuita.
- 30 criptomoedas iniciais, até 100 pares USDT líquidos e 28 pares de Forex.

## Recursos

- Interface nativa Tkinter, sem navegador ou servidor web local.
- Binance Spot REST/WebSocket para criptomoedas, sem chave.
- Twelve Data para Forex com chave gratuita, cache e controle de consumo.
- GDELT para notícias, sem chave; Finnhub opcional para calendário econômico.
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
| Binance Spot | Criptomoedas | Não | Nenhum |
| GDELT | Notícias | Não | Nenhum |
| Twelve Data Basic | Forex | Sim, gratuita | Nenhum |
| Finnhub | Calendário extra | Opcional | Nenhum para o funcionamento do app |

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

A versão 0.4.1 possui 56 testes automatizados cobrindo matemática, ausência de look-ahead, purga temporal, modelos, backtest, sinais, banco, limpeza segura, provedores, reconexão, threads da interface, desempenho do gráfico e comandos dos botões.

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
- Twelve Data exige uma chave gratuita e aplica limites de créditos.
- O feed Forex é consultado aproximadamente a cada 125 segundos; o streaming contínuo é da Binance.
- Backtest e desempenho passado não garantem resultado futuro.

Consulte `docs/STRATEGY.md` para a lógica dos filtros e os limites da validação.

## Aviso de risco

Este software é uma ferramenta de análise e educação. Criptomoedas e Forex envolvem risco elevado, inclusive perda integral do capital. Verifique os dados e faça sua própria gestão de risco antes de operar.
