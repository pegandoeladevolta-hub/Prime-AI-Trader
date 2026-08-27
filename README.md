# PRIME TRADER

**Prime Trader 1.4.0** é a evolução do motor analítico que estava na versão **1.2.6**, agora organizado como terminal desktop e integrado localmente ao **MetaTrader 5**.

A prioridade desta edição é preservar a lógica aprovada em **1 minuto + perfil RÁPIDO + PRICE ACTION** e separar claramente três coisas: análise, interface e execução de ordens.

## O que mudou

- Nome do produto: **PRIME TRADER**.
- A tela principal deixa de usar o painel de cartões como navegação principal e passa a seguir uma estrutura de terminal: barra lateral estreita, abas de ativos no topo, gráfico dominante e boleta MT5 à direita.
- VEX e BullEx não aparecem nem são usadas no fluxo operacional do Prime Trader.
- A origem dos candles para negociação pela Clear passa a ser o **MetaTrader 5 já autenticado pelo usuário**.
- O programa não solicita nem armazena login ou senha da corretora.
- Histórico de negócios, conta, posições, candles e ativos são lidos do terminal local.
- A boleta oferece **COMPRAR**, **VENDER** e **ENCERRAR POSIÇÃO**.
- Execução real começa **bloqueada em toda inicialização** e exige confirmação explícita.
- O modo automático é separado da operação manual e começa desligado.
- Um sinal automático só pode disparar quando estiver `CONFIRMADO`, com deduplicação por ativo/timeframe/vela/direção.
- Stop e alvo técnicos do motor podem acompanhar a ordem quando estiverem disponíveis.

## Configuração de referência

A configuração destacada pelo próprio aplicativo é:

- gráfico/timeframe: `1m`;
- horizonte: `1 minuto`;
- sensibilidade: `RÁPIDO`;
- modo: `PRICE ACTION`.

O `SignalEngine`, os indicadores, a leitura de estrutura, Price Action, Fibonacci, regras de reversão e política de sinais vêm da base da v1.2.6. O adaptador MT5 troca a fonte de candles sem reescrever essas regras.

> Importante: o bom comportamento observado anteriormente não é uma garantia de resultado futuro. Dados da B3/MT5 constituem um contexto de mercado diferente e devem ser validados com conta demo e amostra suficiente antes de usar automação em conta real.

## MetaTrader 5 e Clear

Instale e abra o MetaTrader 5 fornecido/suportado pela sua corretora e faça login **no próprio terminal**. Depois abra o Prime Trader e clique em **CONECTAR MT5**.

Fluxo recomendado:

1. Instale o MetaTrader 5 oficial.
2. No MT5, conecte sua conta da Clear.
3. Deixe os ativos desejados visíveis em **Observação do Mercado**.
4. Abra o Prime Trader.
5. Clique em **CONECTAR MT5**.
6. Escolha o ativo.
7. Teste primeiro com a configuração `1m / RÁPIDO / PRICE ACTION`.
8. Para operação manual pela interface, habilite ordens e clique em COMPRAR/VENDER.
9. Só ative **Execução automática do sinal** depois de validar o comportamento em demo.

O Prime Trader não altera o instalador oficial `mt5setup.exe`; ele se conecta ao terminal instalado através da integração Python do MetaTrader 5. Isso preserva assinatura, atualização e autenticação do terminal.

## Segurança de execução

- Nenhuma senha da corretora é armazenada.
- O botão de execução real fica bloqueado após reiniciar o aplicativo.
- A automação também volta desligada após reiniciar.
- Conta `REAL` e `DEMO` são mostradas de forma distinta.
- Antes de habilitar ordens reais há confirmação explícita.
- A ordem passa por `order_check` e depois `order_send`.
- Erros e rejeições do servidor são exibidos e registrados em log.
- O botão ENCERRAR envia a ordem oposta para fechar as posições do ativo selecionado.

## Navegação

- **Gráfico:** volta ao gráfico sem drawer lateral.
- **Sinais:** mostra o detalhamento técnico da leitura atual.
- **Histórico:** carrega os negócios dos últimos 30 dias diretamente do MT5.
- **Análise:** concentra ativo, sensibilidade, modo, horizonte, iniciar e pausar.
- **Notícias:** abre notícias públicas relacionadas ao mercado brasileiro; elas não alteram automaticamente o sinal MT5 nesta edição.
- **Ajustes:** terminal MT5, áudio, logs, saúde e APIs auxiliares.

## Build Windows

Requisitos de desenvolvimento:

- Windows 10/11 x64;
- Python 3.12 x64;
- MetaTrader 5 instalado para teste de integração real;
- Inno Setup 6;
- PyInstaller.

Build:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

Saídas:

```text
release\PrimeTrader.exe
release\PrimeTrader-Setup-x64.exe
```

## Aviso de risco

O Prime Trader é software de análise e execução técnica. Mercado financeiro envolve risco de perda. Sinais, indicadores, modelos e Price Action não garantem lucro nem taxa de acerto futura. Valide em ambiente de demonstração antes de habilitar ordens reais ou automação.
