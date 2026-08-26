# Arquitetura

```text
Interface Tkinter
    └── TradingController
        ├── MarketDataProvider
        │   ├── ResilientCryptoProvider
        │   │   ├── BinanceSpotProvider / data-api.binance.vision
        │   │   ├── CoinbaseSpotProvider
        │   │   └── KrakenSpotProvider
        │   └── ResilientForexProvider
        │       ├── YahooForexProvider: público, sem chave
        │       ├── TwelveDataProvider / AlphaVantageForexProvider: opcionais
        │       └── FrankfurterReferenceProvider: referência diária
        ├── Indicadores / Price Action / Fibonacci
        │   ├── Candlestick Library: padrões OHLC causais e normalizados por ATR/range
        │   └── Technical Levels: invalidação/alvo por ATR, pivôs e S/R
        ├── Estratégias de mercado
        │   ├── Crypto: volume/taker Binance, VWAP válido e estrutura
        │   └── Forex: sessões IANA/DST, ATR por par e notícias das moedas
        ├── Feature Builder (schema 9 por mercado, padrões e pullbacks)
        ├── ModelManager / SignalEngine / BacktestEngine
        ├── Sincronização visual local
        │   ├── VexBrowserBridge
        │   └── BullexBrowserBridge (opt-in + alerta CVM)
        ├── CompositeNewsProvider: GDELT, Google News, Cointelegraph,
        │                            CoinDesk, FXStreet e ForexLive
        ├── ResilientEconomicCalendar: Forex Factory / Finnhub opcional
        └── Repository SQLite / VoiceService / Logs
```

## Fluxo ao iniciar análise

1. O provider carrega candles históricos; a análise ao vivo exige 100 e usa os 200 mais recentes, enquanto treino/backtest preservam até 2.000 em `history_candles`.
2. Os indicadores são calculados apenas com candles presentes e passados.
3. A estrutura agrupa pivôs próximos em zonas.
4. A biblioteca de candles reconhece padrões na vela atual e nas duas anteriores; vela aberta permanece em formação.
5. O Fibonacci seleciona um swing relevante.
6. O modelo local fornece probabilidades das três classes, se estiver treinado.
7. O motor combina score do modelo com regras auditáveis, setup, payout, padrões confirmados e uma `DecisionPolicy` própria para cada um dos nove cruzamentos de modo/sensibilidade. A política classifica indecisão como veto ou aviso conforme regime, estrutura, eficiência, momentum e modelo, calibrada contra o build oficial 0.9.0. O modelo é consultivo em Price Action/Confirmação e obrigatório no Quantitativo.
8. O módulo `priceaction/levels.py` calcula stop técnico, alvo e espaço contextual. O gráfico mostra somente dois S/R relevantes de cada lado e persiste os níveis no SQLite.
9. Notícias e calendário fornecem contexto; eventos econômicos relevantes podem bloquear o sinal, mas nunca criá-lo sozinhos.
10. Ao abrir uma nova vela, o histórico incremental fecha a anterior e `signals/timing.py` permite que ela confirme a entrada durante uma janela de 8 a 12 segundos. A vela atual continua aberta no gráfico; VEX/BullEx só projetam o novo ciclo para uma confirmação fechada e recém-criada.
11. Após o horizonte, o gráfico pode produzir resultado `INFERRED`; o usuário pode substituí-lo por `MANUAL`, que representa o observado na plataforma.
12. P&L e profit factor usam payout e valor da entrada, nunca a amplitude percentual do feed externo.

## Separação de responsabilidades

| Diretório | Responsabilidade |
|---|---|
| `app/` | Orquestração e estado |
| `market/`, `crypto/`, `forex/` | Contratos e feeds |
| `news/`, `economic_calendar/` | Contexto e bloqueios |
| `indicators/` | Matemática de indicadores |
| `priceaction/`, `fibonacci/` | Estrutura, biblioteca de candles e Fibonacci |
| `strategies/` | Políticas distintas de cripto e Forex |
| `platform/` | VEX/BullEx visual local, sem execução |
| `features/`, `ml/` | Features e modelos locais |
| `signals/`, `backtest/`, `radar/` | Decisão e validação |
| `database/`, `config/` | Persistência e segredos |
| `ui/` | Janela, gráfico e diálogos |
| `installer/` | Instalação Windows |

## Auditoria do modelo

O arquivo `%APPDATA%\PrimeAITrader\models\training_report.json` registra o modelo escolhido, versão, data, amostras e métricas de cada fold. Os artefatos em `models\contexts` são identificados pelo hash de mercado, ativo, timeframe, expiração, estratégia, sensibilidade, modo e schema. O modelo ativo recebe versão imutável `ml-AAAAMMDD-HHMMSS`.
