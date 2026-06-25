# SAP-ESCRITURACAO-V2 — Monitor de escrituração de notas de grãos

Pipeline em Python que, a cada ciclo, lê filas de pedidos/contratos pendentes no
**PostgreSQL**, consulta o **SAP HANA** para identificar NFs que chegaram ao VTIN mas
ainda **não foram escrituradas** (DOCNUM vazio no SAP), salva essas notas aptas no
Postgres para o bot RPA processar, exporta um Excel e notifica o Teams via Power Automate.

> **Status:** branch `refactor/escrituracao-v2` — Fase 1 (reestruturação em camadas) ✅
> + Fase 2 (correções de negócio validadas em prod) ✅
> + Integração Automation Anywhere ✅. **5 processos ativos. 78 testes.**
> **PR ainda não aberto.**

---

## 1. Objetivo

Automatizar a verificação de elegibilidade de escrituração das notas de grãos,
eliminando conferência manual:

1. Ler as filas de contratos/pedidos pendentes no PostgreSQL (status `12`/`13` ou `01`).
2. Para cada item, consultar o SAP HANA: obter os valores esperados do cockpit
   via `ZMMT0022` e cruzar com a NF-e real no `VTIN` por CPF/CNPJ + quantidade + valor.
3. **Veredito:** `DOCNUM` **vazio** no SAP = NF **pendente de escrituração = APTA**
   → salva no Postgres e o bot RPA processa; `DOCNUM` preenchido = já foi escriturada
   → ignorada (não é o nosso caso).
4. Persistir as notas aptas no PostgreSQL (UPSERT) + exportar Excel completo.
5. Notificar o Teams com Adaptive Card e acionar o bot AA (+3 min) se há aptas.

> **DOCNUM vazio = precisa ser escriturado.** Quando o bot conclui, o DOCNUM aparece
> no SAP e a nota sai da fila no próximo ciclo. O status `15` na fila Postgres
> **não garante escrituração** — a verdade está sempre no `DOCNUM` do SAP.

---

## 2. Resumo técnico

| Item | Valor |
|---|---|
| **Linguagem / runtime** | Python **3.11.9** (venv `.ESCR_SAPvenv`) |
| **Banco de fila** | PostgreSQL 10.1.1.36:5432 · db `postgres` · schema `prod` |
| **Banco HANA** | SAP HANA 10.2.3.244:30213 · db `ECP` · schema `SAPABAP1` · user `POWERBI` |
| **Processos ativos** | `CTRFIXO` · `CTR_S_FIXACAO` · `CTR_C_FIXACAO` · `ARMAZEN` · `VALOR` |
| **Critério de aptidão** | `DOCNUM` **vazio** = pendente (apto) · preenchido = já escriturado (ignorado) |
| **Tabela de resultado** | `complemento_notas_escrituracao` — 84 colunas UPPERCASE (schemas `dev` e `prod`) |
| **Estratégia de gravação** | Truncate no início de cada ciclo + UPSERT com índice único por `(PROCESS_NAME, DOC_COMPRA, N_CONTRATO, NUMERO_COCKPIT, DOCNUM, STATUS_EXECUCAO)` |
| **Export** | Excel em `data/output/{process_name}/` |
| **Notificação** | Adaptive Card → Teams via `POWER_AUTOMATE_TEAMS_URL` (Power Automate) |
| **Automação RPA** | Automation Anywhere A360 — agendamento do bot de escrituração (+3 min) após apta encontrada |
| **Logs** | loguru — console + arquivo diário (`logs/`) |
| **Testes** | 78 (golden de caracterização + unit); conectores fake, não tocam SAP/PG/Teams |

---

## 3. Pacotes (dependências do venv)

Declarados em [`requirements.txt`](requirements.txt); versões instaladas no venv:

| Pacote | Versão | Papel no projeto |
|---|---|---|
| `hdbcli` | 2.28.17 | Driver SAP HANA (SAP HANA Client) |
| `psycopg[binary]` | 3.3.3 | Driver PostgreSQL |
| `pandas` | 3.0.1 | DataFrame, normalização, Excel |
| `openpyxl` | 3.1.5 | Exportação XLSX |
| `pydantic` | 2.12.5 | Modelos de config (`SapConfig`, `PostgresConfig`, `ProcessDefinition`) |
| `python-dotenv` | 1.2.2 | Leitura do `.env` |
| `loguru` | 0.7.3 | Logging (console + arquivo diário) |
| `PyYAML` | 6.0.3 | Leitura de `config/processes.yaml` |
| `requests` | 2.32.5 | Notificação Teams via webhook Power Automate |
| `tenacity` | 9.1.4 | Retry (disponível; não aplicado nas queries ainda — ver backlog) |
| `pytest` | 9.0.3 | Suíte de testes (dev) |

Instalar dependências de desenvolvimento:

```powershell
.\.ESCR_SAPvenv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

---

## 4. Processos

Os 5 processos são definidos em [`config/processes.yaml`](config/processes.yaml) e
carregados dinamicamente por `ProcessLoader`. A ordem é preservada (afeta o payload
do Teams).

| `process_name` | Tipo de contrato | Parâmetros HANA | Fila PostgreSQL (entrada) | Status da fila |
|---|---|---|---|---|
| `V2_Consulta_Comp_CTRFIXO` | Compra com preço fixo | `doc_compra`, `numero_cockpit` | `prod.complemento_quantidade_fixo_fila` | `'12','13'` |
| `V2_Consulta_Comp_CTR_S_FIXACAO` | Compra sem fixação ("a fixar") | `doc_compra`, `numero_cockpit` | `prod.complemento_quantidade_sem_fixacao_fila` | `'12','13','9'` |
| `V2_Consulta_Comp_CTR_C_FIXACAO` | Compra com fixação | `doc_compra`, `numero_cockpit` | `prod.complemento_quantidade_com_fixacao_fila` | `'12','13'` |
| `V2_Consulta_Comp_ARMAZEN` | Venda / armazém | `n_contrato`, `numero_cockpit` | `prod.complemento_quantidade_deposito_fila` | `'12','13'` |
| `V2_Consulta_Comp_VALOR` | Complemento de valor (CFIN) | `doc_compra`, `numero_cockpit` | `prod.complem_valor_fila` | `'01'` |

Todos os resultados são gravados em `dev/prod.complemento_notas_escrituracao` (84 colunas UPPERCASE).

As filas de quantidade usam `CROSS JOIN LATERAL regexp_split_to_table(numero_cockpit, '\|')` para
explodir cockpits compostos em linhas individuais — uma consulta HANA por cockpit.

> **Processo VALOR — lógica especial:** `ZMMT0022.VALOR` representa o valor do *complemento*
> (diferença em centavos), não o total da NF. O match no HANA usa apenas CPF/CNPJ + QTDE,
> sem filtro de valor, com âncora de data de ±90 dias a partir de `ZMMT0022."DATA"`.

---

## 5. Arquitetura

```
main.py                      # entrypoint fino → Application().run()
config/processes.yaml        # processos (declarativo, YAML)
src/
  domain/                    # enums (StatusProcesso, StatusExecucaoGlobal, SaveStrategy)
  │                          # + ProcessDefinition (Pydantic) + protocols — sem I/O
  config/                    # SapConfig/PostgresConfig/LogConfig (Pydantic + from_env())
  │                          # + ProcessLoader (YAML) + process_definitions (shim de compat.)
  │                          # + ddl_complemento.py (DDL fixo 84 cols UPPERCASE)
  connectors/                # HanaConnector (retry automático) · PostgresConnector (DDL/DML/UPSERT)
  │                          # + AutomationAnywhereConnector (auth/CB/retry · guard · schedule)
  services/                  # ProcessRunner (fila → HANA → DataFrame)
  │                          # + ResultadoService (normaliza · Excel · UPSERT Postgres)
  orchestration/             # Application (orquestra o ciclo) · column_log
  utils/                     # logger · paths · execution_summary · teams_notifier
sql/
  postgres/consultas/        # 5 SQLs de leitura de fila (Consulta_Comp_*.sql)
  sap_hana/consultas/        # 5 SQLs HANA (estrutura: CTEs zmmt_base / ctr / vtin_fallback)
tests/
  golden/                    # testes de caracterização (travam DataFrame, seq. gravação, payload)
  unit/                      # normalização, DDL, enums, settings, loader, import surface
  fixtures/golden/snapshots/ # snapshots JSON dos testes golden
```

**Fluxo de um ciclo:**

Cada execução de `main.py` corresponde a **um ciclo completo**: lê todas as filas,
consulta o SAP HANA, grava o resultado e encerra. A recorrência é externa
(Agendador de Tarefas do Windows). O ciclo tem 4 fases principais: guard, truncate,
loop de processos e notificação.

```
Windows Task Scheduler dispara o monitor (1 execução = 1 ciclo)
              │
              ▼
  ┌─ GUARD AA ────────────────────────────────────────────────────────┐
  │  Verifica se algum bot de escrituração está ativo no Control Room │
  │  SIM → aborta o ciclo inteiro (sem truncar, sem consultar SAP)   │
  │         preserva os dados da execução em andamento               │
  └───────────────────────────────────────────────────────────────────┘
              │ NÃO — nenhum bot ativo, pode prosseguir
              ▼
  Trunca complemento_notas_escrituracao em dev e prod
  (ciclo sempre começa do zero — reflete apenas o estado atual)
              │
              ▼
  ┌─ Para cada um dos 5 processos ativos (em ordem do YAML) ──────────┐
  │                                                                    │
  │  1. Lê a fila PostgreSQL (prod)                                    │
  │     cockpits compostos "id1|id2|id3" → explodidos em linhas       │
  │     individuais via CROSS JOIN LATERAL (1 linha = 1 cockpit)      │
  │              │                                                     │
  │              ▼                                                     │
  │  2. Para cada cockpit → consulta SAP HANA (1 query por cockpit)   │
  │     ├─ VIA_MIRO: MIRO_DOC → J_1BNFDOC.BELNR → DOCNUM             │
  │     │   caminho determinístico; usado quando MIRO_DOC preenchido   │
  │     └─ VIA_CPF_MATCH: CPF/CNPJ + QTDE (+ VALOR exceto VALOR)     │
  │         fallback fuzzy usado quando MIRO_DOC está vazio           │
  │              │                                                     │
  │              ▼                                                     │
  │  3. Consolida resultado por cockpit no DataFrame                   │
  │     DOCNUM vazio      → SUCESSO   (NF pendente de escrituração)   │
  │     DOCNUM preenchido → descartado (já foi escriturada)           │
  │     Exceção           → ERRO                                      │
  │              │                                                     │
  │       ┌──────┴──────┐                                             │
  │       ▼             ▼                                             │
  │  Exporta Excel   UPSERT Postgres (somente linhas SEM DOCNUM)      │
  │  data/output/    dev + prod.complemento_notas_escrituracao        │
  │  {processo}/     84 colunas UPPERCASE, índice único               │
  │  YYYYMMDD.xlsx        │                                           │
  │                       ▼ (se há aptas no processo)                │
  │                  Agenda bot AA +3 min                             │
  │                  pick_runner([8635, 9307]) → POST /v2/schedule/   │
  │                  aguarda a tabela estar gravada antes de disparar  │
  └────────────────────────────────────────────────────────────────────┘
              │
              ▼
  Consolida ExecutionSummary global
  (total de linhas / aptas / pendentes / erros / duração por processo)
              │
              ▼
  Log (loguru) + Adaptive Card → Teams via Power Automate
  Header: verde (SUCESSO) | laranja (PARCIAL/SEM_DADOS) | vermelho (ERRO)
  Card por processo com badge de status + barra de totais (TOTAL/APTAS/PENDENTES)
```

---

## 6. Estrutura de pastas

```
SAP-ESCRITURACAO-V2\
├── main.py                      # entrypoint
├── config\
│   └── processes.yaml           # processos ativos (declarativo)
├── src\                         # código-fonte (ver seção 5)
├── sql\                         # consultas SQL (Postgres + HANA)
├── tests\                       # suíte de testes
├── data\
│   └── output\                  # Excels gerados por ciclo
├── logs\                        # logs diários (loguru, ignorados pelo git)
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml               # config pytest
├── .env                         # credenciais (NÃO versionado)
├── .ESCR_SAPvenv\               # ambiente virtual Python 3.11.9
└── _*.py                        # scripts de diagnóstico/auditoria (raiz, não versionados)
```

Scripts de diagnóstico disponíveis na raiz (rodar direto pelo venv, não afetam prod):

| Script | O que faz |
|---|---|
| `_analise15.py` | Valida em lote se itens status 15 têm DOCNUM (usa cache JSON `data/_analise15_data.json`) |
| `_lista15.py` | Regrava a lista xlsx/csv a partir do cache, sem bater no HANA |
| `_migra_dedup.py` | Dedup + cria índice único em `tb_resultado_final_hana` (`--apply` para executar) |
| `_audit_cols.py` / `_audit_planilha.py` | Auditoria de colunas e planilha de resultado |
| `_diag_*.py` | Diagnósticos pontuais (VTIN, status, pedido, RPA, etc.) |
| `_valida_pedido.py` | Validação manual de um pedido/contrato específico |

---

## 7. Banco de dados

### PostgreSQL — fila de entrada

| Parâmetro | Valor |
|---|---|
| Host | `10.1.1.36` |
| Porta | `5432` |
| Banco | `postgres` |
| Schema das filas | `prod` (hardcoded nos SQLs de fila) |
| Schema de resultado | `dev` e `prod` (configurável via `TARGET_SCHEMAS` em `Application`) |
| Tabela de resultado | `complemento_notas_escrituracao` |

A tabela de resultado tem **84 colunas UPPERCASE**, schema pré-definido em
`src/config/ddl_complemento.py` — criada com todas as colunas mesmo quando não há
registros aptos (evita tabela incompleta em ciclos onde todos retornam SEM_RETORNO).
Os 5 processos compartilham a mesma tabela.

**Índice único:**

```sql
CREATE UNIQUE INDEX ix_uq_complemento_notas_escrituracao
ON complemento_notas_escrituracao (
    "PROCESS_NAME",
    COALESCE("DOC_COMPRA", ''),
    COALESCE("N_CONTRATO", ''),
    COALESCE("NUMERO_COCKPIT", ''),
    COALESCE("DOCNUM", ''),
    "STATUS_EXECUCAO"
);
```

> ⚠️ Somente linhas com `DOCNUM` **vazio** são gravadas — `DOCNUM` vazio = nota pendente de escrituração (apta para o bot RPA processar). `DOCNUM` preenchido = já foi escriturada → não é gravada.

### Dicionário dos campos das filas

#### Filas de quantidade — `complemento_quantidade_*_fila` (4 tabelas)

Campos presentes nas 4 tabelas de fila de quantidade (`complemento_quantidade_fixo_fila`,
`complemento_quantidade_sem_fixacao_fila`, `complemento_quantidade_com_fixacao_fila`,
`complemento_quantidade_deposito_fila`):

**Identificação / controle**

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | integer | PK da fila |
| `status` | varchar | Ciclo de vida: `1`=novo · `9`=aguardando fixação (S_FIXACAO) · `12`/`13`=pendente monitor · `15`=concluído |
| `status_complemento_fixo` | varchar | Descrição textual do status (`ESCRITURAÇÃO JÁ REALIZADA`, etc.) |
| `msg_rpa` | varchar | Mensagem do RPA que processou o item |
| `data_hora_inicio` | varchar | Quando o item entrou na fila |
| `data_hora_ultima_atualizacao` | varchar | Data/hora da última modificação |

**Contrato / pedido**

| Campo | Tipo | Descrição |
|---|---|---|
| `n_contrato` | varchar | Número do contrato (KONNR para compra / VBELN para armazém) — parâmetro 1 do HANA para ARMAZEN |
| `doc_compra` | varchar | Pedido de compra (EBELN) — parâmetro 1 do HANA para processos CTR |
| `tipo` | varchar | Tipo de lançamento (`A_FIXAR_C`, `SFIS`, `CFIS`, etc.) |
| `tipo_contrato` / `desc_tipo_contrato` | varchar | Código e descrição do tipo de contrato SAP |
| `tipo_pedido` | varchar | Tipo de pedido SAP (ex.: `ZPGD`) |
| `safra` | varchar | Safra de referência (ex.: `2025/2026`) |
| `material` | varchar | Código do material SAP |
| `centro` | varchar | Centro SAP responsável |
| `cod_parceiro` / `desc_parceiro` | varchar | Código e nome do fornecedor/cliente |
| `moeda` | varchar | Moeda do contrato (ex.: `BRL`) |

**Quantidades / valores**

| Campo | Tipo | Tabelas | Descrição |
|---|---|---|---|
| `qtd_contratado` | varchar | todas | Quantidade total contratada |
| `qtd_a_entreg_a_fix` | varchar | todas | Quantidade a entregar/fixar |
| `qtde_liquidada` | varchar | todas | Quantidade liquidada |
| `qtde_rom_entregue` | varchar | todas | Quantidade ROM entregue |
| `qtde_nf` | varchar | DEPOSITO | Quantidade da NF (substituição de `qtde_liquidada`) |
| `valor` | varchar | todas | Valor do cockpit |
| `data_pagamento` | varchar | todas | Data prevista de pagamento |

**Cockpit / NF-e**

| Campo | Tipo | Descrição |
|---|---|---|
| `numero_cockpit` | varchar | ID(s) do cockpit separados por `\|` — parâmetro 2 do HANA |
| `numero_miro` | varchar | Número do documento MIRO (`ZMMT0022.MIRO_DOC`) — usado na validação via VIA_MIRO |
| `chave_acesso` | varchar | Chave de acesso NF-e (44 dígitos) |
| `num_nota_fiscal` | varchar | Número da NF |
| `series` | varchar | Série da NF |
| `num_aleatorio` | varchar | Número aleatório NF-e (DOCNUM9) |
| `num_log` | varchar | Número de autorização SEFAZ |
| `digito_verificador` | varchar | Dígito verificador NF-e |
| `data_documento` | varchar | Data do documento NF |
| `data_processamento` / `hora_processamento` | varchar | Data e hora de processamento da NF — preenchido apenas em CTR_FIXO e CTR_S_FIXACAO; sempre nulo em CTR_C_FIXACAO e DEPOSITO |

**Exclusivo CTR_C_FIXACAO**

| Campo | Tipo | Descrição |
|---|---|---|
| `fixacao` | varchar | Número da fixação de preço vinculada ao cockpit |

#### Fila de complemento de valor — `complem_valor_fila` (processo VALOR)

Schema diferente das demais filas. Lida com `ctr_status = '01'` (NF de complemento
solicitada com sucesso pelo cockpit).

| Campo | Tipo | Descrição / mapeamento para o HANA |
|---|---|---|
| `id` | integer | PK da fila |
| `ctr_status` | varchar | Ciclo de vida: `01` = apta para consulta |
| `ctr_description` | varchar | Descrição textual do status |
| `tipo_complemento` | varchar | Tipo de complemento (ex.: `CFIN`) |
| `n_contrato` | varchar | Número do contrato |
| `documento_compras` | varchar | Pedido de compra (EBELN) → `doc_compra` → parâmetro 1 do HANA |
| `id_cockpit` | varchar | ID(s) do cockpit separados por `\|` → `numero_cockpit` → parâmetro 2 do HANA |
| `centro` | varchar | Centro SAP |
| `safra` | varchar | Safra de referência |
| `material` | varchar | Código do material SAP |
| `codigo_parceiro` | varchar | Código do fornecedor/cliente → `cod_parceiro` |
| `ctr_last_updated` | varchar | Data/hora da última atualização → `data_hora_ultima_atualizacao` |
| `msg_sap` | varchar | Mensagem do RPA → `msg_rpa` |

### SAP HANA — fonte de verdade

| Parâmetro | Valor |
|---|---|
| Host | `10.2.3.244` |
| Porta | `30213` |
| Banco | `ECP` |
| Schema | `SAPABAP1` |
| Usuário | `POWERBI` |

**Tabelas consultadas:**

| Tabela | Módulo SAP | Papel no processo |
|---|---|---|
| `ZMMT0022` | Z (customizado) | Fila interna: pedido/contrato, cockpit, QTDE, VALOR, MIRO_DATA |
| `EKKO` | MM – Compras | Cabeçalho do pedido de compra (EBELN, LIFNR) |
| `EKPO` | MM – Compras | Itens do pedido de compra (MATNR) |
| `MARA` | MM – Material | Dados do material — filtro `SPART='01'` (grãos) |
| `ZVS_BP_ID_FISCAL` | Z (customizado) | CPF/CNPJ do fornecedor vinculado ao LIFNR |
| `VBAK` | SD – Vendas | Cabeçalho do contrato de venda (armazenagem) |
| `VBAP` | SD – Vendas | Itens do contrato de venda (armazenagem) |
| `KNA1` | SD – Clientes | Dados do cliente — CPF/CNPJ para armazenagem |
| `/VTIN/_XML_REC` | VTIN (NF-e) | XML da NF-e recebida: CPF, CODESTA, MANSTA, valor, quantidade |
| `/VTIN/NFEIT` | VTIN (NF-e) | Itens da NF-e — quantidade por item (`QCOM`) |
| `J_1BNFE_ACTIVE` | FI-LOC (Brasil) | NF-e ativa no SAP — fornece o `DOCNUM` |
| `J_1BNFDOC` | FI-LOC (Brasil) | Documento NF-e — cabeçalho fiscal (peso, valor total) |

> **Compra** (CTRFIXO, CTR_S_FIXACAO, CTR_C_FIXACAO): `ZMMT0022 → EKKO / EKPO / MARA / ZVS_BP_ID_FISCAL → /VTIN/_XML_REC / /VTIN/NFEIT / J_1BNFE_ACTIVE / J_1BNFDOC`
>
> **Armazenagem** (ARMAZEN): substitui o bloco de compra por `VBAK / VBAP / KNA1`

---

## 8. Configuração (.env)

Credenciais ficam **somente** no `.env` (não versionado). Variáveis esperadas:

```ini
# --- SAP HANA ---
SAP_HOST=
SAP_PORT=
SAP_DATABASE=
SAP_SCHEMA=
SAP_USER=
SAP_PASSWORD=
SAP_CONNECTION_DELAY=1.0   # segundos entre tentativas de conexão
SAP_QUERY_DELAY=0.5        # segundos entre queries HANA (throttle)
SAFRA_ANO=                 # ano do filtro HANA; padrão = ano corrente

# --- PostgreSQL ---
POSTGRES_HOST=
POSTGRES_PORT=5432
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_SCHEMA=public

# --- Teams ---
POWER_AUTOMATE_TEAMS_URL=  # webhook Power Automate; deixar vazio para desabilitar

# --- Automation Anywhere ---
AA_CONTROL_ROOM_URL=       # ex.: https://empresa.my.automationanywhere.digital
AA_USERNAME=               # usuário da API do Control Room
AA_PASSWORD=               # senha (ou AA_API_KEY para autenticação por chave)
AA_AUTH_PATH=/v2/authentication  # /v1/authentication em alguns ambientes
AA_VERIFY_SSL=true
AA_TIMEOUT=60
AA_RUN_AS_USER_IDS=        # IDs dos runners em ordem de preferência (ex.: 8635,9307)
AA_CALL_RPA=true           # true=habilita guard check + agendamento de bots; false=desabilita (modo consulta)

# --- Log ---
LOG_LEVEL=INFO
LOG_SAVE_FILE=true
```

> `SAFRA_ANO` substitui o filtro `YEAR(VTIN_DT_EMISSAO)` nas 5 queries HANA. Se omitido,
> usa o ano corrente automaticamente — **não é necessário atualizar anualmente**.

Processos são configurados em [`config/processes.yaml`](config/processes.yaml)
(nome, caminhos SQL, parâmetros, tabela destino, flags `truncate_before_insert` /
`drop_and_create`). A ordem é preservada e afeta o payload do Teams.

---

## 9. Integração Automation Anywhere

Quando o monitor encontra uma nota apta à escrituração (`SUCESSO`), ele aciona
automaticamente o bot RPA correspondente no **Automation Anywhere Control Room A360**,
agendando a execução para daqui **3 minutos** num runner livre.

### 9.1 Lógica de guard (antes de truncar)

Ao iniciar cada ciclo, o monitor verifica se algum bot de escrituração já está ativo
no Control Room. Se sim, **aborta o ciclo inteiro** sem truncar nem consultar o SAP —
preservando os dados da execução em andamento até a próxima janela do Task Scheduler.

### 9.2 Mapeamento processo → bot

| Processo | `aa_file_id` | Bot AA |
|---|---|---|
| `V2_Consulta_Comp_CTRFIXO` | `1211403` | `MainEscriturarNotaComplementoFixo` |
| `V2_Consulta_Comp_CTR_S_FIXACAO` | `1266717` | `MainEscriturarNotaComplementoSemFixacao` |
| `V2_Consulta_Comp_CTR_C_FIXACAO` | `1233302` | `MainEscriturarNotaComplementoComFixacao` |
| `V2_Consulta_Comp_ARMAZEN` | `1310535` | `MainEscriturarNotaComplementoDeposito` |
| `V2_Consulta_Comp_VALOR` | *(pendente — bot ainda não criado no AA)* | `MainEscriturarNotaComplementoValor` (a criar) |

### 9.3 Seleção de runner

| Prioridade | ID | Username | Papel |
|---|---|---|---|
| 1 (principal) | `8635` | `bot04_runner_aws` | Usado se livre |
| 2 (fallback) | `9307` | `bot05_runner_ws` | Usado se candidato 1 ocupado |

Se ambos estiverem ocupados, o agendamento é ignorado e registrado no log como warning.

### 9.4 Agendamento (não disparo imediato)

O bot **nunca é disparado imediatamente**. O monitor cria um agendamento one-time
via `POST /v2/schedule/automations` para daqui 3 minutos, garantindo que a tabela
`complemento_notas_escrituracao` já esteja populada quando o RPA for ler.

```
Monitor encontra aptas → salva no Postgres → schedule_bot(file_id, runner, +3min)
```

### 9.5 Componentes

| Arquivo | Papel |
|---|---|
| `src/connectors/automation_anywhere_connector.py` | Cliente completo: auth, circuit breaker, retry, `is_bot_running`, `is_runner_busy`, `pick_runner`, `any_bot_running`, `schedule_bot` |
| `src/connectors/automation_anywhere_metrics.py` | Status buckets (RUNNING / WAITING / FAILED / COMPLETED) |
| `src/orchestration/application.py` | `_aa_guard_check()` (início do ciclo) + `_schedule_aa_safe()` (após save) |
| `docs/automation_anywhere.md` | Documentação completa do módulo AA portado do CONTROLE_JOBS_AA |

---

## 10. Como rodar

```powershell
& ".\.ESCR_SAPvenv\Scripts\python.exe" main.py
```

> ⚠️ Um ciclo completo **grava em produção** (`prod`) e **dispara o Teams** (se
> `POWER_AUTOMATE_TEAMS_URL` estiver configurado). Use com consciência do efeito.
> `main.py` executa **1 ciclo** e encerra; a recorrência é externa (planejado:
> Agendador de Tarefas do Windows).

Para rodar sem notificar o Teams, basta deixar `POWER_AUTOMATE_TEAMS_URL` vazio no `.env`.

### Recriar o ambiente do zero (se o venv sumir)

```powershell
python -m venv .ESCR_SAPvenv
.\.ESCR_SAPvenv\Scripts\python.exe -m pip install --upgrade pip
.\.ESCR_SAPvenv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

---

## 11. O que o pipeline faz (passo a passo)

1. **Valida conexões** com HANA e PostgreSQL (teste de query simples em cada).
2. **Carrega processos ativos** de `config/processes.yaml`.
3. **Trunca a tabela de resultado** (`complemento_notas_escrituracao`) em `dev` e `prod` —
   uma única vez antes do loop, garantindo que cada ciclo reflita apenas o estado atual.
4. Para cada processo:
   a. **Lê a fila** PostgreSQL (status `12`/`13` ou `01` para VALOR) via SQL file;
      cockpits separados por `|` são explodidos em linhas individuais (`CROSS JOIN LATERAL`).
   b. Para cada linha da fila, **consulta o HANA**: 3 CTEs (`zmmt_base`, `ctr`,
      `vtin_fallback`) → retorna `DOCNUM`, `MIRO_DATA`, `RESULTADO` e metadados
      via `UNION ALL` VIA_MIRO (determinístico) + VIA_CPF_MATCH (fallback fuzzy).
   c. Consolida em DataFrame com `process_name`, `data_execucao`,
      `status_execucao` (`SUCESSO` / `SEM_RETORNO` / `ERRO`), `tempo_execucao`.
5. **Exporta Excel** em `data/output/{process_name}/{process_name}_YYYYMMDD_HHMMSS.xlsx`.
6. **Normaliza** o DataFrame (colunas UPPERCASE com `psycopg.sql.Identifier`).
7. **Filtra aptas** (`DOCNUM` vazio = nota pendente de escrituração) e faz **UPSERT** em
   `dev.complemento_notas_escrituracao` e `prod.complemento_notas_escrituracao`
   (84 colunas; cria tabela se não existir).
8. **Agenda bot AA** (`schedule_bot`) para +3 min se há aptas — após confirmação que
   a tabela já foi gravada.
9. **Monta `ExecutionSummary`** com KPIs (aptas / pendentes / erros / duração).
10. **Loga** o resumo e envia **Adaptive Card** ao Teams (card por processo com badge
    colorido + barra de totais com TOTAL/APTAS/PENDENTES).

---

## 12. Testes

```powershell
& ".\.ESCR_SAPvenv\Scripts\python.exe" -m pytest -q
```

Rodar **sempre antes e depois de qualquer mudança** — a suíte golden trava o
comportamento observável completo.

- **`tests/golden/`** — testes de caracterização: travam o DataFrame consolidado,
  a sequência exata de chamadas de gravação e o payload do Teams. Snapshots em
  `tests/fixtures/golden/snapshots/`. Rodam 100% com conectores **fake** — não
  tocam SAP/Postgres/Teams.
- **`tests/unit/`** — normalização de colunas, mapeamento de tipos SQL, DDL,
  `execution_summary`, enums, settings, `ProcessLoader`, superfície de import.

---

## 13. Logs

- **loguru** (`src/utils/logger.py`).
- **Console:** `INFO`, colorido.
- **Arquivo:** `logs/SAP_ESCRITURAR_V2_AAAA-MM-DD.log`, `DEBUG`, rotação diária,
  retenção configurável.

---

## 14. Backlog

### Fase 2 — correções de negócio (branch `refactor/escrituracao-v2`)

Itens já corrigidos e validados nos sistemas reais:

- ✅ `YEAR=2026` hardcoded → parametrizado via `SAFRA_ANO` no `.env` (`SapConfig.safra_ano`; padrão = ano corrente se omitido)
- ✅ DDL com f-string → `psycopg.sql.Identifier` + rollback em `PostgresConnector`
- ✅ `TO_NUMBER(zmmt.ID)` → `LTRIM(zmmt.ID,'0') = LTRIM(?,'0')` nos 3 SQL HANA
- ✅ Gravação append-only → UPSERT com índice único em `complemento_notas_escrituracao`
  (`_migra_dedup.py <schema> --apply` dedupou dev e prod: 7.617 → 1.451 linhas)
- ✅ `COALESCE(QTDE/VALOR, 0)` removido do match (evitava falso match com NULL/zero)
- ✅ Split de cockpit com `DISTINCT` nas 5 filas Postgres
- ✅ Regra de valor `CTR_S_FIXACAO` validada: afrouxar não recupera nenhuma nota
  real — **não alterado** (gargalo é existência da NF, não o valor)
- ✅ Truncate da tabela de resultado no início de cada ciclo (`Application.run()`),
  garantindo que `complemento_notas_escrituracao` reflita apenas os dados do ciclo atual
- ✅ `CODESTA='100'` (NF-e autorizada) corrigido de `'101'` (inutilização — 45k registros incorretos)
- ✅ `YEAR(VTIN_DT_EMISSAO)` corrigido de `VTIN_DT_CRIACAO` (data de entrada no sistema)
- ✅ `UNION ALL VIA_MIRO + VIA_CPF_MATCH` em todos os 5 SQLs HANA — caminho determinístico
  (MIRO_DOC → J_1BNFDOC → DOCNUM) + fallback fuzzy (CPF+QTDE+VALOR quando MIRO_DOC vazio)
- ✅ DDL fixo 84 colunas UPPERCASE (`src/config/ddl_complemento.py`) — tabela sempre criada com
  todas as colunas, mesmo quando nenhum registro retorna apto no ciclo; +1 coluna `CRENAM`
- ✅ Campo `CRENAM` nos 5 SQLs HANA + DDL — SAP user que postou o documento fiscal
  (`J_1BNFDOC.CRENAM`); adicionado nas 3 posições por arquivo (CTE, VIA_MIRO, VIA_CPF_MATCH)
- ✅ **Lógica de aptidão CORRIGIDA** — `DOCNUM` **vazio** = apto (pendente de escrituração);
  preenchido = já foi escriturado → ignorado. VIA_MIRO: `INNER JOIN J_1BNFDOC` → `LEFT JOIN`
  + `WHERE doc.DOCNUM IS NULL OR doc.DOCNUM = ''`. VIA_CPF_MATCH: `AND (vtin_fallback.DOCNUM IS NULL
  OR vtin_fallback.DOCNUM = '')`. Python `df_aptas`: `isna()|==''` em vez de `notna()&!=''`
- ✅ Flag `AA_CALL_RPA` no `.env` — `false` desabilita guard check + agendamento de bots sem
  interromper o ciclo (consulta HANA, salva Postgres, notifica Teams)
- ✅ **Teams layout Opção B** — header com cor dinâmica por status (SUCESSO=verde, ERRO=vermelho, PARCIAL=laranja),
  card por processo com badge colorido, barra de totais com 3 mini-KPIs
- ✅ **5º processo VALOR** — novo tipo `V2_Consulta_Comp_VALOR` lendo `prod.complem_valor_fila`;
  match por CPF+QTDE sem filtro de valor (ZMMT0022.VALOR = centavos do complemento, não o total da NF)
- ✅ Integração Automation Anywhere — guard check antes do truncate + agendamento +3min após aptas salvas

Pendente:

- N+1 + `query_delay` — execução serial; requer reescrita de `ProcessRunner`
- `SPART='01'` hardcoded nos SQL HANA
- Retry (tenacity) nas consultas HANA
- Pré-filtro das CTEs `ctr`/`vtin_fallback` (varrem `EKKO`/`EKPO`/`VTIN` inteiro)
- `MANDT` não amarrado no join de compra (`EKKO`/`EKPO`)
- `aa_file_id` do processo VALOR (aguardando criação do bot no Control Room)

---

## 15. Pontos de atenção (gotchas)

- **`DOCNUM` vazio = apto; preenchido = já feito.** A tabela guarda notas PENDENTES,
  não confirmadas. Quando o bot escritura, o `DOCNUM` aparece no SAP e a nota sai da
  fila no próximo ciclo. Status `15` na fila Postgres **não garante escrituração** —
  validação em massa (585 itens): apenas 75% tinham `DOCNUM`. Critério real = SAP.
- **Produtor rural:** CPF fica no campo `STCD2` (não `STCD1`), com zeros à esquerda
  no VTIN — só casa com `LTRIM`.
- **`PONUMBER` descartado** como elo NF↔pedido em produtor rural (~93% vazio).
  O elo confiável é `chave_acesso` (44 dígitos) + match por cockpit.
- **Fila lida hardcoded de `prod`** nos SQLs Postgres — `PostgresConfig.schema`
  não afeta as queries de fila.
- **Resultado gravado em 2 schemas** (`dev` e `prod`) a cada ciclo — ambos ficam
  sincronizados automaticamente.
- **ZMMT0022 no fixo:** tem ~4,3 linhas por contrato (1 por `ID`/cockpit) com
  qtde/valor da **parcela**, não o total. Casar `ID == cockpit` resolve 75% dos casos.
- **Checkout antigo (append puro) viola o índice único** criado pela migração —
  sempre usar a versão com UPSERT após rodar `_migra_dedup.py`.
- **Processo VALOR — `ZMMT0022.VALOR` é o complemento, não o total da NF.**
  Para registros CFIN, `ZMMT0022.VALOR` representa a diferença em centavos (ex.: R$ 0,17),
  enquanto a NF real tem o valor total (ex.: R$ 915.919,83). O filtro de valor no
  VIA_CPF_MATCH foi removido neste processo — substituído por âncora de data (±90 dias).
  **Nunca reaplicar filtro de valor ao processo VALOR.** Nos demais processos
  (CTRFIXO, CTR_S, CTR_C, ARMAZEN) o filtro de valor é necessário e correto.
- **VIA_MIRO falha para CFIN:** `J_1BNFDOC.GJAHR ≠ ZMMT0022.MIRO_ANO` para complementos
  de valor — o BELNR existe em outros anos no SAP, não no ano do MIRO_ANO. O path
  VIA_MIRO está incluído no SQL mas não resolve para CFIN na prática.

---

## 16. Solução de problemas

| Sintoma | Provável causa / ação |
|---|---|
| `HdbError` / "connection refused" | HANA offline ou porta 30213 bloqueada — verificar `SAP_HOST`/`SAP_PORT` no `.env`. |
| `OperationalError` (Postgres) | Credenciais incorretas ou PostgreSQL inacessível — verificar `POSTGRES_*` no `.env`. |
| `SEM_RETORNO` em todos os itens | NF não existe no VTIN ainda **ou** `SAFRA_ANO` errado (filtra ano incorreto). Verificar `DOCNUM` manualmente no SAP. |
| Tabela inflando a cada ciclo | Índice único ausente — rodar `_migra_dedup.py <schema> --apply`. |
| `UniqueViolation` ao gravar | Código sem UPSERT (versão antiga) sendo usado após a migração — atualizar para o branch atual. |
| Teams não recebe notificação | `POWER_AUTOMATE_TEAMS_URL` vazio ou webhook inativo no Power Automate. |
| Testes falhando após mudança | Snapshots desatualizados — deletar o snapshot correspondente em `tests/fixtures/golden/snapshots/` e rodar `pytest` para regravar. |
