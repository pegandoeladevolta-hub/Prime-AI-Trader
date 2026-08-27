# Release notes

## 1.4.0 — Prime Trader / MT5

Esta edição foi criada diretamente a partir do commit da **v1.2.6** para preservar o comportamento aprovado do motor, em vez de continuar em cima da interface e das mudanças da v1.3.0.

### Base analítica preservada

- `SignalEngine` da v1.2.6 preservado.
- Perfis `RÁPIDO`, `EQUILIBRADO` e `CONSERVADOR` preservados.
- Modos `PRICE ACTION`, `CONFIRMAÇÃO` e `QUANTITATIVO` preservados.
- Regra de confirmação pela vela fechada e janela curta de entrada preservada.
- Estrutura, Fibonacci, padrões de candles, reversão, momentum, suporte/resistência e níveis técnicos preservados.
- Configuração recomendada na interface: `1m + RÁPIDO + PRICE ACTION`, horizonte de 1 minuto.

### Nova interface PRIME TRADER

- Produto renomeado visualmente para **PRIME TRADER**.
- Layout principal reorganizado como terminal: trilho lateral, abas de ativos, gráfico central dominante e boleta à direita.
- VEX e BullEx não aparecem nem são usadas no fluxo operacional da nova interface.
- Navegação deixa de reutilizar a mesma tela para botões diferentes:
  - Gráfico volta ao gráfico;
  - Sinais abre o detalhamento técnico;
  - Histórico lê o histórico real do MT5;
  - Análise abre os parâmetros do motor;
  - Notícias consulta fontes públicas do mercado brasileiro;
  - Ajustes concentra MT5, áudio, logs e saúde.

### MetaTrader 5 / Clear

- Novo gateway local `prime_ai_trader/platform/mt5.py`.
- Conecta ao terminal MetaTrader 5 já autenticado pelo usuário; não recebe senha da corretora.
- Lê conta, modo REAL/DEMO, saldo, patrimônio, P&L, ativos, candles, posições e negócios históricos.
- Carrega candles `1m`, `3m`, `5m`, `15m`, `30m`, `1h` e `4h` do terminal.
- Novo adaptador leva os candles MT5 ao motor analítico da v1.2.6 sem reescrever o SignalEngine.
- Boleta envia ordem a mercado com `order_check` + `order_send`.
- Suporte a COMPRAR, VENDER e ENCERRAR posições.
- Stop e alvo técnicos podem acompanhar a ordem quando o sinal os fornece.
- Histórico dos últimos 30 dias é carregado diretamente do terminal.

### Proteções da execução real

- Execução real inicia bloqueada em toda abertura do aplicativo.
- Conta real exige confirmação explícita antes de liberar os botões de ordem.
- Automação começa desligada e precisa de confirmação própria.
- Automação exige sinal `CONFIRMADO` e deduplica por ativo/timeframe/vela/direção.
- Desconectar o MT5 religa automaticamente o bloqueio de ordens.
- Rejeições do terminal/corretora não são mascaradas como sucesso.
- Login, senha, token e assinatura eletrônica não são armazenados pelo Prime Trader.

### Instalador

- Novo executável: `PrimeTrader.exe`.
- Novo instalador: `PrimeTrader-Setup-x64.exe`.
- Versão do produto: `1.4.0`.
- O instalador oficial do MetaTrader 5 não é modificado nem reempacotado dentro do robô.

### Validação

A suíte da v1.2.6 continua sendo executada integralmente no build Windows, acrescida dos testes do novo gateway MT5. O instalador só é publicado quando testes, compilação estática, importação do MetaTrader5, PyInstaller e Inno Setup terminam com sucesso.

### Limitação importante

O motor foi preservado porque apresentou o comportamento desejado no contexto anterior, mas **resultado passado não é garantia de resultado futuro**. B3/MT5 é um contexto de mercado diferente. Antes de habilitar execução automática em conta real, valide o ativo e a configuração em conta demo e com amostra suficiente.
