# PRIME AI TRADER

Build automático da versão 0.9.0 para Windows x64 configurado no GitHub Actions.

Assistente quantitativo desktop para análise de criptomoedas e Forex. O aplicativo gera cenários de **COMPRA**, **VENDA** ou **AGUARDAR**, mas **não envia ordens** a corretoras.

## Destaques da versão 0.9.0

- Motor estrutural profissional reconhece continuidade de tendência (BOS), mudança de caráter/tendência (CHOCH), pullback confirmado, correções profundas, exaustão e lateralização.
- Divergências regulares e ocultas de RSI/MACD, rejeições, varreduras de liquidez e distância real até suporte/resistência qualificam os sinais.
- Leitura estrutural disponível em rápido, equilibrado e conservador; modos price action, confirmação e quantitativo; gráficos 1m, 3m, 5m, 15m, 30m, 1h e 4h.
- Quando o preço real da VEX está visível, ele atualiza a vela atual do gráfico sem inventar candles antigos, volume, preço OTC ou confirmação de fechamento.
- Reanálise incremental ajustada ao timeframe e à sensibilidade, evitando espera fixa desnecessária e mantendo a interface responsiva.
- Doze features causais de pullback, rompimento, divergência, compressão, liquidez e reversão alimentam os modelos; após atualizar, clique em **TREINAR IA** no ativo/timeframe escolhido.
- Backtest reforçado contra preço esticado, tendência oposta, compressão sem rompimento e pressão contrária de reversão, preservando a validação walk-forward.
- Novo botão **CONECTAR VEX INVEST**: abre o traderoom em perfil dedicado do Chrome/Edge; o usuário entra diretamente no navegador e não informa senha ao robô.
- Sincroniza automaticamente ativo, mercado, payout, expiração e tempo restante quando esses campos estão visíveis no traderoom da VEX.
- Compara o preço visível da VEX com a fonte pública e explica divergências reais; ativos OTC não são tratados como se fossem cotações públicas.
- Corrige o cronômetro que reiniciava em atualizações do gráfico/notícias: usa o relógio visível da VEX ou o horário original do sinal.
- Confirmações equilibradas/conservadoras verificam direção do timeframe superior, fechamento da vela e categorias independentes de confluência.
- Sem modelo treinado, a interface mostra força técnica real em vez de apresentar pontuação de regras como probabilidade calibrada da IA.
- Mantém a interface aprovada da versão 0.7.0, o cartão de voz compacto da 0.7.2 e os padrões equilibrado/confirmação.
- Alto-falante e onda de áudio compactos liberam espaço para a explicação da IA e os últimos sinais; sensibilidade equilibrada e modo confirmação continuam intactos.
- Nova interface PRIME AI TRADER baseada no painel premium solicitado: fundo preto profundo, cabeçalho com status, ações coloridas e três colunas organizadas.
- Gráfico ampliado com atalhos de timeframe, cards compactos de indicadores e preservação integral das ferramentas de desenho/análise.
- Painel de sinal com direção destacada, confiança, barra de score, entrada, expiração, cronômetro e motivos reais da análise.
- Faixa inferior com explicação contextual da IA, últimos sinais reais do banco de dados e status visual dos alertas de voz.
- Configurações avançadas recolhíveis preservam pagamento, controle de risco, APIs, radar, backtest, treinamento, limpeza e monitor de saúde.
- Provedores, estratégias, sinais, análise, notícias, áudio e atualização Forex da versão anterior permanecem inalterados.
- Forex com cotação pública real consultada a cada 10 segundos e atualização incremental da última vela, sem consumir créditos do Twelve Data ou da Alpha Vantage.
- O histórico Forex continua sendo reconciliado automaticamente; fontes atrasadas são identificadas honestamente e não geram ticks ou volume inventados.
- Gráfico Forex com cinco casas decimais, três para pares em JPY, escala ampliada e remoção da área de volume quando a fonte não fornece volume real.
- Perfis calibrados de verdade: conservador exige alta confirmação; equilibrado mantém seletividade intermediária; rápido prioriza leitura imediata com duas confirmações.
- Score mínimo por perfil: conservador 86, equilibrado 73 e rápido 57; ADX, momentum, volatilidade, vantagem direcional e peso da IA também são independentes.
- O perfil rápido avisa a direção ainda durante a formação da vela, deixando claro que a confirmação final depende do fechamento.
- Com bloqueio automático desligado, notícias e eventos aparecem somente na tela: o robô não repete mais o aviso genérico de risco no áudio.
- Eventos realmente bloqueantes possuem intervalo de cinco minutos entre avisos iguais; sinais confirmados sempre têm prioridade.
- As 10 criptomoedas identificadas na plataforma aparecem primeiro: BTC, LTC, ADA, BNB, XRP, ETH, SOL, DOGE, SUI e XLM/Stellar.
- Binance com hosts públicos oficiais alternativos e fallback automático para Coinbase Exchange e Kraken.
- Forex público sem chave, com Twelve Data e Alpha Vantage opcionais; Frankfurter fornece referência diária sem simular candles intraday.
- Notícias visíveis no painel e atualizadas automaticamente por GDELT, Google Notícias, Cointelegraph, CoinDesk, FXStreet e ForexLive.
- Calendário econômico público sem chave, com cache de uma hora; Finnhub permanece opcional.
- Estratégias de pullback na EMA 21, rompimento/reteste, varredura de liquidez, rejeição, engolfo e confirmação do timeframe superior.
- Score técnico e score da IA aparecem separadamente; quando houver AGUARDAR, o motivo concreto é mostrado.
- Pagamento configurável da plataforma: cálculo de ponto de equilíbrio, expectativa e intervalo de confiança no backtest.
- Sinais confirmados durante o WebSocket são gravados; resultados vencidos alimentam corretamente a calibração real.
- Amostra de backtest em formação aparece como informação discreta, sem aviso amarelo e sem bloqueio.
- Correção do contexto do modelo: a IA treinada agora é carregada também na primeira análise completa.
- Comportamento fluido da v0.3.0 restaurado, mantendo as correções das versões posteriores.
- Mais histórico no treinamento e backtest (até 2.000 candles por contexto).
- Seleção de modelo pela precisão direcional seletiva com limite inferior de Wilson, cobertura mínima e validação walk-forward.
- Purga temporal entre treino e teste para evitar vazamento causado pelo horizonte do rótulo.
- Limites de sinais recalibrados para não reduzir o backtest a poucas operações; tendência, momentum, volatilidade extrema e preço excessivamente estendido continuam filtrados.
- Probabilidade mínima e vantagem mínima sobre o cenário oposto iguais no sinal ao vivo e no backtest.
- Calibração separada por mercado, ativo, timeframe, horizonte e modo; `DRAW` não entra na taxa de acerto.
- Notícias classificadas por palavras completas, correção de moedas de eventos Forex e expiração de bloqueios antigos.
- Threads de rede e cálculo não acessam mais o Tkinter diretamente; treinamento, backtest, desempenho e diagnósticos ficam fora da interface.
- Botões para atualizar o gráfico e limpar cache/modelos antigos com preservação de chaves, configurações e histórico.
- Radar Forex em lotes rotativos compatíveis com o limite da API gratuita.
- 31 criptomoedas iniciais, até 100 pares USDT líquidos e 28 pares de Forex.

## Recursos

- Interface nativa Tkinter; a conexão opcional com a VEX usa navegador local dedicado, perfil separado e comunicação restrita ao computador.
- Binance Spot REST/WebSocket, Coinbase Exchange e Kraken para criptomoedas, sem chave.
- Forex público sem chave, Twelve Data gratuita e Alpha Vantage gratuita opcional, com cache e controle de consumo.
- GDELT e feeds RSS para notícias sem chave; calendário econômico público e Finnhub opcional.
- Gráfico próprio de candles/volume com zoom, arraste, crosshair, EMAs, Bollinger, S/R e Fibonacci.
- EMA 9/21/50, RSI, MACD, Bollinger, Stochastic, ADX/+DI/-DI, ATR, VWAP, OBV, CCI, Williams %R, volume relativo e volatilidade histórica.
- Price Action com HH/HL/LH/LL, zonas, rompimento, falso rompimento e reteste.
- Quatro modelos locais leves, persistidos por ativo/timeframe/horizonte/schema.
- Radar, backtest fora da amostra, SQLite, desempenho observado, voz pt-BR e logs rotativos.
- Chaves protegidas pelo Windows DPAPI e nunca incluídas no código-fonte.

## Requisitos

- Windows 10/11 x64.
- 8 GB de RAM.
- Internet para dados ao vivo.
- Google Chrome ou Microsoft Edge para a sincronização opcional com a VEX Invest.
- Python 3.11–3.13 somente para executar o código-fonte; o instalador final inclui o runtime.

## APIs

| Fonte | Uso | Chave | Custo obrigatório |
|---|---|---|---|
| Binance Spot + espelhos oficiais | Criptomoedas e WebSocket | Não | Nenhum |
| Coinbase Exchange | Backup de criptomoedas em USD | Não | Nenhum |
| Kraken | Backup de criptomoedas em USD | Não | Nenhum |
| Yahoo Finance Forex público | Candles Forex e cotação pública a cada 10 segundos | Não | Nenhum |
| Frankfurter | Referência cambial diária, nunca intraday | Não | Nenhum |
| Twelve Data Basic | Forex principal opcional | Sim, gratuita | Nenhum |
| Alpha Vantage | Forex alternativo opcional | Sim, gratuita | Nenhum |
| GDELT + Google Notícias + RSS | Notícias cripto/Forex | Não | Nenhum |
| Calendário econômico público | Eventos de alto impacto | Não | Nenhum |
| Finnhub | Calendário extra | Opcional | Nenhum |

Por padrão, notícias, eventos e backtest fraco aparecem como avisos silenciosos na tela. O bloqueio automático de notícia/evento pode ser ativado no painel esquerdo; apenas um bloqueio realmente ativo pode gerar alerta de voz.

## Sincronizar com a VEX Invest

1. Abra o aplicativo e clique em **CONECTAR VEX INVEST**.
2. O Chrome ou Edge abrirá `https://vexinvest.com/traderoom` em um perfil separado.
3. Faça login normalmente somente nessa janela do navegador.
4. Selecione o ativo e a operação na VEX; o robô identifica os campos visíveis e atualiza payout, mercado, ativo, expiração e cronômetro.
5. Clique em **INICIAR ANÁLISE** e mantenha a janela dedicada da VEX aberta.

A integração não usa senha digitada no robô, não lê cookies, saldo ou campos privados, não envia ordens e não representa uma API oficial da plataforma. Se um campo não estiver visível, ele não é inventado. O histórico anterior dos candles continua vindo das APIs públicas; quando disponível, somente o preço real visível da VEX atualiza a vela em formação.

Após instalar uma versão com novo motor de análise, selecione o ativo, timeframe e expiração desejados e clique em **TREINAR IA**. Os modelos são separados por contexto e os modelos de versões anteriores não são apresentados incorretamente como compatíveis.

## Perfis de análise

| Perfil | Score mínimo | Confirmações | ADX mínimo | Comportamento |
|---|---:|---:|---:|---|
| CONSERVADOR | 86 | 5 | 20 | Alta confirmação e menos operações. |
| EQUILIBRADO | 73 | 4 | 15 | Frequência e confirmação intermediárias. |
| RÁPIDO | 57 | 2 | 10 | Leitura imediata, mais sinais e aviso antecipado durante a vela. |

Uma leitura rápida em formação não é apresentada como sinal já confirmado. Nenhum perfil promete taxa fixa de acerto.

## Executar pelo código-fonte

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

## Gerar o EXE e o instalador

Em Windows x64 com Python e Inno Setup 6:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

Saídas:

- `release\PrimeAITrader.exe`
- `release\PrimeAITrader-Setup-x64.exe`

## Testes

```powershell
python -m unittest discover -s tests -v
```

A versão 0.8.0 possui 174 testes automatizados de matemática, ausência de look-ahead, purga temporal, modelos, backtest, payout, perfis calibrados, sinais rápidos, prioridades do áudio, banco, feeds públicos, fallback, calendário, notícias, limpeza segura, reconexão, threads da interface, desempenho do gráfico e comandos dos botões, incluindo 37 cenários de sincronização segura com a VEX, seis verificações de confiabilidade Windows, cronômetro, divergências, OTC, confluências independentes e montagem real da interface em Windows.

## Dados locais

Em Windows, o programa grava em `%APPDATA%\PrimeAITrader`:

- `settings.json` — preferências sem segredos;
- `secrets.dat` — chaves protegidas por DPAPI;
- `prime_ai_trader.db` — sinais e resultados;
- `models\` — modelos e relatórios separados por contexto;
- `logs\app.log` — logs rotativos.
- `vex-browser\` — perfil opcional e separado do navegador usado para abrir a VEX.

## Limitações honestas

- Não executa ordens nem promete lucro ou taxa fixa de acerto.
- Os filtros mais rigorosos reduzem a quantidade de sinais; `AGUARDAR` é uma decisão válida.
- Cada ativo/timeframe/horizonte precisa de treinamento próprio para usar a IA.
- Twelve Data e Alpha Vantage exigem chaves gratuitas apenas se forem configuradas; o Forex público não exige chave, mas sua disponibilidade não é garantida.
- Frankfurter publica referência diária; ela nunca é apresentada como cotação intraday.
- O Forex é atualizado entre aproximadamente 60 e 120 segundos; o streaming contínuo é da Binance.
- Coinbase/Kraken podem usar par USD como referência para o ativo USDT; compare o preço com o da plataforma.
- Ativos OTC/sintéticos e preços internos de corretoras podem divergir das APIs públicas e não devem ser tratados como feeds equivalentes.
- A sincronização VEX depende de login realizado pelo próprio usuário, Chrome/Edge aberto e textos efetivamente visíveis; alterações no site podem exigir ajuste de compatibilidade.
- Backtest e desempenho passado não garantem resultado futuro.

Consulte `docs/STRATEGY.md` para a lógica dos filtros e os limites da validação.

## Aviso de risco

Este software é uma ferramenta de análise e educação. Criptomoedas e Forex envolvem risco elevado, inclusive perda integral do capital. Verifique os dados e faça sua própria gestão de risco antes de operar.
