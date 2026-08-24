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
        │   └── Candlestick Library: padrões OHLC causais e normalizados por ATR/range
        ├── Estratégias de mercado
        │   ├── Crypto: volume/taker Binance, VWAP válido e estrutura
        │   └── Forex: sessões IANA/DST, ATR por par e notícias das moedas
        ├── Feature Builder (schema 7 por mercado e padrões de candles)
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

1. O provider carrega candles históricos.
2. Os indicadores são calculados apenas com candles presentes e passados.
3. A estrutura agrupa pivôs próximos em zonas.
4. A biblioteca de candles reconhece padrões na vela atual e nas duas anteriores; vela aberta permanece em formação.
5. O Fibonacci seleciona um swing relevante.
6. O modelo local fornece probabilidades das três classes, se estiver treinado.
7. O motor combina o modelo com regras auditáveis, setup, payout, padrões confirmados e threshold da sensibilidade.
8. Notícias e calendário fornecem contexto; eventos econômicos relevantes podem bloquear o sinal, mas nunca criá-lo sozinhos.
9. Sinais confirmados são salvos tanto na análise inicial quanto na atualização contínua por WebSocket.
10. Após o horizonte, o gráfico pode produzir resultado `INFERRED`; o usuário pode substituí-lo por `MANUAL`, que representa o observado na plataforma.
11. P&L e profit factor usam payout e valor da entrada, nunca a amplitude percentual do feed externo.

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
