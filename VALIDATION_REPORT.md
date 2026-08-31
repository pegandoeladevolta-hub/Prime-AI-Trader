# Relatório de validação — PRIME TRADER 1.3.3

Data: 31/08/2026

## Resultado local

- Comando: `python -m unittest discover -s tests -v`
- Resultado: **416 testes aprovados, zero falhas; 1 smoke test visual reservado para Windows**.
- Total descoberto: **417 testes**.
- `python -m compileall -q prime_ai_trader tests`: aprovado.
- O GitHub Actions repetirá a suíte completa em Windows antes de executar PyInstaller e Inno Setup.

## Matriz validada

| Área | Evidência verificada |
|---|---|
| Conta selecionada | Botões Real/Demo, seletor e perfil persistente apontam para o mesmo ambiente. |
| Demo sem Real | Servidor Real preenchido por padrão não transforma a seção vazia em cadastro parcial nem bloqueia o salvamento da Demo. |
| Separação | Terminal, credenciais, diário e limites são independentes entre Clear Real e Clear Simulador. |
| Erro da captura | Uma sessão MT5 no ambiente oposto gera erro tipado e oferece trocar para a conta detectada, revisar credenciais ou cancelar. |
| Autenticação | Login e servidor são aplicados ao perfil correto; senha não aparece no diagnóstico. |
| Sessão ativa | Conta já aberta com login, servidor e ambiente esperados é reutilizada sem uma segunda autenticação. |
| Erro `-6` | Reautenticação rejeitada pela Clear não bloqueia a sessão Demo correta que já está conectada. |
| Troca de conta | Credenciais só são enviadas quando a sessão ativa não corresponde ao perfil selecionado. |
| Proteção de senha | Credenciais são protegidas por DPAPI no Windows e vinculadas ao usuário local. |
| Persistência | Cadastro Demo é gravado, relido por uma nova instância do cofre e comparado sem expor a senha; falha de releitura impede falso sucesso. |
| Gravação atômica | As duas seções são validadas antes da gravação, e o arquivo protegido é substituído de forma atômica. |
| Histórico curto | Uma resposta inicial de 108 candles solicita intervalo maior e entra em repetição automática sem reduzir o mínimo de 200. |
| Conta Demo | Modo automático continua disponível após armar a execução. |
| Conta Real | Automático é convertido em execução sob comando; uma segunda trava impede passagem direta pelo motor. |
| SL/TP adaptativos | ATR, pivôs, estrutura, zonas opostas e R:R mínimo geram plano simétrico de compra/venda. |
| Plano inviável | A entrada é recusada quando suporte/resistência não deixa espaço para o retorno mínimo. |
| Meta e stop | P/L realizado do dia bloqueia novas ordens ao atingir os limites configurados. |
| Losses consecutivos | Duas perdas encerradas seguidas bloqueiam nova entrada; win/draw encerra a sequência; zero desativa a trava. |
| Separação de risco | Meta, stop e quantidade de losses ficam independentes em Real e Demo. |
| Diário | Posições e deals do PRIME TRADER são reconciliados com o MT5 e mantidos por conta. |
| Versão Windows | Pacote Python, executável e instalador usam a versão 1.3.3 de forma consistente. |

## Interpretação correta

A meta diária funciona somente como circuito de parada. O programa não pode prometer alcançá-la e não cria uma entrada quando a estrutura ou o R:R são inadequados. Depois de uma trava diária, os sinais continuam aparecendo para auditoria, mas nenhuma nova ordem é enviada pelo PRIME TRADER.

O resultado válido da conta vem dos deals realizados no MT5. Resultado flutuante não é contado como lucro/prejuízo encerrado e não fecha antecipadamente uma posição que já possui SL/TP.

## Empacotamento pendente

`build_windows.ps1` repetirá os testes, validará Tkinter, criará `PrimeAITrader.exe` e compilará `PrimeTrader-Setup-x64.exe`. Este relatório não declara o instalador aprovado até o runner Windows concluir com sucesso.

Identificador do candidato: `1.3.3`.
