# -*- coding: utf-8 -*-
"""Helpers de status/agregação do Automation Anywhere Control Room.

Portado de CONTROLE_JOBS_AA (`backend/app/integrations/aa/metrics.py`).
Funções PURAS (sem I/O) — mapeiam os ~12 status do Control Room para 4 buckets,
extraem o departamento do path do bot e agregam contagens.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

RUNNING_STATUSES = {"RUNNING", "RUN_PAUSED", "UPDATE", "STARTED"}
WAITING_STATUSES = {"QUEUED", "PENDING_EXECUTION", "DEPLOYED"}
FAILED_STATUSES = {
    "RUN_FAILED",
    "RUN_TIMED_OUT",
    "RUN_ABORTED",
    "FAILED",
    "PENDING_FAILURE",
    "DEPLOY_FAILED",
    "FAILED_TO_DEPLOY",
}
COMPLETED_STATUSES = {"RUN_COMPLETED", "COMPLETED"}

# Qualquer status fora deste conjunto cai em OTHER — um status novo do Control Room
# não pode virar OTHER em silêncio (use unknown_statuses() para detectar).
KNOWN_STATUSES = RUNNING_STATUSES | WAITING_STATUSES | FAILED_STATUSES | COMPLETED_STATUSES

# Status terminais (fim do ciclo de vida de uma execução/deploy).
TERMINAL_STATUSES = COMPLETED_STATUSES | FAILED_STATUSES | {"RUN_ABORTED", "RUN_TIMED_OUT"}


def is_known_status(status: Optional[str]) -> bool:
    return bool(status) and status is not None and status.upper() in KNOWN_STATUSES


def unknown_statuses(items: Iterable[dict[str, Any]]) -> set[str]:
    """Status de execuções que cairiam em OTHER por não serem conhecidos."""
    out: set[str] = set()
    for it in items:
        s = it.get("status")
        if s and not is_known_status(s):
            out.add(str(s))
    return out


def clamp_pct(value: Optional[float]) -> Optional[float]:
    """Porcentagem sempre em [0,100] (defende contra dados corrompidos no render)."""
    if value is None:
        return None
    return max(0.0, min(100.0, round(value, 1)))


def bucket_for_status(status: Optional[str]) -> str:
    """Reduz os ~12 status do Control Room aos 4 buckets (RUNNING/WAITING/FAILED/COMPLETED/OTHER)."""
    if not status:
        return "OTHER"
    status_u = status.upper()
    if status_u in RUNNING_STATUSES:
        return "RUNNING"
    if status_u in WAITING_STATUSES:
        return "WAITING"
    if status_u in FAILED_STATUSES:
        return "FAILED"
    if status_u in COMPLETED_STATUSES:
        return "COMPLETED"
    return "OTHER"


def derive_department(path: Optional[str]) -> Optional[str]:
    r"""Extrai o departamento (elemento após 'Bots') de paths tipo
    'Automation Anywhere\Bots\Fiscal\...' -> 'Fiscal'."""
    if not path:
        return None
    normalized = path.replace("/", "\\")
    parts = [p for p in normalized.split("\\") if p]
    try:
        idx = parts.index("Bots")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    return parts[idx + 1]


def summarize_status_counts(executions: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Conta execuções por bucket + total."""
    counts = {"RUNNING": 0, "WAITING": 0, "FAILED": 0, "COMPLETED": 0, "OTHER": 0}
    total = 0
    for ex in executions:
        bucket = bucket_for_status(ex.get("status"))
        counts[bucket] = counts.get(bucket, 0) + 1
        total += 1
    counts["TOTAL"] = total
    return counts
