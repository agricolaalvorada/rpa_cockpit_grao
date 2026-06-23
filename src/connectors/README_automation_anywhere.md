# Conector Automation Anywhere (Control Room A360)

Aciona (deploy) um robô do Automation Anywhere a partir deste projeto e, opcionalmente,
acompanha a execução até concluir.

> 📖 **Conhecimento completo** (arquitetura do módulo AA do CONTROLE_JOBS_AA, cliente robusto,
> catálogo de endpoints do Control Room, status buckets, princípio serve-from-snapshot, models e
> coletores): veja [`docs/automation_anywhere.md`](../../docs/automation_anywhere.md).

Conhecimento reaproveitado do projeto **CONTROLE_JOBS_AA**
(`backend/app/integrations/aa/client.py` + `metrics.py`) — autenticação, **cliente robusto**
(cache de token, **circuit breaker**, retry, re-auth em 401) e mapeamento de status — adaptado ao
padrão deste projeto (síncrono, `requests`, config Pydantic). Os helpers de status estão em
`src/connectors/automation_anywhere_metrics.py`.

> Importante: o CONTROLE_JOBS_AA só **monitora** o AA (coleta execuções/auditoria/inventário);
> ele **não dispara** bots. O disparo (`POST /v3/automations/deploy`) foi adicionado aqui,
> reaproveitando o mesmo fluxo de auth (`/vX/authentication` → token → header `X-Authorization`).

## 1. Variáveis no `.env`

```dotenv
AA_CONTROL_ROOM_URL=https://SEU-CONTROLROOM.automationanywhere.digital
AA_USERNAME=usuario_api
# use senha OU api key (api key tem precedência):
AA_PASSWORD=sua_senha
# AA_API_KEY=sua_api_key
AA_VERIFY_SSL=true
AA_TIMEOUT=60
# alguns Control Rooms usam /v2/authentication — troque se /v1 retornar 404:
AA_AUTH_PATH=/v1/authentication
```

A config é lida automaticamente em `src/config/settings.py` (`aa_config`).

## 2. Uso

```python
from src.config.settings import aa_config
from src.connectors.automation_anywhere_connector import AutomationAnywhereConnector

aa = AutomationAnywhereConnector(aa_config)

# valida URL/credenciais (opcional)
aa.test_connection()

# (A) só disparar (fire-and-forget):
deployment_id = aa.run_bot(file_id=1234, run_as_user_ids=[567])

# (B) disparar e aguardar concluir:
atividade = aa.run_bot_and_wait(file_id=1234, run_as_user_ids=[567], timeout=900)
print(atividade["status"])   # COMPLETED / RUN_FAILED / ...

aa.close()
```

`run_bot_and_wait` (e `wait_for_completion`) levantam `AutomationAnywhereError` se o bot
terminar em status de falha ou estourar o `timeout`.

## 3. Como descobrir `file_id` e `run_as_user_ids` (uma vez)

- **fileId** (o bot no repositório):
  ```python
  for f in aa.find_files("NomeDoSeuBot"):
      print(f["id"], f["name"], f.get("path"))
  ```
- **runAsUserIds**: são os *Run-as users* (usuário + device) cadastrados no Control Room.
  Pegue no Control Room (Administration → Users / Devices) ou via API
  (`POST /v3/devices/runasusers/list` no seu CR). Em geral é um id numérico fixo por ambiente —
  coloque-o numa constante/config do processo.

Depois de descobertos, fixe-os na configuração do processo (ex.: `config/processes.yaml` ou
um campo dedicado) para não consultar toda vez.

## 4. O que o conector faz

| Método | Para quê |
|---|---|
| `connect()` / `close()` | sessão HTTP + token (auth automática) |
| `test_connection()` | valida URL + credenciais |
| `get_json(path, params)` / `post_json(path, body)` | chamam **qualquer** endpoint do Control Room (com auth + retry + circuit breaker) |
| `run_bot(file_id, run_as_user_ids, ...)` | **dispara** o bot → retorna `deploymentId` |
| `get_activity(deployment_id)` | status atual da execução |
| `wait_for_completion(deployment_id, timeout, poll_interval)` | aguarda terminar |
| `run_bot_and_wait(...)` | dispara **e** aguarda |
| `find_files(name_contains)` | descobre o `fileId` do bot pelo nome |

## 5. Endpoints do Control Room usados

- `{AA_AUTH_PATH}` (default `/v1/authentication`) — autenticar (`{username, password|apiKey}` → `{token, tokenExpiresIn}`)
- `POST /v3/automations/deploy` — disparar o bot (→ `deploymentId`)
- `POST /v3/activity/list` — status da execução (filtra por `deploymentId`)
- `POST /v2/repository/file/list` — descobrir o `fileId`

Token é cacheado em memória pelo TTL devolvido (folga de 60s) e renovado automaticamente em `401`;
há retry em erros de rede e `5xx`.
