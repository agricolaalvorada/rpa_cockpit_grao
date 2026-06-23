from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------

def _safe_text(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _status_upper(status: Any) -> str:
    return _safe_text(status).upper()


def _status_emoji(status: Any) -> str:
    s = _status_upper(status)
    if s == "SUCESSO":
        return "✅"
    if s == "PARCIAL":
        return "🟡"
    if s == "ERRO":
        return "❌"
    if s == "SEM_DADOS":
        return "⚠️"
    return "ℹ️"


def _status_color(status: Any) -> str:
    s = _status_upper(status)
    if s == "SUCESSO":
        return "Good"
    if s == "PARCIAL":
        return "Warning"
    if s == "ERRO":
        return "Attention"
    if s == "SEM_DADOS":
        return "Warning"
    return "Accent"


def _status_container_style(status: Any) -> str:
    s = _status_upper(status)
    if s == "SUCESSO":
        return "good"
    if s == "ERRO":
        return "attention"
    if s in ("PARCIAL", "SEM_DADOS"):
        return "warning"
    return "accent"


def _fmt_dt(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str[:16].replace("T", " ")


def _short_name(process_name: str) -> str:
    return process_name.replace("V2_Consulta_Comp_", "")


def _resumo_linha(proc: Dict[str, Any]) -> str:
    if _status_upper(proc.get("status", "")) == "SEM_DADOS":
        return "nenhum registro na fila"
    rows = int(proc.get("rows_processed") or 0)
    aptas = int(proc.get("rows_aptas") or 0)
    pend = int(proc.get("rows_pendentes") or 0)
    duration = _safe_text(proc.get("duration_formatted"))
    return f"{rows} processadas  ·  {aptas} aptas  ·  {pend} pendentes  ·  {duration}"


# ---------------------------------------------------------------------------
# Blocos do card
# ---------------------------------------------------------------------------

def _build_header(execution_summary: Dict[str, Any]) -> Dict[str, Any]:
    status = _safe_text(execution_summary.get("status"))
    process_name = _safe_text(execution_summary.get("process_name"))
    environment = _safe_text(execution_summary.get("environment"))
    duration = _safe_text(execution_summary.get("duration_formatted"))
    started = _fmt_dt(_safe_text(execution_summary.get("started_at")))

    subtitle = (
        f"{_status_emoji(status)} {_status_upper(status)}  ·  "
        f"{started}  ·  {environment}  ·  {duration}"
    )

    return {
        "type": "Container",
        "style": _status_container_style(status),
        "bleed": True,
        "items": [
            {
                "type": "TextBlock",
                "text": f"🌿 {process_name}",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": subtitle,
                "spacing": "Small",
                "isSubtle": True,
                "wrap": True,
            },
        ],
    }


def _build_process_container(proc: Dict[str, Any]) -> Dict[str, Any]:
    status = _safe_text(proc.get("status"))
    emoji = _status_emoji(status)
    color = _status_color(status)
    name = _short_name(_safe_text(proc.get("process_name")))
    resumo = _resumo_linha(proc)
    aa_runner_id = proc.get("aa_runner_id")

    items: List[Dict[str, Any]] = [
        {
            "type": "ColumnSet",
            "spacing": "None",
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": name,
                            "weight": "Bolder",
                            "wrap": True,
                        }
                    ],
                },
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"{emoji} {_status_upper(status)}",
                            "color": color,
                            "weight": "Bolder",
                            "horizontalAlignment": "Right",
                        }
                    ],
                },
            ],
        },
        {
            "type": "TextBlock",
            "text": resumo,
            "size": "Small",
            "isSubtle": True,
            "spacing": "Small",
            "wrap": True,
        },
    ]

    if aa_runner_id is not None:
        items.append(
            {
                "type": "TextBlock",
                "text": f"📅 bot agendado  ·  +3 min  ·  runner {aa_runner_id}",
                "size": "Small",
                "color": "Accent",
                "isSubtle": True,
                "spacing": "None",
                "wrap": True,
            }
        )

    return {
        "type": "Container",
        "separator": True,
        "spacing": "Small",
        "items": items,
    }


def _build_summary_bar(execution_summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = execution_summary.get("summary", {})
    total = _safe_text(summary.get("total_linhas_processadas"))
    aptas = _safe_text(summary.get("total_notas_aptas"))
    pendentes = _safe_text(summary.get("total_notas_pendentes"))

    def _kpi_col(label: str, value: str, subtitle: str, color: str, align: str = "Center") -> Dict[str, Any]:
        return {
            "type": "Column",
            "width": 1,
            "items": [
                {
                    "type": "TextBlock",
                    "text": label,
                    "size": "Small",
                    "weight": "Bolder",
                    "isSubtle": True,
                    "horizontalAlignment": align,
                    "spacing": "None",
                },
                {
                    "type": "TextBlock",
                    "text": value,
                    "size": "ExtraLarge",
                    "weight": "Bolder",
                    "color": color,
                    "horizontalAlignment": align,
                    "spacing": "None",
                },
                {
                    "type": "TextBlock",
                    "text": subtitle,
                    "size": "Small",
                    "isSubtle": True,
                    "horizontalAlignment": align,
                    "spacing": "None",
                    "wrap": True,
                },
            ],
        }

    return {
        "type": "Container",
        "style": "emphasis",
        "separator": True,
        "spacing": "Small",
        "items": [
            {
                "type": "ColumnSet",
                "columns": [
                    _kpi_col("📊 TOTAL", total, "linhas", "Accent"),
                    _kpi_col("✅ APTAS", aptas, "escrituradas", "Good"),
                    _kpi_col("⏳ PENDENTES", pendentes, "aguardando", "Warning"),
                ],
            }
        ],
    }


def _build_error_block(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not errors:
        return []

    lines = [
        f"• {_safe_text(e.get('process_name'))}: {_safe_text(e.get('error'))}"
        for e in errors[:5]
    ]

    return [
        {
            "type": "TextBlock",
            "text": "🧨 Erros encontrados",
            "weight": "Bolder",
            "separator": True,
            "color": "Attention",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "\n".join(lines),
            "wrap": True,
            "size": "Small",
        },
    ]


# ---------------------------------------------------------------------------
# Card principal
# ---------------------------------------------------------------------------

def build_teams_adaptive_card(execution_summary: Dict[str, Any]) -> Dict[str, Any]:
    processos = execution_summary.get("processos_executados", [])

    body: List[Dict[str, Any]] = [
        _build_header(execution_summary),
        *[_build_process_container(p) for p in processos],
        _build_summary_bar(execution_summary),
    ]

    body.extend(_build_error_block(execution_summary.get("processos_com_erro", [])))

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
    }


def build_teams_payload(execution_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "execution_summary": execution_summary,
        "adaptive_card": build_teams_adaptive_card(execution_summary),
    }


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------

def send_to_power_automate(
    url: str,
    execution_summary: Dict[str, Any],
    timeout: int = 30,
) -> Dict[str, Any]:
    payload = build_teams_payload(execution_summary)

    response = requests.post(
        url,
        json=payload,
        timeout=timeout,
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()

    try:
        response_body: Optional[Any] = response.json()
    except ValueError:
        response_body = response.text

    return {
        "success": True,
        "status_code": response.status_code,
        "response": response_body,
    }


def notify_teams_safe(
    logger: logging.Logger,
    url: str,
    execution_summary: Dict[str, Any],
    timeout: int = 30,
) -> None:
    try:
        result = send_to_power_automate(
            url=url,
            execution_summary=execution_summary,
            timeout=timeout,
        )
        logger.info(
            "📣 Resumo enviado ao Teams com sucesso | status_code=%s",
            result["status_code"],
        )
    except Exception as exc:
        logger.warning("⚠️ Falha ao enviar resumo ao Teams: %s", exc)
