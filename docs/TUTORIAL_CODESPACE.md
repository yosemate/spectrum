# Tutorial de teste no Codespace

Roteiro para validar a interface da versão 4.16.2: minimalismo com botões neutros e painéis translúcidos, tema Noturno (roxo e dourado), tema Claro (verdes), fontes Inter e Dropline, logo ao lado do nome, teclado automático, conexão com o ESP32, Configurações em duas seções, legibilidade e responsividade.

> **Importante.** A interface foi escrita sem poder abrir o PyQt5 no ambiente do assistente. A lógica pura tem testes automáticos que passam, mas **a aparência e o toque ainda não foram vistos em execução**. É isso que este roteiro verifica.

## 1. Criar o Codespace

1. No GitHub, abra o repositório **`indiolibanes/spectrum-web`** (onde a branch desta fase está publicada; depois do merge no `yosemate/spectrum`, use ele).
2. Troque a branch para **`feat/ux-acessibilidade-animacoes`** (a interface desta fase: Configurações separadas, contraste maior no escuro, layout responsivo, botões e animações novos).
3. **Code → Codespaces → Create codespace on feat/ux-acessibilidade-animacoes**.
4. Aguarde o VS Code (web) abrir. Confira, no canto inferior esquerdo, que a branch é a certa.

Já tem um Codespace antigo? Abra o terminal e rode `git fetch && git checkout feat/ux-acessibilidade-animacoes && git pull`.

## 2. Instalar dependências (uma vez por Codespace)

```bash
bash run/setup.sh
```

No fim deve aparecer `PyQt5 OK`. As fontes (Arena, Dropline e IBM Plex) e os cursores já vêm no repositório; não há nada a instalar para eles.

## 3. Conferir o ambiente (novo)

```bash
bash run/check.sh
```

O script lista com ✔ e ✘ o que está pronto: branch, arquivos novos, ferramentas, bibliotecas Python, display e portas. **Se algo falhar daqui em diante, copie a saída inteira dele.** Neste ponto é normal aparecer "display parado" e "portas sem serviço": eles sobem no passo 5.

## 4. Rodar os testes automáticos (sem janela)

Na raiz do repositório:

```bash
python3 -I tests/test_typography.py
python3 -I tests/test_glass.py
python3 -I tests/test_analysis_messages.py
python3 -I tests/test_animation_math.py
python3 -I tests/test_responsive_math.py
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_gui_smoke -v
```

Esperado: os seis primeiros terminam com `OK` (há também `python3 -I tests/test_glass.py`, que confere a translucidez, os botões neutros e os contrastes). O último abre widgets de verdade em modo invisível e confere: fontes registradas (e só nos estilos Regular/Bold), os cursores de fibra, só dois temas, textura pintada em ambos, painéis de vidro realmente translúcidos, indicador desenhado em todos os estados, efeito nos botões (e que ele respeita *Reduzir animações*), brilho em botão desabilitado, o teclado numérico digitando `192.168.4.1`, as **Configurações** só com a seção de tema, ícones e rostos coloridos, uma cor por barra do gráfico, os links do rodapé, o cartão de calibração sem texto comprimido e o canvas adaptativo sem cortar o layout.

| Se falhar… | Significa |
|---|---|
| `test_embedded_fonts_are_registered` | as fontes não carregaram: confira a pasta `assets/fonts/` |
| `test_font_styles_are_regular_and_bold_only` | o Qt registrou um estilo inesperado de fonte; copie a mensagem (ela lista qual) |
| `test_cursor_images_load` ou `test_buttons_and_windows_get_the_cellulose_cursor` | os PNG de `assets/cursors/` não carregaram ou o cursor não foi instalado |
| `test_panels_are_translucent_over_the_background` | o painel está opaco: o fundo não aparece por trás dele |
| `test_canvas_has_no_texture_in_both_themes` | a textura de celulose voltou a aparecer |
| `test_double_click_opens_and_outside_click_closes` | o teclado não abriu com duplo clique ou não recolheu com clique fora |
| `test_numeric_keyboard_types_an_ip_address` | o teclado não está entregando as teclas ao campo |
| Qualquer outro | copie a saída completa e envie |

## 5. Subir o display e abrir no navegador

```bash
bash run/start_display.sh
```

O script confere as ferramentas, espera as portas subirem e **imprime o endereço pronto** (algo como `https://<seu-codespace>-6080.app.github.dev/vnc.html?autoconnect=1&resize=scale`). Abra-o **no navegador em que você está logado no GitHub**. Você verá uma área de trabalho vazia.

Não torne a porta 6080 *Public*: a área de trabalho virtual não tem senha. Mantenha *Private*.

Depois, em outro terminal (ou no mesmo):

```bash
bash run/start_app.sh
```

Isso sobe o ESP32 simulado (porta 8080) e abre o supervisório. Se o display não estiver de pé, ele sobe sozinho. Na primeira execução, o login pede **CRIAR ADMINISTRADOR INICIAL**: use um usuário de teste e senha com 8 ou mais caracteres. Para encerrar tudo: `bash run/stop.sh`.

## 6. Roteiro de teste

Marque **OK** ou descreva o problema. Prints ajudam muito.

### A. Aparência

| # | Passo | Esperado | |
|---|---|---|---|
| A1 | Observe a abertura | Marca "SpectrumLab Pro", "Da luz" e "à análise." em Dropline (ou Arena na marca); fundo quase preto liso, logos SENAI e ARAUCO; assinatura no canto inferior direito | ☐ |
| A2 | Janela principal (Noturno) | Fundo roxo muito escuro com **brilhos roxos e dourados** suaves; painéis **translúcidos** (o brilho aparece por trás); destaques em **ouro**; **sem** textura | ☐ |
| A3 | Títulos, marca e números | **Logo do projeto ao lado** de "SpectrumLab Pro" (fonte Arena); "Ensaios automáticos", "Calibração" e o título do indicador em **Dropline**; rótulos e botões em **Inter**; valores e o número Kappa em Mono | ☐ |
| A4 | **Configurações** → seção **Aparência** → tema **Claro** | Troca na hora, com uma fusão suave, para branco e verde, também liso; nenhum trecho "esquecido" na cor antiga | ☐ |
| A5 | Volte para **Noturno · roxo e dourado** | A lista tem só dois temas | ☐ |
| A6 | Feche e abra o programa | Lembra o último tema escolhido | ☐ |
| A7 | Rodapé | Mais baixo que antes; logos SENAI e ARAUCO **menores** (cerca de 20 px de altura); à direita: "Protótipo desenvolvido por **Davi Baracat**, **Kauê Alencar** e **Mateus Ferreira**", os três como links | ☐ |
| A7b | Clique nos três nomes | Abrem `github.com/DaviBaracat`, `github.com/indiolibanes` e `github.com/yosemate` | ☐ |
| A8 | Abra qualquer diálogo (login, calibração) | Mesmas cores e fontes do painel principal; botões lisos com cantos de 10 px | ☐ |
| A9 | Compare com `docs/img/especime-noturno.png`, `especime-claro.png` e `especime-config-*.png` | Proporções, cores e hierarquia parecidas (o espécime não tem a renderização do Qt) | ☐ |
| A10 | Olhe os quatro indicadores | **Menores** que antes (altura ~90 px), valores ainda bem legíveis | ☐ |
| A11 | Olhe os cartões **ESP32 · Comunicação** e **GY-AS7263 · Sensor espectral** | Borda roxo lilás, rótulos em 14 px e valores em 16 px negrito: são os dados mais visíveis depois do gráfico | ☐ |

### A2. Configurações, legibilidade e cores

| # | Passo | Esperado | |
|---|---|---|---|
| S1 | Abra **Configurações** | Uma seção, **Aparência**, com dois botões (Noturno e Claro). Não há opções de teclado nem de animações | ☐ |
| S2 | Em **Animações**, escolha **Reduzidas** | Daqui em diante: sem entrada escalonada, sem fusão na troca de tema, botões só trocam de estado. Volte para **Completas** | ☐ |
| L1 | No tema Noturno, leia rótulos, valores, legendas do gráfico e o cartão **Calibração** | Texto claro e nítido, nada comprimido; R², RMSE e N em linhas (rótulo à esquerda, valor à direita); nenhum texto menor que 12 px | ☐ |
| L2 | Role a **coluna da esquerda** (método, ensaios, calibração, resultado) | Rola inteira; os cartões não encolhem para caber | ☐ |
| L3 | Olhe os botões no tema Noturno | **Todos iguais**: véu cinza-roxo translúcido, cantos de 12 px, sem cor por função. **Realizar leitura** é o único preenchimento sólido (quase branco), com borda dourada. Só **Parada de emergência** é vermelha | ☐ |
| L3b | Passe o mouse sobre um botão | O véu fica um pouco mais forte e a borda ganha o dourado | ☐ |
| L4 | Olhe o gráfico de barras | Uma cor por banda (azul, laranja, verde, âmbar, rosa, violeta), rótulos em cor de texto com uma tarja da cor da banda; curva clara com um ponto colorido por banda | ☐ |
| L5 | Ícones dos indicadores | Raio dourado, tendência roxa, folha verde, gota azul, cada um com um filete da mesma cor | ☐ |
| L6 | Confira simetria | Margens iguais entre cartões (cerca de 16 px), cartões alinhados nas bordas, rodapé na largura total | ☐ |

### B. Botões

| # | Passo | Esperado | |
|---|---|---|---|
| B1 | Passe o mouse sobre **Leitura com repetibilidade** | Borda realçada e leve clareamento, sem piscar | ☐ |
| B1b | Olhe qualquer botão de perto | Véu translúcido sem degradê nem fio de luz, cantos de 12 px, sem texto cortado | ☐ |
| B1c | Mova o mouse sobre um botão | **Sem** foco de luz seguindo o ponteiro (foi removido de propósito) | ☐ |
| B2 | Mantenha o botão pressionado | Ele "cede" com mola e escurece de leve, como um botão do iOS; **sem** onda | ☐ |
| B2b | Solte o botão | Volta com leve ultrapassagem (efeito de mola) e um anel que se dissipa; o tamanho do botão **não** muda | ☐ |
| B3 | Olhe **Realizar leitura** | Cor cheia e lisa (roxo no noturno, verde no claro), texto em Inter negrito | ☐ |
| B4 | Com a bancada desconectada | Botões de ensaio cinza, sem efeito ao passar o mouse | ☐ |

### B2. Cursor de fibra de celulose

| # | Passo | Esperado | |
|---|---|---|---|
| K1 | Mova o mouse sobre o fundo e os painéis | Seta cor de papel com fibras soltas na cauda, legível sobre o preto | ☐ |
| K2 | Passe sobre um botão | A seta fica na cor de destaque | ☐ |
| K3 | Passe sobre o campo de IP | Cursor "I" comum, para digitar | ☐ |
| K4 | Abra um diálogo | O cursor de fibra continua | ☐ |

No noVNC, se aparecer só um ponto em vez da seta, abra o painel lateral do noVNC → *Settings* e desligue *Show Dot when No Cursor*; se ainda assim vier a seta do sistema, anote: é limite da transmissão do cursor pelo VNC, não do programa. Para comparar, rode `SPECTRUM_SYSTEM_CURSOR=1 bash run/start_app.sh`.

### C. Teclado na tela (touch)

Escolha **Conexão → Wi-Fi** no cabeçalho para mostrar os campos de IP e porta.

**Antes de tudo, o teclado não abre sozinho.** Ele só aparece com duplo clique em um campo de texto, em qualquer computador ou celular.

| # | Passo | Esperado | |
|---|---|---|---|
| C0 | Inicie o programa e rode **Realizar leitura** com o teclado em **Automático** | O teclado **não** abre em nenhum momento (nem ao iniciar a análise) | ☐ |
| C0b | **Configurações** → Teclado na tela | Três opções: Automático, Sempre, Nunca. Embaixo: "Neste aparelho: nenhuma tela de toque detectada" (no Codespace) | ☐ |
| C0c | Dê **duplo clique** em um campo de texto | O teclado abre perto do campo; um clique fora dele o recolhe; arrastar pelo título o move | ☐ |
| C1 | Modo **Sempre**; clique no campo **IP ESP32** | Teclado numérico **menor**, no **canto superior esquerdo** da janela; o cursor continua piscando no campo | ☐ |
| C2 | Digite `127.0.0.1` | Aparece no campo; a tecla pressionada fica em destaque | ☐ |
| C3 | Teste **Apagar** (segure), **‹ ›** e **Limpar** | Apaga repetindo, move o cursor e esvazia o campo | ☐ |
| C4 | Toque em **Concluir** | O teclado fecha e o valor fica | ☐ |
| C5 | Clique em **Porta** | Teclado só de dígitos (sem ponto). Digite `8080` | ☐ |
| C6 | Abra o login e clique em usuário e senha | Teclado completo (também menor, no canto superior esquerdo); teste **Maiús.**, **123** e **Acentos** (á, ã, ç) | ☐ |
| C7 | Modo **Nunca** | Ao clicar num campo, não abre teclado. Volte para **Automático** | ☐ |
| C8 | Com o teclado aberto, clique em **Fechar** | Fecha; clicar de novo no campo reabre | ☐ |
| C9 | Se o teclado cobrir o campo em edição (campo no canto superior esquerdo) | Ele se desloca para baixo ou para o lado do campo | ☐ |

Observação: no noVNC o toque do navegador chega ao programa como clique de mouse, e é por isso que o teclado abre ao clicar. Em um touchscreen de verdade o comportamento é o mesmo.

### D. Análise da amostra (com o simulador)

Conecte: Wi-Fi, IP `127.0.0.1`, porta `8080`, **Conectar ESP32**.

| # | Passo | Esperado | |
|---|---|---|---|
| D1 | Antes de iniciar | Abaixo do gráfico, rosto sorrindo e "Pronto para a próxima amostra." (pisca de vez em quando) | ☐ |
| D2 | Calibrar · Branco e escuro (confirme os pop-ups) | Título "Calibração · padrão branco" e depois "referência escura"; etapas 1 a 5 avançando | ☐ |
| D3 | **Realizar leitura** | O botão vira **Analisando…** com uma faixa suave percorrendo; o indicador mostra etapas e frases que trocam a cada ~4,5 s | ☐ |
| D4 | Durante a leitura do espectro | Curva animada no indicador (etapa 3 de 5) | ☐ |
| D5 | Fim do ciclo | "Análise concluída. Boa amostra!", rosto **amarelo** com pulinho e faíscas coloridas por ~7 s; o botão volta a **Realizar leitura** | ☐ |
| D6 | Ensaio de repetibilidade | Título "Leitura com repetibilidade"; entre as leituras, "Aguardando a próxima leitura…" | ☐ |
| D7 | Parada de emergência durante um ciclo | Rosto laranja preocupado (com gota) e mensagem de emergência, sem sorriso | ☐ |
| D9 | Antes de conectar (ou depois de **Desconectar**) | O indicador mostra "ESP32 desconectado", **não** "Pronto para a próxima amostra" | ☐ |
| D8 | Ao iniciar o programa e ao rodar a leitura | Painéis entram em sequência com subida suave; as barras do gráfico sobem com mola | ☐ |

### E. Responsividade

Repita A2, C1 e D3 em cada configuração (veja `run/README.md`, seção 7):

| Teste | Como | Esperado |
|---|---|---|
| 1920×1080 | `RESOLUTION=1920x1080 bash run/start_display.sh` + `bash run/start_app.sh` | Cabeçalho em **uma** linha, indicadores em **4 colunas**, painéis lado a lado; sem cortes |
| 125% | `QT_SCALE_FACTOR=1.25 bash run/start_app.sh` | Idem |
| 1366×768 | `RESOLUTION=1366x768 bash run/start_display.sh` + `bash run/start_app.sh` | Cabeçalho em **duas** linhas (campos na primeira, ações na segunda); texto do mesmo tamanho, sem compressão; teclado cabe na tela |
| 1024×768 e 800×1280 (vertical) | `RESOLUTION=1024x768 ...` e `RESOLUTION=800x1280 ...` | Indicadores em grade 2×2; painel do gráfico **embaixo** do painel de ensaios (empilhados); a janela inteira rola se preciso, o texto continua legível |
| Arrastar a borda da janela | Redimensione com o mouse | O layout se reorganiza nos pontos de quebra, sem saltos nem texto cortado |

### F. Conexão com o ESP32 (correção da 4.16.2)

Na versão anterior, ao clicar em **Conectar**, a tela dizia "pronto" mas o estado ficava "Desconectado". **A causa não pôde ser confirmada sem o PyQt5 real e sem o hardware**; a 4.16.2 aplica correções de diagnóstico, e este bloco existe para fechar o caso.

| # | Passo | Esperado | |
|---|---|---|---|
| N1 | Com o simulador de pé (`start_app.sh` o sobe), Wi-Fi, IP `127.0.0.1`, porta `8080`, **Conectar ESP32** | O botão mostra **Conectando…** por instantes e depois vira **Desconectar**; o selo do cabeçalho e o cartão **ESP32 · Comunicação** mostram **Conectado** e *Protocolo: 2 · confirmado* | ☐ |
| N2 | Cartão **ESP32 · Comunicação** | "Heartbeat: Última resposta: X s" com X pequeno e renovando | ☐ |
| N3 | Pare o simulador (`bash run/stop.sh` ou encerre `fake_esp32.py`) e tente conectar | Aparece a janela **Falha na conexão** com o motivo e dicas (Wi-Fi/USB); o status diz "Falha ao conectar" e o indicador mostra "ESP32 desconectado" | ☐ |
| N4 | Conecte com IP errado (ex.: `10.255.255.1`) | Em até ~4 s aparece a janela de falha (tempo-limite), sem travar a janela | ☐ |
| N5 | Se N1 falhar | Copie: a mensagem da janela de falha, o final do terminal do `start_app.sh` e o conteúdo do Console de telemetria (rodapé) | ☐ |

Com o ESP32 real: confirme que o celular/PC está na rede do ESP32, o IP é o impresso no monitor serial do ESP32 e a porta é a mesma do firmware.

## 7. O que enviar de volta

1. A saída do passo 3 (`bash run/check.sh`) e do passo 4 (testes), em texto.
2. A tabela do passo 6 com OK/problema em cada linha.
3. Prints dos itens com problema (use a captura do navegador).
4. Se o programa fechar com erro: o final do terminal do `start_app.sh`.

## 8. Encerrar

```bash
bash run/stop.sh
```

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Fonte parecendo a padrão do sistema | Rode os testes de fontes do passo 4. Se passarem, o problema é só visual do noVNC |
| O teclado não abre | Use **duplo clique** no campo (um clique só posiciona o cursor). O campo não pode ser somente leitura |
| O teclado abre mas o cursor some do campo | Anote o gerenciador de janelas em uso (`start_display.sh` usa o fluxbox) e envie |
| O teclado cobre o campo | Envie um print com a resolução usada |
| Faixa do botão "Analisando…" não aparece | Pode ser limite de desempenho do display virtual; compare no Windows |
| Tela preta no noVNC | `bash run/start_app.sh` ainda não foi executado |
| Página do noVNC não abre (erro 502, 404 ou "não foi possível acessar") | Rode `bash run/check.sh`: ele mostra se a porta 6080 está de pé. Espere 10 s e atualize; abra o endereço impresso por `start_display.sh` **no navegador logado no GitHub**; na aba **PORTS**, a 6080 deve aparecer (Private) |
| `bash: run/start_display.sh: cannot execute` ou `\r: command not found` | Fim de linha do Windows: `sed -i 's/\r$//' run/*.sh` |
| O Codespace mostra a interface antiga (cores por botão, Inter) | Está na branch errada: `git fetch && git checkout feat/ux-acessibilidade-animacoes && git pull` |
| `could not load xcb` | `bash run/setup.sh` de novo |
