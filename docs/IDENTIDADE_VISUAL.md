# Identidade visual — SPECTRUM-LAB PRO

Este documento define logos, cores, tipografia, superfícies, cursor e comportamento visual do programa, da documentação e do README. Vale para novas telas e ajustes futuros. A regra de estilo (superfícies planas, cor como informação) está em [`ISA-101.md`](ISA-101.md).

![Tema Noturno](img/especime-noturno.png)
![Tema Claro](img/especime-claro.png)

| Configurações · Noturno | Configurações · Claro |
|---|---|
| ![Configurações no tema Noturno](img/especime-config-noturno.png) | ![Configurações no tema Claro](img/especime-config-claro.png) |

> As imagens são um **espécime em HTML** gerado por `tools/especime.py` a partir das **mesmas paletas e receitas** do programa (`appearance.py` e `glass.py`). Servem para conferir hierarquia, contraste e proporção. **Não são capturas da tela real**: a renderização exata das fontes no Qt só se confirma com o programa aberto (`docs/TUTORIAL_CODESPACE.md`).

## Linguagem de design

Desde a 4.16.2 o programa é **minimalista e segue a ISA-101** (interfaces homem-máquina para automação de processos) com um acabamento inspirado no **iOS**:

- **Gráficos com cor**: uma cor por banda espectral, sempre na mesma ordem. A cor serve para dados.
- **Botões neutros**: todos com o mesmo véu translúcido e cantos contínuos de 12 px (estilo iOS). Não há cor por função nos botões. O botão principal é um preenchimento sólido neutro, com borda de ouro (noturno) ou verde (claro).
- **Ouro e roxo (noturno), verdes (claro)**: aparecem em foco, títulos, bordas de destaque e no fundo, nunca como preenchimento de botão.
- **Fundo e painéis translúcidos**: o fundo tem brilhos suaves (roxo e ouro no noturno; verdes no claro), e os painéis são translúcidos sobre eles. A profundidade vem da transparência.
- **Alarme**: vermelho e laranja são reservados a emergência e aviso. Nada mais os usa.
- **Movimento**: molas curtas e um véu ao pressionar, como no iOS. Sem ondulação de Material, sem reflexos e sem anel de luz.

A translucidez é uma exceção consciente à regra "superfícies lisas" da ISA-101: ela só aparece sobre brilhos de fundo, sem textura nem degradê nos controles. Veja [`ISA-101.md`](ISA-101.md).

**Por que não Jetpack Compose neste programa.** O Compose é uma biblioteca em Kotlin (Android e JVM) e não pode ser embutido em um aplicativo PyQt5. O caminho para Android é um cliente separado, que fale o mesmo protocolo TCP do ESP32 (comandos em `run/fake_esp32.py`), e fica para a última fase do roteiro: primeiro UX/UI, depois animações, por fim Android e talvez web.

## Logos

| Marca | Arquivo | Onde aparece |
|---|---|---|
| SPECTRUM-LAB PRO | `assets/logo/spectrumlab-mark.svg` | Ícone da janela, abertura e **ao lado do nome no cabeçalho** (40 px) |
| SENAI | `assets/brands/senai.svg` | Rodapé da janela (120 × 20 px) e abertura |
| ARAUCO \| Projeto Sucuriú | `assets/brands/arauco-sucuriu.svg` | Rodapé da janela (120 × 20 px) e abertura |
| ARAUCO (wordmark isolado) | `assets/brands/arauco.svg` | Reserva, para uso sem o projeto |

Regras de uso:

- Os SVGs não têm fundo. Use sobre fundo claro ou escuro, sem recolorir a marca.
- Tamanho mínimo: 20 px de altura na tela (logos do rodapé). Abaixo disso, a marca do programa substitui a composta.
- Deixe, em volta de cada logo, um espaço livre igual à altura da letra "a" do wordmark ARAUCO.
- Os logos SENAI e ARAUCO são de terceiros. O uso no executável e na documentação depende de autorização (auditoria, item B8).

## Assinatura

> Protótipo desenvolvido por Davi Baracat, Kauê Alencar e Mateus Ferreira

Aparece na abertura (canto inferior direito) e no **rodapé da janela principal**. Cada autor é um link para o seu GitHub: **Davi Baracat** → `github.com/DaviBaracat` (@DaviBaracat), **Kauê Alencar** → `github.com/indiolibanes` e **Mateus Ferreira** → `github.com/yosemate`. Os nomes e os links estão em `version.py` (`__authors__` e `__author_links__`; `credits_html()` monta o texto), em um só lugar. A cor do link é a cor de link da paleta do tema (destaque).

## Temas

Há dois temas, escolhidos em *Configurações → Aparência*; a escolha fica salva e a troca acontece em uma fusão suave de cerca de 360 ms. As *Configurações* não têm mais seção de acessibilidade: o teclado abre com duplo clique e as animações são sempre completas. Preferências antigas (`dark`, `gold`, `umber`) migram sozinhas para o tema Noturno.

### Noturno · roxo e dourado (padrão)

Roxo muito profundo no fundo, com brilhos roxos e dourados; painéis translúcidos; **ouro** como destaque de foco e identidade; **roxo lilás** como cor secundária (cartões de comunicação e sensor).

| Token | Hex | Uso |
|---|---|---|
| canvas | `#0A0614` | Fundo (roxo quase preto) |
| surface | `#1A1030` | Painéis, com 32% de opacidade |
| soft | `#2A1F4A` | Áreas alternadas |
| border | `#6A5A9A` | Divisores |
| text | `#FBF7EE` | Texto principal |
| heading | `#FFF1C4` | Títulos (ouro pálido) |
| muted | `#D9D0EE` | Texto secundário |
| accent | `#E8BE5C` | Ouro: foco, números de destaque, bordas de destaque |
| secondary | `#A88BFF` | Roxo lilás: cartões de comunicação e sensor |
| positive / warning / danger | `#8FD69B` / `#F4A259` / `#FF8A80` | Normal / aviso / alarme (reservadas) |
| sky / violet / rose | `#8CC8FF` / `#B7A0FF` / `#F2A7D0` | Matizes de barras e ícones |
| on_strong | `#0A0614` | Texto sobre o botão principal |

### Claro · branco e verde

Fundo verde muito claro, painéis brancos translúcidos, e **quatro verdes distintos**: folha (destaque), musgo (ações secundárias), floresta (estado OK) e jade (secundária).

| Token | Hex | Uso |
|---|---|---|
| canvas | `#EEF5EA` | Fundo |
| surface | `#FFFFFF` | Painéis, com 52% de opacidade |
| soft | `#E2EDD7` | Áreas alternadas |
| border | `#9DB38A` | Divisores |
| text / heading / muted | `#132210` / `#18300F` / `#3F5234` | Texto |
| accent | `#3E7A1E` | Verde folha: foco e destaque |
| secondary | `#0E7A62` | Verde jade: cartões de comunicação e sensor |
| positive | `#1F6B3A` | Verde floresta: estado OK |
| warning / danger | `#8A5A00` / `#B3261E` | Aviso / alarme (reservadas) |
| sky / violet / rose | `#1F6FA8` / `#4B55C8` / `#A03C8E` | Matizes de barras e ícones |
| on_strong | `#FFFFFF` | Texto sobre o botão principal |

**Origem do verde.** Não há manual de marca da Arauco no repositório. O matiz principal (cerca de 92°) vem do logo *ARAUCO | Projeto Sucuriú*. **Se houver o manual oficial, troque `accent`, `secondary` e `positive` em `appearance.py`.**

**Contrastes (WCAG, conferidos em `tests/test_glass.py`).** Texto sobre fundo e sobre painel acima de 13:1; texto secundário acima de 7:1; destaque sobre o fundo acima de 4,5:1; texto do botão principal acima de 4,5:1. Controles desabilitados ficam perto de 3,5:1 de propósito.

## Botões, cores e séries

**Botões.** Todos iguais: véu translúcido da cor de texto (10% no noturno, 7% no claro), borda fina, cantos de 12 px. Ao passar o mouse, o véu fica um pouco mais forte e a borda ganha o destaque (ouro ou verde). O **botão principal** é um preenchimento sólido neutro (quase branco no noturno, quase preto no claro) com texto invertido. **Emergência** é a única exceção: vermelho, porque é alarme.

**Gráficos.** Uma cor por banda espectral, sempre na mesma ordem (`appearance.SERIES`): noturno `#3987E5 #D95926 #199E70 #C98500 #D55181 #9085E9`; claro `#2A78D6 #EB6834 #1BAF7A #EDA100 #E87BA4 #6250D6`. São cores de **dados**, sempre com o rótulo da banda (nome e comprimento de onda) e uma tarja ao lado.

## Superfícies

Receitas em `glass.py` (sem Qt, testadas). O nome do módulo é herança do visual anterior:

| Elemento | Receita |
|---|---|
| Painel | Superfície translúcida (32% no noturno, 52% no claro), borda fina de tinta do tema a 16%, raio 12 px |
| Cartão de resultado e rodapé | O mesmo painel, um pouco mais opaco, com um sopro de ouro |
| Cartões de comunicação e sensor | Borda na cor secundária (roxo lilás no noturno, verde jade no claro) |
| Botão | Véu translúcido neutro (ver acima), sem gradiente nem fio de luz |
| Campos | Poço translúcido, mais fundo que o painel |
| Fundo | Cor do tema com brilhos suaves (`glow_spec`), sem textura |

Diálogos usam o mesmo painel translúcido sobre a cor do tema.

## Tipografia

Quatro famílias, embutidas em `assets/fonts/`; o programa as carrega na abertura, então a aparência é igual no Windows, no Linux e no executável.

| Família | Função | Licença |
|---|---|---|
| **Inter** | Interface: rótulos, botões, texto corrido. Sans neutra e legível em tamanhos pequenos, a mais próxima do estilo do iOS sem usar a fonte da Apple | SIL OFL |
| **Arena** | Marca: o nome "SpectrumLab Pro" no cabeçalho. Não tem dígitos nem acentos: só serve para o nome | Não documentada (ver abaixo) |
| **Dropline** | Títulos e cabeçalhos de seção. Cobre acentos e dígitos; só existe em peso regular | Não documentada (ver abaixo) |
| **IBM Plex Mono** | Valores de medição (KPIs, número kappa, eixos, console), largura fixa | SIL OFL |

A IBM Plex Sans, usada antes na interface, saiu. A EB Garamond também saiu. Os arquivos *Evershore* e *The Heritage Legacy Fancy Logo*, enviados junto, são decorativos e **não são usados** na interface operacional.

**Aviso de licença.** Os arquivos Arena, Dropline, Evershore e Heritage não trazem licença legível, e o repositório é público. A Evershore declara `fsType 4` (incorporação só para visualização/impressão). Antes de distribuir o executável ou publicar o repositório com essas fontes, confirme os direitos de uso com a origem delas; se não houver permissão, troque `FAMILY_BRAND` e `FAMILY_DISPLAY` em `typography.py`.

Só os pesos **400 e 700** são usados nas famílias que têm os dois. A Dropline e a Arena só têm o regular: o QSS normalizado remove o negrito delas. A Dropline não tem alguns sinais (`·`, `…`, `–`): a pilha cai para a Inter nesses caracteres.

Se uma fonte não carregar, o programa usa Segoe UI / Consolas (nessa ordem de preferência por papel).

### Escala (pixels, a 100%)

| Papel | Tamanho | Família · peso | Uso |
|---|---|---|---|
| display | 44 | Dropline 400 | Só na abertura |
| hero | 40 | Mono 400 | Número kappa |
| kpi | 28 | Mono 400 | Valor dos indicadores |
| brand | 24 | Arena 400 | Nome "SpectrumLab Pro" no cabeçalho |
| title | 24 | Dropline 400 | Títulos de diálogo |
| section | 20 | Dropline 400 | Títulos de painel e do indicador de análise |
| button | 16 | Inter 700 | Botão principal e Concluir do teclado |
| card | 14 | Inter 400 | Título de cartão, botões |
| body | 14 | Inter 400 | Texto corrido, campos |
| label | 12 | Inter 400 | Rótulos pequenos |
| caption | 12 | Inter 400 | Legendas e apoio |
| data | 14 | Mono 400 | Tabelas e console |

Regras:

1. A escala é 12, 14, 16, 20, 24, 28 e 40 px (44 só na abertura). O mínimo é 12 px: nada fica menor, e tamanhos antigos de 9 a 11 px sobem para 12.
2. Cada painel usa no máximo quatro tamanhos.
3. Cada tela tem um único destaque.
4. Números de medição sempre em Mono.
5. O QSS do Qt **ignora** `line-height` e `letter-spacing`; por isso o programa não os usa.

**Como é aplicado.** `typography.py` define a escala. Toda folha de estilo que passa pelo gerenciador de temas é normalizada: tamanhos vão ao degrau mais próximo, pesos aos disponíveis (400 ou 700), famílias antigas (Segoe UI, Bahnschrift, Georgia, Consolas) à família do mesmo papel, e `line-height`/`letter-spacing` são removidos. Assim, telas antigas seguem a escala sem reescrita. Novos widgets devem usar `typography.qss("papel")`.

## Responsividade

A janela se adapta a qualquer tela, sem encolher o texto:

- O painel é um canvas que **acompanha o tamanho da janela** e é ampliado ou reduzido só um pouco (escala entre 0,90 e 1,35, nunca abaixo do que o layout precisa). A lógica está em `responsive_math.py` (pura, com testes) e em `responsive_layout.py`.
- Quando falta largura, o **layout se reorganiza**: o cabeçalho passa para duas linhas abaixo de ~1590 px lógicos, os quatro indicadores viram uma grade 2×2 abaixo de ~1180 px e os painéis se empilham em tela vertical ou abaixo de ~1040 px.
- A coluna da esquerda (método, ensaios, calibração, resultado) fica numa **área rolável**: os cartões mantêm a altura natural e o texto nunca é comprimido; se não couber, rola.
- O cartão de calibração mostra R², RMSE e N em **linhas** (rótulo à esquerda, valor à direita), em vez de três caixas estreitas lado a lado, que era o que comprimia o texto.

## Cursor

O cursor do mouse é uma **seta de fibra de celulose**: corpo cor de papel, contorno escuro, um fio de luz claro para ler sobre o fundo escuro e fibras soltas na cauda. Sobre botões, listas e abas vira uma seta de destaque com o mesmo desenho (`assets/cursors/fibra-seta*.png` e `fibra-mao*.png`, em 32 px e 64 px para telas HiDPI). Campos de texto mantêm o cursor "I" do sistema, que indica onde se digita.

Os desenhos são gerados por `tools/gerar_assets.py`. A instalação está em `cursors.py` (um filtro de eventos da aplicação). Para voltar ao cursor do sistema: variável de ambiente `SPECTRUM_SYSTEM_CURSOR=1`.

## Botões e animações

Inspiração: movimento da Apple (molas com amortecimento, entradas escalonadas, fusões), sem copiar assets. As curvas estão em `animation_math.py` (`spring`, `ease_out_expo`, `staggered`; puras e testadas) e o que o QSS não anima fica em `button_fx.py` e `motion.py`.

| Elemento | Efeito |
|---|---|
| Botão em repouso | Véu neutro translúcido, cantos de 12 px |
| Passar o mouse/dedo | Véu um pouco mais forte e borda de destaque (180 ms) |
| Pressionado | O botão "cede" com **mola** (320 ms) e um véu uniforme que escurece, como no iOS (sem onda) |
| Soltar | Volta com **leve ultrapassagem** (900 ms), sem anel |
| Em andamento | Vira "Analisando…" com um véu de destaque |
| Desabilitado | Cinza apagado, texto cinza do tema, sem efeito |
| Abertura da janela | Painéis entram em sequência (atraso de 70 ms entre eles, 750 ms cada) com subida e fusão |
| Troca de tema | Fusão de ~360 ms entre a imagem antiga e a nova |
| Diálogos | Surgem com fusão de 200 ms |
| Barras do gráfico | Sobem em 850 ms com mola (ultrapassagem leve) |

O efeito de pressão é **só pintura**: não muda o tamanho do botão. Escalar a geometria foi descartado porque faz o layout se mexer e perde toques na borda.

**Animações reduzidas (uso técnico).** Não há opção na tela. A variável `SPECTRUM_REDUCE_MOTION=1` deixa só a troca de estado dos botões; molas, entradas, fusões e a subida das barras são desligadas.

## Indicador de análise

Abaixo do gráfico, o `AnalysisIndicator` mostra o que o equipamento faz, em linguagem simples:

- **Rosto colorido** desenhado em vetor (`emoji_icons.py`; amarelo com brilho, ficando laranja com gota de suor no alerta): sorri em repouso e ao concluir, pisca de tempos em tempos, dá um pulinho com faíscas coloridas quando a análise termina e fica preocupado em falha ou emergência. É desenhado em vez de usar emoji de texto porque o tema remove emojis de texto e as fontes de emoji colorido variam entre sistemas.
- **Título e frase** que se alternam a cada 4,5 s (`analysis_messages.py`, textos em português do Brasil).
- **Espectro animado** durante a leitura e **etapas 1 a 5**, cada etapa concluída na cor da sua banda (fechar gaveta, avançar sensor, ler, recuar sensor, abrir gaveta).
- **Mensagem final** "Análise concluída. Boa amostra!" por 7 s.

## Teclado

O programa não tem teclado virtual próprio. Em touchscreen ou celular, o teclado que abre nos campos de texto é o do próprio sistema (ele ocupa a tela enquanto o campo está em foco).

## Estado da aplicação

Aplicado: abertura, painel principal (cabeçalho com logo, indicadores compactos, coluna rolável, gráfico, cartões de comunicação e sensor em destaque, rodapé reduzido), cartões KPI, diálogos (via normalização), Configurações em duas seções, campos de IP, teclado, indicador, cursor, animações.

**Não verificado com o programa em execução.** Esta revisão foi escrita sem PyQt5 disponível no ambiente de desenvolvimento do assistente: a lógica pura tem testes (`tests/`), e há um teste gráfico (`tests/test_gui_smoke.py`) para rodar no Codespace, mas o resultado visual real precisa ser conferido pelo roteiro de `docs/TUTORIAL_CODESPACE.md`.
