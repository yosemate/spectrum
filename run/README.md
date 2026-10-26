# Executar o SPECTRUM-LAB PRO no Codespace

Roteiro para rodar o supervisório num navegador, com display virtual e uma bancada simulada (ESP32 falso).
**Limitações:** não há hardware real e a escala de DPI do Windows não é reproduzida fielmente. As fontes (Arena, Dropline e IBM Plex) vão embutidas no programa, então a tipografia é a mesma do Windows. Serve para validar layout, fluxo e comunicação, não para medir a bancada.

> Para testar a interface nova (temas, Configurações, botões e animações, gráficos, indicador de análise e teclado na tela), use o roteiro completo em [docs/TUTORIAL_CODESPACE.md](../docs/TUTORIAL_CODESPACE.md). Este arquivo cobre só a parte de execução e responsividade.

## 1. Criar o Codespace

1. No GitHub, abra o repositório `indiolibanes/spectrum-web` (ou o `yosemate/spectrum`, depois do merge desta branch).
2. Troque a branch para `feat/ux-acessibilidade-animacoes` (interface desta fase, já com os scripts de `run/`).
3. Clique em **Code → Codespaces → Create codespace on** a branch escolhida.
4. Aguarde o VS Code (web) abrir.

## 2. Instalar dependências (uma vez por Codespace)

No terminal do Codespace:

```bash
bash run/setup.sh
```

Ao final deve aparecer `PyQt5 OK`. Se houver erro de pacote, copie a mensagem e envie.

Para conferir tudo de uma vez (branch, arquivos, ferramentas, display e portas), use a qualquer momento:

```bash
bash run/check.sh
```

## 3. Subir o display virtual

```bash
bash run/start_display.sh
```

O padrão é **1920x1080**. Para testar outra resolução:

```bash
RESOLUTION=1366x768 bash run/start_display.sh
```

O script confere as ferramentas, espera as portas subirem e imprime o endereço pronto para abrir (no Codespaces, algo como `https://<codespace>-6080.app.github.dev/vnc.html?autoconnect=1&resize=scale`). Abra-o no navegador em que você está logado no GitHub. Você verá uma área de trabalho vazia.

Mantenha a porta 6080 como **Private**: a área de trabalho virtual não tem senha, e o x11vnc só aceita conexões locais (`-localhost`), então só o noVNC alcança a tela.

## 4. Iniciar o programa

Em um terminal (pode ser o mesmo, o display continua rodando em segundo plano):

```bash
bash run/start_app.sh
```

Isso sobe o ESP32 simulado na porta 8080 e abre o supervisório na área de trabalho do noVNC. O log da bancada simulada fica em `run-data/esp32_simulado.log`.

## 5. Conectar ao ESP32 simulado

No supervisório:

| Campo | Valor |
|---|---|
| Conexão | **Wi-Fi** |
| IP | **127.0.0.1** |
| Porta | **8080** |

Clique em **Conectar ESP32**. A aplicação deve mostrar a bancada conectada (`STATUS:PROTOCOLO_2`).

## 6. Primeiro acesso

Como `run-data/` começa vazio, o login mostra **CRIAR ADMINISTRADOR INICIAL**. Preencha usuário, senha (mínimo 8 caracteres) e confirmação. Esse usuário é só para teste.

## 7. Testes de responsividade

Reinicie o programa a cada troca de resolução ou escala (`Ctrl+C` no terminal do `start_app.sh` e rode de novo).

| Teste | Comando | Equivale a |
|---|---|---|
| A. Resolução de referência | `RESOLUTION=1920x1080 bash run/start_display.sh` + `bash run/start_app.sh` | 1920x1080 em 100% |
| B. Escala 125% | `QT_SCALE_FACTOR=1.25 bash run/start_app.sh` (display 1920x1080) | 1536x864 lógicos |
| C. Notebook comum | `RESOLUTION=1366x768 bash run/start_display.sh` + `bash run/start_app.sh` | 1366x768 em 100% |
| D. Tela vertical | `RESOLUTION=800x1280 bash run/start_display.sh` + `bash run/start_app.sh` | Tablet em retrato |

Para o teste B, use `QT_SCALE_FACTOR=1.25 bash run/start_app.sh`. Os demais, sem essa variável. Redimensionar a janela com o mouse também vale: o layout se adapta ao tamanho real, sem escala fixa.

### Checklist por tela

Anote **OK** ou o problema em cada item:

- [ ] Nenhum texto cortado nem sobreposto.
- [ ] Textos com pelo menos 12 px e sem compressão (inclusive no cartão de calibração, no tema escuro).
- [ ] Os KPIs ficam em 4 colunas em telas largas e em grade 2×2 em telas estreitas ou verticais.
- [ ] O cabeçalho passa para duas linhas abaixo de ~1590 px lógicos e os painéis se empilham em tela vertical.
- [ ] Botões de ação visíveis (a coluna da esquerda rola; nada é espremido para caber).
- [ ] Diálogos (login, calibração, configurações) cabem na tela.
- [ ] Logo do cabeçalho visível e alinhado ao título.
- [ ] Barras de rolagem aparecem onde devem, não em toda parte.
- [ ] Fundo texturizado não atrapalha a leitura do texto.
- [ ] Campos de IP e porta cabem no cabeçalho sem cortar os botões ao lado.

Tire um print da tela (botão **Print Screen** ou ferramenta de captura do navegador) de cada resolução com problema e envie junto com o número do item.

## 8. Encerrar

```bash
bash run/stop.sh
```

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `could not connect to display :99` | display não subiu | rode `bash run/start_display.sh` de novo (ele mostra o log do que falhou) |
| Página do noVNC não abre | porta 6080 ainda subindo ou branch errada | `bash run/check.sh`; espere 10 s e atualize |
| Tela preta no noVNC | `start_app.sh` ainda não foi executado | execute `bash run/start_app.sh` |
| `qt.qpa.plugin: could not load xcb` | biblioteca faltando | rode `bash run/setup.sh` de novo |
| "Falha ao conectar" no supervisório | simulador não está ativo ou porta errada | confira IP `127.0.0.1` e porta `8080` |
| Porta 8080 já em uso | simulador antigo ainda rodando | `pkill -f fake_esp32.py` e repita o passo 4 |

## O que o simulador responde

`run/fake_esp32.py` atende os comandos do firmware real: `CMD:PING` (com os protocolos de porta, carrinho, manual e admin, sem os quais a leitura fica bloqueada), `CMD:ESTADO_PORTA`, `CMD:DIAG_SENSOR` (ESPDIAG), `CMD:ADMIN_CARCACA`, movimentos de gaveta, porta e sensor, `CMD:LER_ESPECTRO` (6 canais, 610 a 860 nm), `CMD:LER_ESCURO`, `CMD:EMERGENCIA` e `CMD:MANUAL:<cmd>`. Quando o IP é `127.0.0.1`, o supervisório mostra o selo **SIMULAÇÃO**: os dados são de teste. Ele não simula ruído, falhas nem tempos reais de motor.

## Windows e Linux: instalação comum

Use Python 3.11 ou 3.12. As dependências de execução estão em `requirements.txt`;
para gerar executáveis, instale `requirements-build.txt` na plataforma de destino.
No Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

No Codespaces, atualize a branch e execute:

```bash
bash run/setup.sh
bash run/start_app.sh
```

Abra o endereço impresso (porta 6080, Private). O script usa `.venv/bin/python`,
testa o plugin Qt/xcb e inicia o ESP32 simulado. Na interface selecione Wi-Fi,
IP `127.0.0.1`, porta `8080`. `bash run/check.sh` testa também a abertura do Qt;
em caso de falha consulte `run-data/qt.log` e `run-data/app.log`.
O noVNC exibe o desktop remoto; ele não emula o ESP32 nem encaminha automaticamente
o USB ou a rede Wi-Fi do seu computador para o Codespace. A bancada física pode ser
usada executando o programa localmente em Windows ou Linux, com USB acessível ou
uma rota TCP até o ESP32. No Linux, confirme a permissão de acesso a `/dev/ttyUSB*`
ou `/dev/ttyACM*` (grupo `dialout` nas distribuições Debian/Ubuntu).

O workflow `Windows and Linux runtime` valida Python 3.11/3.12 nas duas plataformas,
a janela real, o handshake e um scan por TCP. Um job adicional testa Xvfb + xcb e
HTTP do noVNC em Linux. Não substitui a validação física dos motores e do sensor.

Por padrão, noVNC escuta somente em 127.0.0.1. No Codespaces mantenha a porta 6080 privada; qualquer alteração de NOVNC_BIND exige definir a proteção de acesso da implantação.
