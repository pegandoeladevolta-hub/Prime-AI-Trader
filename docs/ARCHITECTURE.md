# Arquitetura

```text
Interface Tkinter
    └── TradingController
        ├── MarketDataProvider
        │   ├── BinanceSpotProvider
        │   └── TwelveDataProvider
        ├── Indicadores / Price Action / Fibonacci
        ├── Feature Builder
        ├── ModelManager / SignalEngine / BacktestEngine
        ├── NewsProvider / EconomicCalendar
        └── Repository SQLite / VoiceService / Logs
```

## Fluxo ao iniciar análise

1. O provider carrega candles históricos.
2. Os indicadores são calculados apenas com candles presentes e passados.
3. A estrutura agrupa pivôs próximos em zonas.
4. O Fibonacci seleciona um swing relevante.
5. O modelo local fornece probabilidades das três classes, se estiver treinado.
6. O motor combina o modelo com regras auditáveis e aplica o threshold da sensibilidade.
7. Notícias e calendário podem bloquear o sinal, mas nunca criá-lo sozinhos.
8. Somente sinal confirmado é salvo.
9. Após o horizonte, o resultado é fechado pelo preço observado.

## Separação de responsabilidades

| Diretório | Responsabilidade |
|---|---|
| `app/` | Orquestração e estado |
| `market/`, `crypto/`, `forex/` | Contratos e feeds |
| `news/`, `economic_calendar/` | Contexto e bloqueios |
| `indicators/` | Matemática de indicadores |
| `priceaction/`, `fibonacci/` | Estrutura de mercado |
| `features/`, `ml/` | Features e modelos locais |
| `signals/`, `backtest/`, `radar/` | Decisão e validação |
| `database/`, `config/` | Persistência e segredos |
| `ui/` | Janela, gráfico e diálogos |
| `installer/` | Instalação Windows |

## Auditoria do modelo

O arquivo `%APPDATA%\PrimeAITrader\models\training_report.json` registra o modelo escolhido, versão, data, amostras e métricas de cada fold de cada candidato. O modelo ativo recebe uma versão imutável no formato `ml-AAAAMMDD-HHMMSS`.

