# SAP-ESCRITURACAO-V2 — Monitor de escrituração de notas de grãos

Pipeline de monitoramento em Python que, a cada ciclo, lê filas de pedidos/contratos
pendentes no **PostgreSQL**, consulta o **SAP HANA** para verificar se a NF-e pode
ser escriturada (cruzando `ZMMT0022` × `VTIN` por CPF/CNPJ + quantidade + valor),
consolida o resultado, grava via UPSERT nos schemas `dev` e `prod`
(`tb_resultado_final_hana`), exporta um Excel e notifica o Teams via Power Automate.

> **Status:** branch `refactor/escrituracao-v2` — Fase 1 (reestruturação em camadas) ✅
> + Fase 2 (correções de negócio validadas em prod) ✅. 4 processos ativos. 78 testes.
> **PR ainda não aberto.**

---

## 1. Objetivo

Automatizar a verificação de elegibilidade de escrituração das notas de grãos,
eliminando conferência manual:

1. Ler as filas de contratos/pedidos pendentes no PostgreSQL (status `12`/`13`).
2. Para cada item, consultar o SAP HANA: obter os valores esperados do cockpit
   via `ZMMT0022` e cruzar com a NF-e real no `VTIN` por CPF/CNPJ + quantidade + valor.
3. **Veredito:** `DOCNUM` preenchido em `J_1BNFE_ACTIVE` = **escriturada (SUCESSO)**;
   campo vazio = **ainda não escriturada (SEM_RETORNO)**.
4. Persistir o resultado no PostgreSQL (UPSERT) + exportar Excel.
5. Notificar o Teams com Adaptive Card separando notas aptas de pendentes.

> **Match = apta a escriturar; sem match = não pode** (NF inexistente no VTIN ou
> divergente do pedido — resposta de negócio válida, não erro de sistema). O status
> `15` na fila Postgres **não garante escrituração** — a verdade está sempre no SAP.

---

## 2. Resumo técnico

| Item | Valor |
|---|---|
| **Linguagem / runtime** | Python **3.11.9** (venv `.ESCR_SAPvenv`) |
| **Banco de fila** | PostgreSQL 10.1.1.36:5432 · db `postgres` · schema `prod` |
| **Banco HANA** | SAP HANA 10.2.3.244:30213 · db `ECP` · schema `SAPABAP1` · user `POWERBI` |
| **Processos ativos** | `CTRFIXO` (compra fixo) · `CTR_S_FIXACAO` (sem fixação) · `CTR_C_FIXACAO` (com fixação) · `ARMAZEN` (venda) |
| **Critério de escrituração** | `DOCNUM` preenchido em `J_1BNFE_ACTIVE` |
| **Tabela de resultado** | `tb_resultado_final_hana` (schemas `dev` e `prod`) |
| **Estratégia de gravação** | Truncate da tabela no início de cada ciclo + UPSERT com índice único por `(process_name, doc_compra, n_contrato, numero_cockpit, docnum, status_execucao)` |
| **Export** | Excel em `data/output/{process_name}/` |
| **Notificação** | Adaptive Card → Teams via `POWER_AUTOMATE_TEAMS_URL` (Power Automate) |
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

Os 4 processos são definidos em [`config/processes.yaml`](config/processes.yaml) e
carregados dinamicamente por `ProcessLoader`. A ordem é preservada (afeta o payload
do Teams).

| `process_name` | Tipo de contrato | Parâmetros HANA | Fila PostgreSQL (entrada) | Tabela de resultado (saída) |
|---|---|---|---|---|
| `V2_Consulta_Comp_CTRFIXO` | Compra com preço fixo | `doc_compra`, `numero_cockpit` | `prod.complemento_quantidade_fixo_fila` | `dev/prod.tb_resultado_final_hana` |
| `V2_Consulta_Comp_CTR_S_FIXACAO` | Compra sem fixação ("a fixar") | `doc_compra`, `numero_cockpit` | `prod.complemento_quantidade_sem_fixacao_fila` | `dev/prod.tb_resultado_final_hana` |
| `V2_Consulta_Comp_CTR_C_FIXACAO` | Compra com fixação | `doc_compra`, `numero_cockpit` | `prod.complemento_quantidade_com_fixacao_fila` | `dev/prod.tb_resultado_final_hana` |
| `V2_Consulta_Comp_ARMAZEN` | Venda / armazém | `n_contrato`, `numero_cockpit` | `prod.complemento_quantidade_deposito_fila` | `dev/prod.tb_resultado_final_hana` |

Cada fila usa `CROSS JOIN LATERAL regexp_split_to_table(numero_cockpit, '\|')` para
explodir cockpits compostos em linhas individuais — uma consulta HANA por cockpit.

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
  connectors/                # HanaConnector (retry automático) · PostgresConnector (DDL/DML/UPSERT)
  services/                  # ProcessRunner (fila → HANA → DataFrame)
  │                          # + ResultadoService (normaliza · Excel · UPSERT Postgres)
  orchestration/             # Application (orquestra o ciclo) · column_log
  utils/                     # logger · paths · execution_summary · teams_notifier
sql/
  postgres/consultas/        # 3 SQLs de leitura de fila (Consulta_Comp_*.sql)
  sap_hana/consultas/        # 3 SQLs HANA (estrutura: CTEs zmmt_base / ctr / vtin2)
tests/
  golden/                    # testes de caracterização (travam DataFrame, seq. gravação, payload)
  unit/                      # normalização, DDL, enums, settings, loader, import surface
  fixtures/golden/snapshots/ # snapshots JSON dos testes golden
```

**Fluxo de um ciclo:**

```
PostgreSQL (fila prod)
  └─► ProcessRunner.run(processo)
        ├─ executa SQL Postgres → DataFrame de itens (cockpit explodido)
        └─ para cada linha → HanaConnector.execute_query(SQL HANA, params)
                                  │
                                  ▼
                        DataFrame consolidado
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   ResultadoService.exportar_excel()   ResultadoService.salvar_no_postgres()
   data/output/{processo}/              UPSERT em dev.tb_resultado_final_hana
   {processo}_YYYYMMDD_HHMMSS.xlsx      UPSERT em prod.tb_resultado_final_hana
              │
              ▼
   build_execution_summary() → log + Teams (Adaptive Card)
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
| Tabela de resultado | `tb_resultado_final_hana` |

A tabela de resultado é **criada automaticamente** se não existir; colunas novas são
adicionadas via `ADD COLUMN IF NOT EXISTS`. Os 4 processos compartilham a mesma
tabela (colunas levemente diferentes entre processos).

**Índice único** (criado por `_migra_dedup.py`):

```sql
CREATE UNIQUE INDEX ix_uq_tb_resultado_final_hana
ON tb_resultado_final_hana (
    process_name,
    COALESCE(doc_compra, ''),
    COALESCE(n_contrato, ''),
    COALESCE(numero_cockpit, ''),
    COALESCE(docnum, ''),
    status_execucao
);
```

> ⚠️ Não usar código de versão anterior (append puro) após a migração — viola o índice único.

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

# --- Log ---
LOG_LEVEL=INFO
LOG_SAVE_FILE=true
```

> `SAFRA_ANO` substitui o filtro `YEAR(VTIN_DT_CRIACAO)` nas 3 queries HANA. Se omitido,
> usa o ano corrente automaticamente — **não é necessário atualizar anualmente**.

Processos são configurados em [`config/processes.yaml`](config/processes.yaml)
(nome, caminhos SQL, parâmetros, tabela destino, flags `truncate_before_insert` /
`drop_and_create`). A ordem é preservada e afeta o payload do Teams.

---

## 9. Como rodar

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

## 10. O que o pipeline faz (passo a passo)

1. **Valida conexões** com HANA e PostgreSQL (teste de query simples em cada).
2. **Carrega processos ativos** de `config/processes.yaml`.
3. **Trunca a tabela de resultado** (`tb_resultado_final_hana`) em `dev` e `prod` —
   uma única vez antes do loop, garantindo que cada ciclo reflita apenas o estado atual.
4. Para cada processo:
   a. **Lê a fila** PostgreSQL (status `12`/`13`) via SQL file; cockpits separados
      por `|` são explodidos em linhas individuais (`CROSS JOIN LATERAL`).
   b. Para cada linha da fila, **consulta o HANA**: 3 CTEs (`zmmt_base`, `ctr`,
      `vtin2`) → retorna `DOCNUM`, `MIRO_DATA`, `RESULTADO` e metadados.
   c. Consolida em DataFrame com `process_name`, `data_execucao`,
      `status_execucao` (`SUCESSO` / `SEM_RETORNO` / `ERRO`), `tempo_execucao`.
5. **Exporta Excel** em `data/output/{process_name}/{process_name}_YYYYMMDD_HHMMSS.xlsx`.
6. **Normaliza** o DataFrame (colunas lowercase, sem acento, sem caracteres inválidos).
7. **UPSERT** em `dev.tb_resultado_final_hana` e `prod.tb_resultado_final_hana`
   (cria tabela/colunas se necessário; atualiza linha existente ou insere nova).
8. **Monta `ExecutionSummary`** com KPIs (aptas / pendentes / erros / duração).
9. **Loga** o resumo e envia **Adaptive Card** ao Teams separando notas aptas
   de pendentes por processo.

---

## 11. Testes

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

## 12. Logs

- **loguru** (`src/utils/logger.py`).
- **Console:** `INFO`, colorido.
- **Arquivo:** `logs/SAP_ESCRITURAR_V2_AAAA-MM-DD.log`, `DEBUG`, rotação diária,
  retenção configurável.

---

## 13. Backlog

### Fase 2 — correções de negócio (branch `refactor/escrituracao-v2`)

Itens já corrigidos e validados nos sistemas reais:

- ✅ `YEAR=2026` hardcoded → parametrizado via `SAFRA_ANO` (`SapConfig.safra_ano`)
- ✅ DDL com f-string → `psycopg.sql.Identifier` + rollback em `PostgresConnector`
- ✅ `TO_NUMBER(zmmt.ID)` → `LTRIM(zmmt.ID,'0') = LTRIM(?,'0')` nos 3 SQL HANA
- ✅ Gravação append-only → UPSERT com índice único em `tb_resultado_final_hana`
  (`_migra_dedup.py <schema> --apply` dedupou dev e prod: 7.617 → 1.451 linhas)
- ✅ `COALESCE(QTDE/VALOR, 0)` removido do match (evitava falso match com NULL/zero)
- ✅ Split de cockpit com `DISTINCT` nas 3 filas Postgres
- ✅ Regra de valor `CTR_S_FIXACAO` validada: afrouxar não recupera nenhuma nota
  real — **não alterado** (gargalo é existência da NF, não o valor)
- ✅ Truncate da tabela de resultado no início de cada ciclo (`Application.run()`),
  garantindo que `tb_resultado_final_hana` reflita apenas os dados do ciclo atual

Pendente:

- N+1 + `query_delay` — execução serial; requer reescrita de `ProcessRunner`
- `SPART='01'` hardcoded nos SQL HANA
- Retry (tenacity) nas consultas HANA
- Pré-filtro das CTEs `ctr`/`vtin2` (varrem `EKKO`/`EKPO`/`VTIN` inteiro)
- `MANDT` não amarrado no join de compra (`EKKO`/`EKPO`)

---

## 14. Pontos de atenção (gotchas)

- **Status `15` na fila ≠ escriturado.** Em validação em massa (585 itens): apenas
  75% tinham `DOCNUM` preenchido. Critério real = `DOCNUM` no SAP.
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

---

## 15. Solução de problemas

| Sintoma | Provável causa / ação |
|---|---|
| `HdbError` / "connection refused" | HANA offline ou porta 30213 bloqueada — verificar `SAP_HOST`/`SAP_PORT` no `.env`. |
| `OperationalError` (Postgres) | Credenciais incorretas ou PostgreSQL inacessível — verificar `POSTGRES_*` no `.env`. |
| `SEM_RETORNO` em todos os itens | NF não existe no VTIN ainda **ou** `SAFRA_ANO` errado (filtra ano incorreto). Verificar `DOCNUM` manualmente no SAP. |
| Tabela inflando a cada ciclo | Índice único ausente — rodar `_migra_dedup.py <schema> --apply`. |
| `UniqueViolation` ao gravar | Código sem UPSERT (versão antiga) sendo usado após a migração — atualizar para o branch atual. |
| Teams não recebe notificação | `POWER_AUTOMATE_TEAMS_URL` vazio ou webhook inativo no Power Automate. |
| Testes falhando após mudança | Snapshots desatualizados — deletar o snapshot correspondente em `tests/fixtures/golden/snapshots/` e rodar `pytest` para regravar. |
