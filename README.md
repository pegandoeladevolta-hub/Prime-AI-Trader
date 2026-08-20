# PRIME AI TRADER

Build automático para Windows x64 configurado no GitHub Actions.

Assistente quantitativo desktop para análise de criptomoedas e Forex. A versão 0.3.0 gera sinais de **COMPRA**, **VENDA** ou **AGUARDAR**, mas **não envia ordens** a corretoras.

## O que funciona nesta versão

- Aplicativo nativo em uma única janela Tkinter, sem Chrome/Edge e sem servidor web local.
- Binance Spot REST para histórico, 30 ativos iniciais e até 100 pares USDT líquidos; WebSocket para candle em tempo real com reconexão exponencial.
- Forex por Twelve Data com 28 pares, cache e controle de consumo do plano gratuito.
- Gráfico próprio de candles e volume com zoom, arraste, crosshair, OHLC, EMAs, Bollinger, S/R e Fibonacci.
- Atualização parcial da última vela sem redesenhar todo o gráfico, com troca segura de ativo e cache curto.
- EMA 9/21/50, RSI 14, MACD 12/26/9, Bollinger, Stochastic 14/3, ADX/+DI/-DI, ATR, VWAP, OBV, CCI, Williams %R, volume relativo e volatilidade histórica.
- Pivôs, HH/HL/LH/LL, zonas agrupadas, rompimento, falso rompimento, reteste e Fibonacci automático.
- IA local leve: Logistic Regression, HistGradientBoosting, Random Forest pequeno e Gradient Boosting pequeno, persistidos separadamente por ativo/timeframe/horizonte.
- Seleção do modelo por validação temporal walk-forward, sem random split.
- Sinal de três classes, pré-sinal, confirmação no fechamento, três sensibilidades e filtros de tendência/momentum.
- Notícias GDELT e classificação local de risco/sentimento; calendário Finnhub para Forex quando a chave permite o endpoint.
- Radar de mercado, backtest fora da amostra, acerto direcional sem misturar DRAW com LOSS, matriz de confusão, cobertura e proteção contra contextos fracos.
- SQLite para histórico, fechamento posterior do resultado e confiança calibrada somente após 30 exemplos do mesmo intervalo de score.
- Voz pt-BR via Windows Speech, com limitação de repetição.
- Chaves protegidas por Windows DPAPI; nenhuma chave fica no código-fonte.
- Logs rotativos e mensagens de erro compreensíveis.

## Requisitos do computador

- Windows 10/11 x64.
- 8 GB de RAM.
- Python 3.11–3.13 apenas para executar o código-fonte. A instalação final criada pelo script inclui o runtime e não exige Python no computador do usuário.
- Internet para dados ao vivo.

O projeto limita o treinamento a modelos CPU, define `n_jobs=1` no Random Forest e não usa GPU nem LLM para prever candles.

## Executar pelo código-fonte

No PowerShell, dentro da pasta do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Criptomoedas públicas da Binance funcionam sem chave. Para ativar Forex, abra **APIs** no aplicativo e informe a chave da Twelve Data. A chave Finnhub é opcional e serve para o calendário econômico quando o plano permite. As chaves são salvas fora da pasta de instalação.

## Gerar o EXE e o instalador

Em um Windows x64 com Python e [Inno Setup 6](https://jrsoftware.org/isinfo.php) instalados:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

Saídas:

- `release\PrimeAITrader.exe`
- `release\PrimeAITrader-Setup-x64.exe`

O instalador cria atalhos opcionais, entrada no menu Iniciar, desinstalador e registro em **Configurações > Aplicativos instalados**.

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem indicadores, Fibonacci, pivôs, zonas, features, labels, ausência de uso do futuro nas features, folds temporais, IA, backtest, banco, bloqueio de risco, parsing dos provedores e o contrato de que todo botão visível declara uma ação.

## Dados locais

Em Windows, o programa grava em `%APPDATA%\PrimeAITrader`:

- `settings.json` — preferências sem segredos;
- `secrets.dat` — chaves protegidas por DPAPI;
- `prime_ai_trader.db` — sinais e resultados;
- `models\` — modelos e relatórios separados por contexto;
- `logs\app.log` — logs rotativos.

## Limitações honestas da 0.3.0

- Não envia nem executa ordens.
- Twelve Data precisa de chave. O plano gratuito informa 800 créditos por dia, por isso o app consulta Forex em ritmo econômico.
- O calendário econômico Finnhub pode exigir plano com acesso ao endpoint.
- O feed Forex usa atualização periódica de aproximadamente 125 segundos; o streaming contínuo implementado nesta versão é o da Binance.
- A voz depende de PowerShell e das vozes instaladas no Windows.
- “Score do modelo” não significa “chance de ganhar”. A taxa observada só aparece após amostra real suficiente.
- Backtest não é garantia de desempenho futuro.
- Cada ativo/timeframe/horizonte precisa de treinamento próprio para usar a IA; sem modelo compatível, o app permanece nas regras e confluências.

## Aviso de risco

Este software é uma ferramenta de análise e educação. Criptomoedas e Forex envolvem risco elevado, inclusive perda integral do capital. Verifique os dados e faça sua própria gestão de risco antes de operar.
