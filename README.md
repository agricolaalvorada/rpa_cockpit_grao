# SAP-ESCRITURACAO-V2 — Monitor de escrituração

Monitor recorrente que, a cada ciclo, lê filas de pedidos/contratos pendentes no
**PostgreSQL**, consulta o **SAP HANA** para verificar se a nota pode ser
escriturada (cruzando ZMMT0022 × VTIN por CPF/CNPJ + quantidade + valor),
consolida o resultado, grava nos schemas `dev` e `prod` (`tb_resultado_final_hana`),
exporta um Excel e notifica o Teams.

## Como executar

```bash
& ".\.ESCR_SAPvenv\Scripts\python.exe" main.py
```

> ⚠️ Um ciclo completo **grava em produção** (`prod`) e **dispara o Teams**. Use
> com consciência do efeito. `main.py` executa **1 ciclo** e encerra; a
> recorrência é externa (planejado: Agendador de Tarefas do Windows).

## Configuração

- **`.env`** (não versionado) — credenciais e parâmetros. Variáveis: `SAP_HOST`,
  `SAP_PORT`, `SAP_DATABASE`, `SAP_SCHEMA`, `SAP_USER`, `SAP_PASSWORD`,
  `SAP_CONNECTION_DELAY`, `SAP_QUERY_DELAY`; `POSTGRES_HOST`, `POSTGRES_PORT`,
  `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_SCHEMA`;
  `POWER_AUTOMATE_TEAMS_URL`; `LOG_LEVEL`, `LOG_SAVE_FILE`.
- **`config/processes.yaml`** — definição declarativa dos processos (nome, SQLs,
  parâmetros, tabela destino, flags). A ordem é preservada.

## Arquitetura

```
main.py                      # entrypoint fino -> Application().run()
config/processes.yaml        # processos (declarativo)
src/
  domain/                    # enums (status, estratégia) + models (Pydantic) + protocols — sem I/O
  config/                    # settings (Pydantic) + process_loader (YAML) + process_definitions (shim)
  connectors/                # HanaConnector, PostgresConnector
  services/                  # process_runner (fila->HANA->DataFrame), resultado_service (normaliza/grava)
  orchestration/             # application (orquestra o ciclo) + column_log
  utils/                     # logger, paths, execution_summary, teams_notifier
sql/                         # consultas PostgreSQL (fila) e SAP HANA (matching)
tests/                       # unit/ + golden/ (caracterização) + fixtures/
```

Fluxo de um ciclo: fila PostgreSQL → `ProcessRunner` consulta o HANA por linha →
DataFrame consolidado → `ResultadoService` exporta Excel e grava em `dev`+`prod` →
`build_execution_summary` → log + Teams.

## Testes

```bash
& ".\.ESCR_SAPvenv\Scripts\python.exe" -m pytest -q
```

- **`tests/golden/`** — testes de caracterização que travam o comportamento
  observável (DataFrame consolidado, sequência de gravação, payload). Os
  snapshots ficam em `tests/fixtures/golden/snapshots/`. Rodam 100% com
  conectores **fake** — não tocam SAP/Postgres/Teams.
- **`tests/unit/`** — normalização de colunas, mapeamento de tipos, DDL,
  execution_summary, enums, settings, loader, superfície de import.

## Backlog (Fase 2 — correções de negócio que mudam resultados)

Esta refatoração (Fase 1) **preservou o comportamento**. Itens conhecidos para a
Fase 2: dedup/upsert na gravação (hoje append-only, duplica a cada ciclo);
`YEAR=2026` hardcoded nos SQL HANA; `CTR_S_FIXACAO` idêntico ao `CTRFIXO` (regra
de valor do "a fixar"); `TO_NUMBER`/`LPAD` inconsistentes; `INNER JOIN`
`ZVS_BP_ID_FISCAL` vs `LEFT JOIN KNA1` (fornecedor sem cadastro some); N+1 +
`query_delay`; `SPART='01'` hardcoded; DDL com f-string → `psycopg.sql.Identifier`;
commit sem rollback; retry (tenacity) nas consultas.
