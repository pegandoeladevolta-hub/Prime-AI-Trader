# Relatório de validação — PRIME TRADER 1.3.5

Data: 01/09/2026

## Resultado local

- Comando: `python -m unittest discover -s tests -v`
- Resultado: **415 testes aprovados, zero falhas; 1 smoke test visual reservado para Windows**.
- Total descoberto: **416 testes**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- O GitHub Actions repetirá a suíte completa em Windows antes de executar PyInstaller e Inno Setup.

## Matriz validada

| Área | Evidência verificada |
|---|---|
| Sessão já aberta | A primeira chamada usa `initialize()` sem caminho e adota a conta Clear ativa antes de considerar qualquer executável. |
| Erro -6 reproduzido | Uma sessão aberta válida continua conectando quando `initialize(path=...)` devolveria `Terminal: Authorization failed`. |
| Fallback único | Se a sessão aberta não puder ser usada, cada `terminal64.exe` da Clear é tentado uma única vez, sem repetir o mesmo `-6`. |
| Outra corretora | Uma sessão MT5 aberta cujo servidor não pertence à Clear é recusada antes do fallback para o terminal correto. |
| Conta detectada | Servidor e nome da sessão aberta classificam automaticamente Clear Real ou Clear Demo. |
| Terminal único | O mesmo caminho `terminal64.exe` é usado para Real e Demo e recebe a migração dos caminhos antigos. |
| Sem credenciais | A ponte MT5 não possui método para receber login ou senha e nunca envia esses campos ao `initialize`. |
| Limpeza | Campos de login, senha e servidor deixados pelas versões antigas são removidos sem apagar outros segredos. |
| Interface | Não existem seletor Real/Demo, formulário de senha ou login automático; resta somente conectar ao MT5 aberto. |
| Separação | Diário e limites continuam independentes para Real e Demo após a detecção da sessão. |
| Histórico curto | Uma resposta inicial de 108 candles solicita intervalo maior e entra em repetição automática sem reduzir o mínimo de 200. |
| Conta Demo | Modo automático continua disponível após armar a execução. |
| Conta Real | Automático é convertido em execução sob comando; uma segunda trava impede passagem direta pelo motor. |
| SL/TP adaptativos | ATR, pivôs, estrutura, zonas opostas e R:R mínimo geram plano simétrico de compra/venda. |
| Plano inviável | A entrada é recusada quando suporte/resistência não deixa espaço para o retorno mínimo. |
| Meta e stop | P/L realizado do dia bloqueia novas ordens ao atingir os limites configurados. |
| Losses consecutivos | Duas perdas encerradas seguidas bloqueiam nova entrada; win/draw encerra a sequência; zero desativa a trava. |
| Separação de risco | Meta, stop e quantidade de losses ficam independentes em Real e Demo. |
| Diário | Posições e deals do PRIME TRADER são reconciliados com o MT5 e mantidos por conta. |
| Versão Windows | Pacote Python, executável e instalador usam a versão 1.3.5 de forma consistente. |

## Interpretação correta

A meta diária funciona somente como circuito de parada. O programa não pode prometer alcançá-la e não cria uma entrada quando a estrutura ou o R:R são inadequados. Depois de uma trava diária, os sinais continuam aparecendo para auditoria, mas nenhuma nova ordem é enviada pelo PRIME TRADER.

O resultado válido da conta vem dos deals realizados no MT5. Resultado flutuante não é contado como lucro/prejuízo encerrado e não fecha antecipadamente uma posição que já possui SL/TP.

## Empacotamento pendente

`build_windows.ps1` repetirá os testes, validará Tkinter, criará `PrimeAITrader.exe` e compilará `PrimeTrader-Setup-x64.exe`. Este relatório não declara o instalador aprovado até o runner Windows concluir com sucesso.

Identificador do candidato: `1.3.5`.
