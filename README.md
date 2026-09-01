# PRIME TRADER 1.3.5

Terminal desktop com interface inspirada no layout solicitado e conexão ao MetaTrader 5. O PRIME TRADER usa o MT5 instalado no computador como fonte de mercado, conta, posições, histórico e execução. Ele não modifica os arquivos internos nem a interface original do MetaTrader 5.

## O que esta versão faz

- Conecta ao terminal MetaTrader 5 da Clear e confirma se a sessão aberta é **CLEAR REAL** ou **CLEAR SIMULADOR / DEMO**.
- Tenta primeiro a sessão MT5 que já está aberta, sem forçar um novo contexto pelo caminho do executável.
- Se a sessão aberta for de outra corretora, recusa essa conta e só então tenta o `terminal64.exe` da Clear.
- Usa um único caminho do terminal da Clear para conta Real e Demo; a troca de conta acontece somente dentro do próprio MetaTrader 5.
- Não solicita nem salva login, servidor ou senha. Credenciais MT5 deixadas pelas versões antigas são removidas na primeira abertura.
- Ao conectar, lê login e servidor da sessão aberta e identifica automaticamente se a conta é **CLEAR REAL** ou **CLEAR DEMO**.
- Histórico, diário e limites de risco continuam separados conforme a conta detectada.
- Lê candles e conta diretamente do MT5, pesquisa os símbolos disponíveis na corretora e mostra posições e resultados realizados no gráfico e no diário.
- Quando um ativo recém-aberto entrega menos de 200 candles, solicita um intervalo maior ao servidor e repete a carga automaticamente; não gera análise com histórico insuficiente.
- Analisa de 500 a 3.000 candles do MT5 por decisão (padrão: 2.000), mantendo os 200 mais recentes no gráfico, além de estrutura, tendência, momentum, volatilidade, padrões, suporte/resistência e contexto de timeframe superior.
- Calcula Entrada, Stop Loss e Take Profit adaptativos por ATR, pivôs, zonas estruturais e relação risco/retorno mínima.
- Rejeita a entrada quando uma barreira técnica não deixa espaço para o R:R configurado; o alvo não é alongado artificialmente para tentar alcançar a meta diária.

## Modos de execução

| Perfil | Conta Demo | Conta Real |
|---|---|---|
| **SÓ SINAIS** | Analisa e avisa, sem enviar ordem | Analisa e avisa, sem enviar ordem |
| **EXECUTAR SOB COMANDO** | Exige clique de confirmação | Exige clique de confirmação |
| **AUTOMÁTICO** | Permitido após armar as ordens | Bloqueado; muda para confirmação manual |

O modo automático da conta Demo usa o SL e o TP do plano técnico confirmado. Há defesa adicional no motor para impedir que uma ordem automática passe quando o perfil ativo é Real.

## Limites do dia

Cada conta possui controles independentes:

- **Meta diária:** bloqueia novas ordens após o lucro realizado atingir o valor definido.
- **Stop diário:** bloqueia novas ordens após o prejuízo realizado atingir o limite definido.
- **Losses seguidos:** por padrão, bloqueia novas ordens depois de 2 perdas consecutivas no dia; `0` desativa essa trava.

Somente operações encerradas entram nos limites. Uma posição aberta não é encerrada antecipadamente por esses campos. Ao atingir uma trava, o PRIME TRADER continua analisando e exibindo sinais, mas não envia nova ordem até o próximo dia ou até o usuário alterar conscientemente o limite.

A meta diária é um circuito de parada. Ela não obriga a IA a operar, aumentar lote, afastar o Stop ou buscar operações em mercado inadequado.

## Configuração das contas Clear

1. Instale e abra o terminal oficial MetaTrader 5 fornecido pela Clear.
2. Faça o login na conta desejada diretamente dentro do MetaTrader 5 e aguarde as cotações aparecerem.
3. Deixe o terminal aberto. Não informe login ou senha no PRIME TRADER.
4. Se necessário, use **SELECIONAR TERMINAL MT5** uma única vez e escolha `terminal64.exe` da instalação da Clear.
5. Clique em **CONECTAR AO MT5 ABERTO**. O aplicativo exibirá automaticamente **CLEAR DEMO** ou **CLEAR REAL** e o número da conta detectada.

Para trocar entre Demo e Real, altere a conta dentro do MetaTrader 5 e conecte novamente. O PRIME TRADER nunca realiza essa troca por senha.

## Gestão técnica

- **SCALP:** Stop mais curto, adequado a movimentos menores e maior sensibilidade ao ruído.
- **INTRADAY:** Stop estrutural mais amplo e janela analítica maior.
- **R:R mínimo:** define o retorno técnico mínimo em relação ao risco. O padrão é `1:1,5`.
- **SL/TP manual:** disponível apenas quando o usuário deseja substituir conscientemente o plano técnico na execução sob comando.

O lote não equivale a um valor fixo em reais. Antes da ordem, o PRIME TRADER consulta a fórmula do símbolo no MT5 para estimar perda no SL e ganho no TP na moeda da conta.

## Instalação e desenvolvimento

Requisitos: Windows x64, Python 3.11–3.13 para desenvolvimento, MetaTrader 5 da corretora e mercado disponível para a conta selecionada.

```powershell
python -m pip install -r requirements.txt
python run.py
```

Para gerar o instalador em Windows x64 com Inno Setup 6:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

Saídas:

- `release\PrimeAITrader.exe`
- `release\PrimeTrader-Setup-x64.exe`

## Testes

```powershell
python -m unittest discover -s tests -v
python -m compileall -q prime_ai_trader tests
```

A suíte cobre anexação à sessão MT5 aberta, fallback pelo executável, classificação Real/Demo, ausência e limpeza de credenciais antigas, troca de perfil, plano adaptativo de SL/TP, execução, uma posição por vez, diário, saldo, meta/stop diário, duas perdas consecutivas, análise, notícias, modelos, SQLite, interface e empacotamento Windows.

## Dados locais

O programa grava em `%APPDATA%\PrimeAITrader`:

- `settings.json` — preferências sem segredos;
- `secrets.dat` — chaves e credenciais protegidas pelo Windows;
- `prime_ai_trader.db` — base analítica legada;
- diários MT5 separados para Real e Demo;
- `models\` — modelos e relatórios separados por contexto;
- `logs\app.log` — logs rotativos.

## Limitações e risco

- Nenhuma lógica garante lucro, acerto fixo ou alcance da meta diária.
- Notícias e dados externos podem atrasar ou ficar indisponíveis; o MT5 continua sendo a referência operacional.
- Backtest e desempenho passado não garantem resultado futuro.
- A conta Real sempre exige confirmação manual nesta versão.
- Revise ativo, direção, lote, Entrada, SL, TP, ambiente e saldo no MT5 antes de confirmar uma ordem real.
- Mercado financeiro envolve risco de perda parcial ou integral do capital.

Consulte `docs/STRATEGY.md` para a lógica dos filtros e os limites da validação.
