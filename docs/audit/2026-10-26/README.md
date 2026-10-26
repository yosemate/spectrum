# Revisão de engenharia — 26/10/2026

Esta é uma entrega incremental de correções, com pendências explícitas. Não encerra toda a auditoria e não libera a bancada para operação industrial ou Kappa validado.

Base verificada: `main`, commit `893164537c4193dcb02489516967d94a6dbaa1c8`, árvore limpa. Trabalho em `fix/audit-safety-traceability`. Não foram encontrados arquivos AGENTS.md no checkout. Nenhum movimento físico, gravação de firmware, merge ou publicação foi executado. Bancos e referências usados nos testes são temporários, separados dos dados reais.

## Evidência e execução

- Python 3.12, Linux, Qt offscreen; dependências instaladas em ambiente virtual isolado com requirements.txt.
- Baseline com dependências: **147 testes, 141 aprovados, quatro falhas, dois erros**. O log está em `baseline-tests.txt`.
- Resultado desta entrega: consultar `verified-tests.txt` e `verified-run.txt`, copiados da execução final.
- O teste de prazos extrai a função C++ do sketch e a compila com g++. Testa prazo absoluto apesar de heartbeat, origem que não libera e rollover de millis de 32 bits. Isso **não equivale a compilar o sketch ESP32 completo**, medir neutro do servo ou comprovar parada física.
- O teste `test_workflow_integration.py` usa janela real, worker e TCP reais com simulador determinístico: dez brancos, dez escuros, amostra externa TRACE-42, cinco aquisições, validação instrumental, persistência SQLite, PDF e desconexão. As decisões humanas são automatizadas somente no teste. O texto do PDF deve conter SIMULADA e TRACE-42.
- Outros testes cobrem 150% sem corte, detalhe sem dado válido, exceção global, bloqueio após reconhecimento da emergência, contexto congelado, permissões/invalidação, origem no banco, leitura com carcaça aberta, cancelamento por emergência e backup/restauração.
- Qt offscreen foi efetivamente exercitado. Screenshot da janela e primeira página do PDF foram inspecionados durante o desenvolvimento. Não houve teste de toque, DPI Windows ou resolução mínima validada com operador.
- Tentativa de `bash run/setup.sh` falhou: apt não encontrou Xvfb, x11vnc, noVNC, websockify e outros pacotes. **Não foi exercitada uma sessão noVNC**, nem um Codespace autenticado.
- Arduino CLI/PlatformIO não estão instalados. Compilação integral e bancada permanecem pendentes.

## Matriz dos achados

“Confirmado” refere-se à inspeção/reprodução no código base, não à aprovação da correção em bancada. “Parcial” na entrega significa trabalho ainda aberto. Não há alegação de conclusão para itens pendentes.

| ID | Validação inicial | Entrega, evidência e limitação |
|---|---|---|
| S1 | Confirmado por código; efeito físico dependente de hardware | Firmware: prazos independentes para porta/carrinho, liberação da origem e falha travada. Teste C++ no host. Prazos provisórios: porta 15 s, carrinho 10 s, origem 2 s. Não comissionados. |
| S2 | Confirmado | Hook global chama falha central antes do diálogo; fallback tenta emergência mesmo se falhar a apresentação. Teste de exceção sintética. |
| S3 | Confirmado; pendente | SoftAP continua sem senha e protocolo sem autenticação forte. UI/login e IDENTITY não autenticam controlador. **Bloqueador ainda aberto**: definir rede protegida e autenticação por sessão, inclusive USB/Bluetooth conforme ameaça. |
| S4 | Confirmado | Removidos pedido/renovação automática pelo login admin e aceitação de ACK administrativo legado. Bypass exige privilégio distinto `manutencao`, motivo e pedido explícito; expira com renovação operacional/revogação. Esse papel não é concedido automaticamente nem provisionado pela UI atual; fluxo de concessão e auditoria persistente de manutenção pendentes. |
| S5 | Confirmado | ACK e timer não voltam a IDLE. Botão Rearmar exige decisão humana e CMD:REARMAR/ACK; firmware exige carcaça fechada e chaves não contraditórias. Não inicia movimento. Teste do estado após ACK. Posição da gaveta continua estimada. |
| S6 | Confirmado | Fechamento assíncrono: solicita parada e aguarda até 6 s; timeout exige aviso/decisão explícitos. ACK significa reconhecimento do controlador, não prova independente da parada física. Fluxo de timeout precisa de teste gráfico dedicado. |
| D1 | Confirmado/reproduzido | Desconexão/falha/emergência invalidam apresentação principal e detalhes; números principais são retirados. Teste do fluxo e teste de qualidade do detalhe. |
| D2 | Confirmado | Detalhes/cartões consultam validade antes de avaliar zeros; ausência de leitura usa estado neutro. Zero adquirido continua sendo avaliado como sinal. |
| D3 | Confirmado | Campo externo visível de amostra; código interno gerado quando vazio, ID de ensaio independente. Campo de lote e leitor de código de barras não implementados. |
| D4 | Confirmado | IDENTITY declara REAL/SIMULADA, congelada por ensaio; firmware antigo fica NAO_CONFIRMADA. Banco, CSV atual/histórico e PDF, inclusive preview histórico, recebem origem. Declaração não é autenticada criptograficamente. |
| D5 | Confirmado | Falha fica visível como RESULTADO NÃO SALVO, preserva payload para Tentar salvar novamente e bloqueia novo scan enquanto pendente. Falhas múltiplas em gravação de réplicas ainda precisam de fila durável. |
| D6 | Confirmado | Removido Pronto na conexão inicial; falha/emergência e gravação pendente têm orientação própria. Outras mensagens legadas de conclusão e indicador de animação ainda requerem revisão. |
| D7 | Confirmado | Operador, método, origem, settings e referência capturados no início. Teste modifica sessão/origem após congelamento. Política de expiração de sessão e confirmação de settings pelo dispositivo pendentes. |
| Q1 | Confirmado/reproduzido | 150% é preservado; escala percentual cresce e saturação continua dependente de ADC. Teste em widget real. |
| Q2 | Dependente de validação analítica | Não alterados coeficientes nem inventadas métricas. Kappa continua demonstrativo/experimental. Necessário conjunto pareado e validação independente. |
| Q3 | Confirmado; parcial | Textos dos indicadores usam razões numéricas e rejeitam seletividade não demonstrada. Nomes históricos do esquema/alguns textos legados mantidos por compatibilidade. |
| Q4 | Confirmado | Overlay contínuo ocultado: gráfico operacional mostra seis barras discretas, com comprimentos de onda rotulados. Classe spline mantida por compatibilidade, não exibida. |
| Q5 | Confirmado | Chamadas operacionais usam normalize_sum; alias normalize_snv mantido com comentário explícito de compatibilidade. Chaves internas SNV legadas do gráfico ainda existem. |
| Q6 | Confirmado; pendente | Limites heurísticos e bloqueios instrumentais existentes preservados. Harmonização de qualidade por canal e aceitação analítica requerem especificação/validação. |
| Q7 | Parcialmente confirmado | Ausência de R²/RMSE preservada. Reformulação completa do cartão de referência permanece pendente. |
| H1 | Confirmado | DELETE legado recusado; invalidar_leitura verifica papel na camada de dados e grava evento com autor/motivo/UTC em transação. Dados mantidos e invalidação aparece no preview/PDF/CSV. SQLite não é inviolável para quem tem acesso ao arquivo. |
| H2 | Confirmado | CSV histórico inclui referência, scans, origem, contexto e invalidação; CSV atual recebe contexto e scans. Teste completo de interação dos dois diálogos CSV ainda pendente. |
| H3 | Confirmado; parcial | Réplicas recebem run_id/repeat_index no contexto JSON. Ainda falta entidade agregada persistida e confirmação transacional do conjunto inteiro. |
| H4 | Confirmado; parcial | Contexto identifica kappa_da_media_espectral; tela explica diferença da média/desvio dos Kappas individuais. Ainda falta persistir ambos os agregados e revisar exportação própria da repetibilidade. |
| H5 | Confirmado; parcial | Contexto inclui app, identidade/versão declarada do dispositivo, settings locais e referência. Sem hash de firmware/modelo nem negociação completa de configuração. |
| H6 | Confirmado; parcial | Novas medições e eventos usam UTC com fuso. Backup SQLite consistente e teste de restauração adicionados. Datas antigas preservadas sem inventar fuso; política de retenção/relógio e assinatura não implementadas. |
| T1 | Confirmado; parcial | Simulador rejeita scan com carcaça/porta/gaveta aberta ou sensor recuado. Ainda não reproduz todos os intertravamentos/autorizações do firmware. |
| T2 | Confirmado | Receptor TCP atende emergência/heartbeat enquanto aquisição/movimento usam espera cancelável. Operações concorrentes recusadas; servidor aceita uma sessão ativa. Teste de preempção da espera; latência física não medida. |
| T3 | Confirmado; parcial | Seed e cenários normal, sensor_ausente, fim_travado, chaves_contraditorias e saturacao. Faltam modos determinísticos próprios de pacotes antigos/incompletos, referência expirada/instável e falha de gravação no CLI. |
| T4 | Confirmado | Bind padrão de websockify passa a 127.0.0.1. Codespaces deve manter porta privada. Sem teste de acesso noVNC neste ambiente. |
| T5 | Confirmado | Diagnóstico de processo reconhece executável do venv e não exige textura desativada; README ajusta resolução. Roteiros históricos ainda merecem revisão integral. |
| M1 | Confirmado; pendente | Sem reescrita ampla; serviços/FSM permanecem concentrados em main.py. |
| M2 | Confirmado; pendente | Transformação de tema por regex preservada; testes existentes de paleta mantidos. |
| M3 | Confirmado; parcial | Compatibilidade UI/firmware/protocolo documentada abaixo; versões históricas de pacote/README ainda não unificadas. |
| M4 | Confirmado; pendente | Gerador da documentação técnica e dependências não reformulados. Gerador de relatório experimental foi exercitado no fluxo. |
| M5 | Confirmado; parcial | CI agora executa suíte inteira e testes de run/. Build completo ESP32 e executável continuam pendentes. |
| M6 | Confirmado; pendente documental | Nenhuma licença, fonte ou marca removida. Licenças gerais/terceiros ainda requerem inventário. |
| M7 | Confirmado; pendente | Abertura inicial TCP ainda é síncrona, com timeout. Leitura/transmissão continuam no worker. Necessária tarefa de conexão com cancelamento. |
| M8 | Confirmado; parcial | Redução de animações acessível em Configurações e persistida; mínimos explícitos do canvas preservados. Diálogos ainda podem ser reduzidos; validação física de tipografia/toque pendente. |

## Interface e fundamento

A orientação foi tornar causa e próxima ação visíveis e evitar qualidade divergente entre janelas. A página pública oficial da ISA-101 foi consultada: https://www.isa.org/standards-and-publications/isa-standards/isa-101-standards . Seu escopo sustenta avaliar usabilidade e ciclo de vida; não foi usado texto normativo integral nem declarada conformidade.

Permanece aberta a reorganização maior da navegação, alarmes com reconhecimento/retorno, redução de modais e revisão em resolução mínima acordada com operador. Não foram acrescentadas variáveis de processo fictícias.

## Migrações e compatibilidade

- SQLite acrescenta `origin`, `trial_context_json`, `invalidated_at`, `invalidated_by`, `invalidation_reason` e tabela `audit_events`. Linhas antigas são mantidas; origem desconhecida é apresentada como NAO_CONFIRMADA.
- O JSON de contexto tem `schema_version=1`. Contém ID interno, código externo, operador, método, origem, versão do app, início UTC, identidade declarada, settings, snapshot de referência e estimador. Réplicas recebem vínculo adicional.
- Aplicativo continua em 4.16.4/build1265; sketch declara extensão `4.16.2-audit1`, protocolo base 2. IDENTITY e REARMAR/REARME_CONFIRMADO são extensões desta branch. Igualdade de número de versão não implica compatibilidade.
- Firmware antigo pode fornecer aquisições de origem não confirmada. **Não possui os novos prazos nem o ACK de rearme**: após falha/emergência a UI fica bloqueada até usar controlador compatível. Não há fallback que libere retomada automaticamente.
- normalize_snv continua sendo alias de normalize_sum para chamadas antigas; não implementa SNV estatística.
- excluir_leitura passa a recusar exclusão permanente. Integrações devem usar invalidar_leitura com usuário existente autorizado e motivo.
- A trilha é de aplicação; acesso direto ao SQLite pode alterá-la. Nenhuma assinatura ou conformidade regulatória é prometida.

## Reprodução sem hardware

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s run -p 'test_*.py' -v
```

Windows: usar `.venv\Scripts\python.exe` e definir QT_QPA_PLATFORM=offscreen pelo shell correspondente. g++ é necessário apenas ao teste da função C++ no host; a ausência gera skip explícito, sem validar firmware.

Fluxo noVNC reproduzível em ambiente com apt funcional:

```bash
bash run/setup.sh
bash run/start_display.sh
bash run/start_app.sh
```

Manter 6080 privada no Codespaces; uso local: http://127.0.0.1:6080/vnc.html . Na UI selecionar Wi-Fi, conectar ao simulador 127.0.0.1:8080, confirmar selo de simulação, medir branco e escuro pelo assistente, identificar amostra, medir, conferir qualidade/gravação, histórico e exportar CSV/PDF. Confirmar que SIMULADA acompanha o registro. Este roteiro foi automatizado por TCP/offscreen; sua execução pelo navegador permanece pendente.

Para cenários: `python run/fake_esp32.py --seed 42 --scenario saturacao` (sem outra instância do simulador usando a porta). Simulação não valida segurança física.

## Backup/restauração

Criar cópia consistente sem substituir destino existente:

```bash
python run/backup_database.py /caminho/usuarios.db /caminho/seguro/usuarios-backup.db
```

Salvar também calibracao.json e preferências, com controle de acesso: o banco contém credenciais derivadas e dados de ensaio. Para restaurar: encerrar aplicativo e simulador, preservar uma cópia do banco atual, verificar `PRAGMA integrity_check` no backup, copiar para um diretório de dados separado, iniciar com SPECTRUM_LAB_DATA_DIR apontando a esse diretório e conferir registros antes de substituir qualquer instalação. Nenhuma restauração de dados reais foi realizada. O teste restaura exclusivamente em diretório temporário.

## Arquivos mantidos e decisões

Nenhum arquivo removido. Firmware, biblioteca do sensor, run/, devcontainer, testes, adaptadores, fontes/licenças, SVGs e KaTeX foram preservados. A spline continua definida por compatibilidade, mas o overlay não aparece na operação. Remoção de assets/legado depende da auditoria de empacotamento e geração documental ainda pendente.

## Antes de bancada e validação analítica

1. Resolver autenticação/rede do controlador (S3), revisar permissões de manutenção e compilar o firmware integral em toolchain fixada.
2. Responsável físico deve confirmar circuito de emergência, neutros/direções, chaves e proteção independente do software. Comissionar os prazos por eixo; não presumir que 15/10/2 segundos são seguros para a geometria real.
3. Ensaiar chave ausente, origem presa, contradição, perda de comunicação, abertura de proteção e rearme, registrando atuação real sem reinício automático.
4. Completar os itens de software marcados parciais/pendentes, em especial conexão assíncrona, repetibilidade transacional e exportações/qualidade.
5. Validar Kappa com referência laboratorial, amostras representativas e conjunto independente antes de qualquer alegação de desempenho.
