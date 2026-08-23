# Prime AI Trader — correção por mercado

Este repositório documenta e testa a correção aplicada sobre o executável
`PrimeAITrader.exe` versão 0.9.0 enviado pelo proprietário.

O ZIP recebido continha somente o aplicativo já compilado, sem os arquivos
`.py`, `requirements.txt` e `tests` citados na documentação interna. O motor
original foi recuperado do pacote PyInstaller como bytecode Python 3.12 e é
preservado sem alterações. O overlay revisável deste repositório adiciona uma
última etapa determinística de confirmação antes de exibir uma entrada.

## Mudanças

- Criptomoedas e Forex usam políticas diferentes.
- O modo **CONFIRMAÇÃO**, inclusive com sensibilidade rápida, nunca confirma
  entrada usando uma vela ainda aberta.
- Cripto exige volume relativo real; Forex não reutiliza volume de cripto.
- Entrada contra a tendência principal exige duas velas, cruzamento de EMAs,
  força DI/MACD e quebra estrutural. Um pullback isolado não vira reversão.
- Vela dominada por pavio, fechamento no lado errado, preço esticado e baixa
  força direcional resultam em `AGUARDAR`.
- Limites de score e probabilidade são independentes por mercado.

## Testar

Os testes pressupõem o pacote recuperado do aplicativo no `PYTHONPATH`:

```powershell
python -m unittest discover -s tests -v
```

## Aplicar sobre a versão 0.9.0

Use exatamente Python 3.12:

```powershell
py -3.12 tools\patch_prime_ai_trader.py `
  "C:\caminho\PrimeAITrader.exe" `
  "C:\caminho\PrimeAITrader-market-aware.exe"
```

O patch mantém todos os componentes originais e injeta apenas
`signals/market_guard.py` e o adaptador `signals/engine.py`.

## Gerar o instalador Windows x64

Depois de criar o executável corrigido, gere um setup compacto com:

```powershell
py -3.12 tools\build_market_aware_setup.py `
  "PrimeAITrader-market-aware.exe" `
  "PrimeAITrader-Setup-x64-v0.9.1-Market-Aware.exe"
```

O instalador reutiliza o runtime do próprio aplicativo, preserva configurações
existentes durante a atualização, cria atalhos e registra o desinstalador no
perfil do usuário. A geração só termina se o setup conseguir reconstruir um
executável idêntico ao aplicativo corrigido.

## Limite importante

Este filtro reduz entradas frágeis, mas não promete lucro ou taxa fixa de
acerto. A nova versão deve permanecer em conta demo até completar pelo menos
200 operações de validação separadas para Cripto e 200 para Forex.
