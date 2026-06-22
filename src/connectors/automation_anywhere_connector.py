# -*- coding: utf-8 -*-
"""Conector do Automation Anywhere Control Room (A360) — cliente robusto + disparo de robô.

Portado e adaptado de CONTROLE_JOBS_AA (`backend/app/integrations/aa/client.py`),
no padrão deste projeto (síncrono, `requests`, config Pydantic em src/config/settings.py).

Robustez reaproveitada do projeto original:
  - Autenticação: POST {auth_path} com {username, password|apiKey} -> {token, tokenExpiresIn}.
    Token cacheado EM MEMÓRIA pelo TTL devolvido (folga de 60s) e renovado em 401.
  - Retry exponencial (0.5/1/2s) em erros de rede e 5xx transitórios (502/503/504).
  - Circuit breaker EM MEMÓRIA: 5 falhas em 60s abrem o circuito por 300s; half-open
    libera 1 sondagem a cada 30s (evita martelar um Control Room fora do ar).
  - Header `X-Authorization: <token>` em toda chamada; `requests.Session` reusa a conexão TLS.

Diferenças vs. o original: lá o cache de token e o circuit breaker vivem no Redis (compartilhados
entre réplicas/worker); aqui são por-instância em memória (este projeto não usa Redis).

API genérica + operações de bot:
  - get_json(path, params) / post_json(path, body)  -> chamam QUALQUER endpoint do CR.
  - run_bot(...) / run_bot_and_wait(...)            -> disparam o robô (POST /v3/automations/deploy).
  - get_activity(...) / wait_for_completion(...)    -> acompanham a execução (/v3/activity/list).
  - find_files(name_contains)                       -> descobrem o fileId do bot (/v2/repository/file/list).

Uso típico:
    from src.config.settings import aa_config
    from src.connectors.automation_anywhere_connector import AutomationAnywhereConnector

    aa = AutomationAnywhereConnector(aa_config)
    deployment_id = aa.run_bot(file_id=1234, run_as_user_ids=[567])
    resultado = aa.wait_for_completion(deployment_id)   # opcional
    print(resultado["status"])                          # COMPLETED / RUN_FAILED / ...
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

import requests

from src.config.settings import AutomationAnywhereConfig
from src.connectors.automation_anywhere_metrics import TERMINAL_STATUSES, FAILED_STATUSES

# Circuit breaker (espelha CONTROLE_JOBS_AA/REQ-0364).
CB_FAIL_THRESHOLD = 5
CB_WINDOW_SECONDS = 60
CB_OPEN_SECONDS = 300
CB_PROBE_INTERVAL = 30


def normalize_control_room_url(url: str) -> str:
    """Remove paths de SPA (#/login, /#/...) e barras finais, mantendo só scheme://host[:port]."""
    cleaned = (url or "").strip().split("#", 1)[0].rstrip("/")
    parts = urlsplit(cleaned)
    if not parts.scheme or not parts.netloc:
        return cleaned
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


class AutomationAnywhereError(RuntimeError):
    """Erro de chamada ao Control Room."""


class AutomationAnywhereAuthError(AutomationAnywhereError):
    """Falha de autenticação no Control Room."""


class AutomationAnywhereConnector:
    def __init__(
        self,
        config: AutomationAnywhereConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.base_url = normalize_control_room_url(config.control_room_url)
        self.session: Optional[requests.Session] = None
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        # circuit breaker (em memória, por instância)
        self._cb_failures: List[float] = []
        self._cb_open_until: float = 0.0
        self._cb_last_probe: float = 0.0

    # ── ciclo de vida ────────────────────────────────────────────────────────
    def connect(self) -> None:
        """Garante sessão HTTP + token válido (autentica se necessário)."""
        if self.session is None:
            self.config.validate()
            self.session = requests.Session()
            self.session.verify = self.config.verify_ssl
            self.logger.info("🔌 Control Room | base=%s | user=%s", self.base_url, self.config.username)
        self._ensure_token()

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None
            self._token = None
            self._token_expires_at = 0.0
            self.logger.info("🔌 Conexão Control Room encerrada")

    def test_connection(self) -> Dict[str, Any]:
        """Autentica e faz uma chamada leve — valida URL/credenciais."""
        started = time.perf_counter()
        self.connect()
        self.post_json("/v3/activity/list", {"page": {"length": 1, "offset": 0}})
        elapsed = round(time.perf_counter() - started, 4)
        self.logger.info("🔎 Control Room OK | base=%s | tempo=%.4fs", self.base_url, elapsed)
        return {"control_room": self.base_url, "authenticated": True, "elapsed_seconds": elapsed}

    # ── autenticação (token em memória) ───────────────────────────────────────
    def _ensure_token(self) -> None:
        if self._token and time.time() < self._token_expires_at:
            return
        self._authenticate()

    def _authenticate(self) -> None:
        if self.session is None:
            raise AutomationAnywhereError("Sessão não inicializada (chame connect()).")

        payload: Dict[str, Any] = {"username": self.config.username}
        if self.config.api_key:
            payload["apiKey"] = self.config.api_key
        else:
            payload["password"] = self.config.password

        url = self.base_url + self.config.auth_path
        try:
            resp = self.session.post(url, json=payload, timeout=self.config.timeout)
        except requests.RequestException as exc:
            raise AutomationAnywhereAuthError(f"Falha de rede ao autenticar: {exc}") from exc

        if resp.status_code != 200:
            raise AutomationAnywhereAuthError(
                f"Autenticação falhou (HTTP {resp.status_code}): {_safe_error(resp)}"
            )

        body = resp.json()
        token = body.get("token")
        if not token:
            raise AutomationAnywhereAuthError("Resposta de autenticação sem campo 'token'.")
        ttl = int(body.get("tokenExpiresIn") or 1500)
        self._token = token
        self._token_expires_at = time.time() + max(ttl - 60, 60)  # folga de 60s
        self.logger.info("🔑 Token do Control Room obtido (ttl=%ss)", ttl)

    # ── circuit breaker (em memória) ──────────────────────────────────────────
    def _cb_is_open(self) -> bool:
        now = time.time()
        if now >= self._cb_open_until:
            return False  # fechado
        # aberto: libera 1 sondagem por intervalo (half-open)
        if now - self._cb_last_probe >= CB_PROBE_INTERVAL:
            self._cb_last_probe = now
            return False
        return True

    def _cb_record_failure(self) -> None:
        now = time.time()
        self._cb_failures = [t for t in self._cb_failures if now - t < CB_WINDOW_SECONDS]
        self._cb_failures.append(now)
        if len(self._cb_failures) >= CB_FAIL_THRESHOLD:
            self._cb_open_until = now + CB_OPEN_SECONDS
            self._cb_failures.clear()
            self.logger.warning(
                "⚡ Circuit breaker ABERTO (Control Room indisponível) por %ss", CB_OPEN_SECONDS
            )

    def _cb_record_success(self) -> None:
        self._cb_failures.clear()
        self._cb_open_until = 0.0
        self._cb_last_probe = 0.0

    # ── request genérico (CB + auth header + re-auth em 401 + retry em 5xx) ───
    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict | None = None,
        _retried: bool = False,
    ) -> Any:
        if self.session is None:
            raise AutomationAnywhereError("Sessão não inicializada (chame connect()).")
        if self._cb_is_open():
            raise AutomationAnywhereError(
                "circuit_open: Control Room temporariamente indisponível (circuit breaker ativo)."
            )
        self._ensure_token()
        headers = {"X-Authorization": self._token or ""}
        url = self.base_url + path

        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = self.session.request(
                    method, url, headers=headers, json=json_body,
                    params=params, timeout=self.config.timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                self._cb_record_failure()
                raise AutomationAnywhereError(f"Falha de rede em {method} {path}: {exc}") from exc

            if resp.status_code in (502, 503, 504) and attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            if resp.status_code in (502, 503, 504):
                self._cb_record_failure()
                raise AutomationAnywhereError(
                    f"{method} {path} retornou HTTP {resp.status_code}: {_safe_error(resp)}"
                )

            if resp.status_code == 401 and not _retried:
                self._token = None
                self._authenticate()
                return self._request(method, path, json_body=json_body, params=params, _retried=True)

            if resp.status_code >= 400:
                # erro "de negócio" (4xx) não conta p/ o circuit breaker
                raise AutomationAnywhereError(
                    f"{method} {path} retornou HTTP {resp.status_code}: {_safe_error(resp)}"
                )

            self._cb_record_success()
            return resp.json() if resp.content else {}

        self._cb_record_failure()
        raise AutomationAnywhereError(f"Esgotou tentativas em {method} {path}: {last_exc}")

    # ── API genérica (chame qualquer endpoint do Control Room) ────────────────
    def get_json(self, path: str, *, params: dict | None = None) -> Any:
        self.connect()
        return self._request("GET", path, params=params)

    def post_json(self, path: str, body: Any | None = None) -> Any:
        self.connect()
        return self._request("POST", path, json_body=body if body is not None else {})

    # ── AÇÃO PRINCIPAL: disparar um robô ──────────────────────────────────────
    def run_bot(
        self,
        *,
        file_id: int,
        run_as_user_ids: List[int],
        pool_ids: Optional[List[int]] = None,
        override_default_device: bool = False,
        callback_url: Optional[str] = None,
    ) -> str:
        """Dispara o bot `file_id` no Control Room. Retorna o deploymentId.

        - file_id: id do bot no repositório (descubra com find_files() uma vez).
        - run_as_user_ids: ids dos run-as users (com device associado) que executam o bot.
        """
        body: Dict[str, Any] = {
            "fileId": file_id,
            "runAsUserIds": run_as_user_ids,
            "poolIds": pool_ids or [],
            "overrideDefaultDevice": override_default_device,
        }
        if callback_url:
            body["callbackInfo"] = {"url": callback_url}

        self.logger.info("🚀 Disparando bot | fileId=%s | runAsUserIds=%s", file_id, run_as_user_ids)
        data = self.post_json("/v3/automations/deploy", body)
        deployment_id = data.get("deploymentId")
        if not deployment_id:
            raise AutomationAnywhereError(f"Deploy sem deploymentId na resposta: {data}")
        self.logger.info("✅ Bot disparado | deploymentId=%s", deployment_id)
        return str(deployment_id)

    # ── acompanhamento da execução ────────────────────────────────────────────
    def get_activity(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Retorna o registro de atividade da execução (ou None se ainda não apareceu)."""
        body = {
            "filter": {"operator": "eq", "field": "deploymentId", "value": deployment_id},
            "page": {"length": 1, "offset": 0},
            "sort": [{"field": "startDateTime", "direction": "desc"}],
        }
        data = self.post_json("/v3/activity/list", body)
        items = data.get("list") or []
        return items[0] if items else None

    def wait_for_completion(
        self,
        deployment_id: str,
        *,
        timeout: float = 600.0,
        poll_interval: float = 10.0,
    ) -> Dict[str, Any]:
        """Aguarda a execução chegar a um status terminal. Retorna a atividade final.

        Levanta AutomationAnywhereError em status de falha ou se estourar o timeout.
        """
        deadline = time.time() + timeout
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            activity = self.get_activity(deployment_id)
            if activity:
                last = activity
                status = str(activity.get("status") or "").upper()
                if status in TERMINAL_STATUSES:
                    self.logger.info("🏁 Finalizado | deploymentId=%s | status=%s", deployment_id, status)
                    if status in FAILED_STATUSES:
                        raise AutomationAnywhereError(
                            f"Bot falhou | deploymentId={deployment_id} | status={status} | "
                            f"msg={activity.get('message')}"
                        )
                    return activity
                self.logger.info("⏳ Em andamento | deploymentId=%s | status=%s", deployment_id, status)
            time.sleep(poll_interval)
        raise AutomationAnywhereError(
            f"Timeout ({timeout}s) aguardando deploymentId={deployment_id}. Último status: {last.get('status')}"
        )

    def run_bot_and_wait(
        self,
        *,
        file_id: int,
        run_as_user_ids: List[int],
        timeout: float = 600.0,
        poll_interval: float = 10.0,
        **deploy_kwargs: Any,
    ) -> Dict[str, Any]:
        """Conveniência: dispara o bot E aguarda concluir. Retorna a atividade final."""
        deployment_id = self.run_bot(
            file_id=file_id, run_as_user_ids=run_as_user_ids, **deploy_kwargs
        )
        return self.wait_for_completion(deployment_id, timeout=timeout, poll_interval=poll_interval)

    # ── idempotência e seleção de runner ─────────────────────────────────────
    def is_bot_running(self, file_id: int) -> bool:
        """Retorna True se o bot já tem atividade ativa no Control Room (RUNNING/WAITING)."""
        active = ["RUNNING", "RUN_PAUSED", "STARTED", "QUEUED", "PENDING_EXECUTION", "DEPLOYED"]
        body = {
            "filter": {
                "operator": "and",
                "operands": [
                    {"operator": "eq", "field": "fileId", "value": str(file_id)},
                    {
                        "operator": "or",
                        "operands": [{"operator": "eq", "field": "status", "value": s} for s in active],
                    },
                ],
            },
            "page": {"length": 1, "offset": 0},
        }
        data = self.post_json("/v3/activity/list", body)
        return len(data.get("list") or []) > 0

    def is_runner_busy(self, user_id: int) -> bool:
        """Retorna True se o runner tem atividade ativa (RUNNING/WAITING) no Control Room."""
        active = ["RUNNING", "RUN_PAUSED", "STARTED", "QUEUED", "PENDING_EXECUTION", "DEPLOYED"]
        body = {
            "filter": {
                "operator": "and",
                "operands": [
                    {"operator": "eq", "field": "runAsUserId", "value": str(user_id)},
                    {
                        "operator": "or",
                        "operands": [{"operator": "eq", "field": "status", "value": s} for s in active],
                    },
                ],
            },
            "page": {"length": 1, "offset": 0},
        }
        data = self.post_json("/v3/activity/list", body)
        return len(data.get("list") or []) > 0

    def pick_runner(self, candidate_ids: List[int]) -> Optional[int]:
        """Retorna o primeiro runner livre (em ordem de preferência). None se todos ocupados."""
        for user_id in candidate_ids:
            if not self.is_runner_busy(user_id):
                self.logger.info("🤖 Runner disponível | userId=%s", user_id)
                return user_id
            self.logger.info("⏳ Runner ocupado | userId=%s — tentando próximo", user_id)
        return None

    def any_bot_running(self, file_ids: List[int]) -> Optional[int]:
        """Retorna o primeiro fileId com atividade ativa, ou None se todos estão livres."""
        for file_id in file_ids:
            if self.is_bot_running(file_id):
                return file_id
        return None

    # ── agendamento (schedule one-time +N minutos) ────────────────────────────
    def schedule_bot(
        self,
        *,
        file_id: int,
        run_as_user_id: int,
        delay_minutes: int = 3,
        name: Optional[str] = None,
        time_zone: str = "America/Sao_Paulo",
    ) -> str:
        """Cria um agendamento one-time para o bot rodar daqui `delay_minutes` minutos.

        Retorna o id do agendamento criado.
        """
        import datetime as _dt

        run_at = _dt.datetime.utcnow() + _dt.timedelta(minutes=delay_minutes)
        start_date = run_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        schedule_name = name or f"SAP-ESCRIT-{file_id}-{run_at.strftime('%Y%m%d%H%M%S')}"

        body: Dict[str, Any] = {
            "name": schedule_name,
            "fileId": file_id,
            "runAsUserIds": [run_as_user_id],
            "startDate": start_date,
            "timeZone": time_zone,
            "recurrenceType": "NONE",
        }

        self.logger.info(
            "📅 Agendando bot | fileId=%s | runner=%s | execucao=%s",
            file_id, run_as_user_id, start_date,
        )
        data = self.post_json("/v2/schedule/automations", body)
        schedule_id = str(data.get("id") or data.get("scheduleId") or "")
        if not schedule_id:
            raise AutomationAnywhereError(f"Agendamento sem id na resposta: {data}")
        self.logger.info("✅ Agendamento criado | scheduleId=%s | execucao=%s", schedule_id, start_date)
        return schedule_id

    # ── descoberta (rode uma vez p/ achar o fileId do bot) ───────────────────
    def find_files(self, name_contains: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Lista arquivos do repositório cujo nome contém `name_contains` (acha o fileId)."""
        body = {
            "filter": {"operator": "substring", "field": "name", "value": name_contains},
            "page": {"length": limit, "offset": 0},
        }
        data = self.post_json("/v2/repository/file/list", body)
        return data.get("list") or []


def _safe_error(resp: requests.Response) -> str:
    """Extrai mensagem amigável da resposta de erro (sem vazar payload sensível)."""
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or "(sem corpo)")[:200]
    if isinstance(body, dict):
        for key in ("message", "error_description", "error", "detail"):
            value = body.get(key)
            if value:
                return str(value)[:200]
    return str(body)[:200]
