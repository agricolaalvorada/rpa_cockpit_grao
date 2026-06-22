# Automation Anywhere (Control Room A360) — Conhecimento + Módulo

Transferência de conhecimento do backend do projeto **CONTROLE_JOBS_AA** (módulo de Automation
Anywhere) para este projeto, + o **cliente robusto** portado para cá. Objetivo: poder **acionar
robôs** (e, se quiser, consultar execuções) com o mesmo nível de robustez do projeto de origem.

---

## 1. Visão geral

O Control Room (A360 Cloud/on-prem) expõe uma **API REST**. Todo acesso segue 2 passos:

1. **Autenticar** → recebe um *token* (JWT) com validade (`tokenExpiresIn`, em segundos).
2. **Chamar os endpoints** com o header **`X-Authorization: <token>`** (note: NÃO é `Authorization: Bearer`).

No CONTROLE_JOBS_AA esse módulo é só de **monitoramento** (coleta execuções/inventário/auditoria
e serve do banco). O **disparo de robô** (`POST /v3/automations/deploy`) foi adicionado aqui, porque
é o que este projeto precisa — reaproveitando o mesmo fluxo de auth/robustez.

---

## 2. Autenticação (padrão comprovado)

```
POST {AA_AUTH_PATH}            # default /v1/authentication; alguns CRs usam /v2/authentication
Body: {"username": "...", "password": "..."}        # ou {"username","apiKey"}
Resp: {"token": "eyJ...", "tokenExpiresIn": 1500}
```

- O token é **cacheado** pela validade (com folga de 60s) e **renovado automaticamente em HTTP 401**.
- No CONTROLE_JOBS_AA o cache fica no **Redis** (compartilhado entre worker e réplicas).
- Aqui (sem Redis) o cache é **em memória, por instância** do conector — suficiente para um processo/script.

---

## 3. Robustez do cliente (o que vale copiar)

O `client.py` original embute padrões que evitam derrubar a integração quando o CR oscila. Portados
para `src/connectors/automation_anywhere_connector.py`:

| Padrão | Original (CONTROLE_JOBS_AA) | Aqui (SAP-ESCRITURACAO-V2) |
|---|---|---|
| Cache de token | Redis (TTL do CR − 60s) | memória por instância |
| Re-auth em 401 | sim | sim |
| Retry exponencial | 0.5/1/2s em rede + 502/503/504 | idem |
| Circuit breaker | 5 falhas/60s → abre 300s; half-open 1 sondagem/30s (Redis) | idem, em memória |
| Pool de conexão | httpx HTTP/2 keep-alive | `requests.Session` (keep-alive) |
| Métricas Prometheus | sim (`aa_api_*`) | omitido (este projeto não usa Prometheus) |

> Por que circuit breaker importa: sem ele, um CR fora do ar faz cada chamada esperar o timeout e
> empilha retries — o breaker "abre" e falha rápido até o CR voltar.

---

## 4. Catálogo de endpoints do Control Room

Consolidado do módulo de origem (todos usam `X-Authorization`). Os de **monitoramento** são opcionais
aqui; o de **disparo** é o que você precisa.

| Endpoint | Método | Para quê |
|---|---|---|
| `/v1/authentication` (ou `/v2/authentication`) | POST | Autenticar → token |
| **`/v3/automations/deploy`** | **POST** | **Disparar um bot** → `{deploymentId}` |
| `/v3/activity/list` | POST | Listar execuções/atividades (filtro por status, data, `deploymentId`…) |
| `/v3/activity/log` (ou `/v1/activity/execution/{id}/log`) | POST/GET | Logs de uma execução |
| `/v2/repository/file/list` | POST | Descobrir o `fileId` do bot pelo nome |
| `/v2/repository/workspaces/{public\|private}/files/list` | POST | Inventário de bots/pastas |
| `/v2/schedule/automations/list` | POST | Agendamentos |
| `/v2/devices/list` | GET/POST | Devices (bot runners) |
| `/v3/wlm/queues/list` | GET/POST | Filas (work items) |
| `/v1/usermanagement/users/list` | GET/POST | Usuários |
| `/v1/audit/messages/list` | POST | Trilha de auditoria |

**Corpo típico do `/v3/activity/list`** (paginação + filtro):
```json
{
  "filter": {"operator": "eq", "field": "deploymentId", "value": "<id>"},
  "sort": [{"field": "startDateTime", "direction": "desc"}],
  "page": {"offset": 0, "length": 100}
}
```

**Disparo (`/v3/automations/deploy`):**
```json
{"fileId": 1234, "runAsUserIds": [567], "poolIds": [], "overrideDefaultDevice": false}
```
→ `{"deploymentId": "<uuid>"}`

---

## 5. Status do Control Room → 4 buckets

Portado em `src/connectors/automation_anywhere_metrics.py`. O CR tem ~12 status; reduza a 4 buckets:

- **RUNNING**: `RUNNING, RUN_PAUSED, UPDATE, STARTED`
- **WAITING**: `QUEUED, PENDING_EXECUTION, DEPLOYED`
- **FAILED**: `RUN_FAILED, RUN_TIMED_OUT, RUN_ABORTED, FAILED, PENDING_FAILURE, DEPLOY_FAILED, FAILED_TO_DEPLOY`
- **COMPLETED**: `RUN_COMPLETED, COMPLETED`
- qualquer outro → **OTHER** (use `unknown_statuses()` para detectar status novos sem silenciar)

`bucket_for_status()`, `summarize_status_counts()`, `derive_department(path)` (extrai o depto do path
`...\Bots\<DEPT>\...`) e `clamp_pct()` estão no módulo de metrics.

---

## 6. Princípio de dados do projeto de origem (REQ-0657) — lição de arquitetura

> **Servir do NOSSO banco, não buscar na fonte a cada request.**

No CONTROLE_JOBS_AA, **coletores** (no worker) batem no Control Room periodicamente e **persistem
snapshots**; os endpoints de leitura **servem do snapshot** (latência estável mesmo com o CR lento).
Live só sob refresh explícito.

Se este projeto evoluir para **monitorar** execuções (não só disparar), siga o mesmo princípio:
um job coleta `/v3/activity/list` e grava no Postgres/HANA local; a UI/relatório lê do banco.

Cadência dos coletores na origem (referência): live 60s · executions 5min · inventory/audit/schedules
10min · devices/queues/users 15min. Cada coletor pega um lock (evita execução concorrente).

---

## 7. Mapa do módulo na origem (referência — o que é possível)

Caso queira replicar mais do módulo no futuro:

- **Integração** `backend/app/integrations/aa/`: `client.py` (auth/CB/retry/pool), `metrics.py` (status).
- **Coletores** `backend/app/services/aa_*_collector.py` + `aa_metrics_service.py` (camada de consulta),
  `aa_incidents_service.py` (6 detectores de incidente).
- **Models** (7 tabelas) `backend/app/models/aa_*.py`: execution / inventory / audit / schedule /
  device / queue / user snapshot — todas com `data_source_id` + chave natural + `collected_at` + `payload_json`.
- **API** `backend/app/api/v1/aa.py`: ~25 endpoints (overview, executions, pulse, trend, analytics, incidents…).
- **Credenciais**: model `DataSource` (tipo `AA_CONTROL_ROOM`) com `host`/`username`/senha **cifrada (Fernet)**;
  `DataSourceService.get_credentials()` decifra para os coletores. Nunca exposta em resposta de API.

---

## 8. O que foi portado para ESTE projeto

| Arquivo | Conteúdo |
|---|---|
| `src/connectors/automation_anywhere_connector.py` | Cliente robusto (auth + token-cache + retry + circuit breaker) + `get_json`/`post_json` genéricos + `run_bot`/`run_bot_and_wait`/`wait_for_completion`/`get_activity`/`find_files`. |
| `src/connectors/automation_anywhere_metrics.py` | Status buckets, `bucket_for_status`, `derive_department`, `summarize_status_counts`, `clamp_pct`. |
| `src/config/settings.py` | `AutomationAnywhereConfig` (frozen, `from_env`/`validate`) + instância `aa_config`. |
| `src/connectors/README_automation_anywhere.md` | Quickstart de uso. |

### Configuração (`.env`)
```dotenv
AA_CONTROL_ROOM_URL=https://SEU-CR.automationanywhere.digital
AA_USERNAME=usuario_api
AA_PASSWORD=...            # ou AA_API_KEY=...
AA_VERIFY_SSL=true
AA_TIMEOUT=60
AA_AUTH_PATH=/v1/authentication   # use /v2/authentication se /v1 der 404
```

### Uso
```python
from src.config.settings import aa_config
from src.connectors.automation_anywhere_connector import AutomationAnywhereConnector

aa = AutomationAnywhereConnector(aa_config)
aa.test_connection()                                   # valida URL/credenciais

# achar o fileId (uma vez):
for f in aa.find_files("NomeDoBot"):
    print(f["id"], f["name"], f.get("path"))

# disparar:
deployment_id = aa.run_bot(file_id=1234, run_as_user_ids=[567])
# disparar e aguardar:
atividade = aa.run_bot_and_wait(file_id=1234, run_as_user_ids=[567], timeout=900)
print(atividade["status"])

# chamar qualquer endpoint do CR diretamente:
execucoes = aa.post_json("/v3/activity/list", {"page": {"length": 50, "offset": 0}})

aa.close()
```

`run_as_user_ids` = ids dos *Run-as users* do Control Room (Administration → Users/Devices, ou via
`POST /v3/devices/runasusers/list`). Em geral é fixo por ambiente — guarde em config/processo.
