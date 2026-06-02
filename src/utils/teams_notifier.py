from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


def _safe_text(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _status_upper(status: str) -> str:
    return _safe_text(status).upper()


def _status_emoji(status: str) -> str:
    status_up = _status_upper(status)

    if status_up == "SUCESSO":
        return "✅"
    if status_up == "PARCIAL":
        return "🟡"
    if status_up == "ERRO":
        return "❌"
    if status_up == "SEM_DADOS":
        return "⚠️"
    return "ℹ️"


def _status_color(status: str) -> str:
    status_up = _status_upper(status)

    if status_up == "SUCESSO":
        return "Good"
    if status_up == "PARCIAL":
        return "Warning"
    if status_up == "ERRO":
        return "Attention"
    if status_up == "SEM_DADOS":
        return "Warning"
    return "Accent"


def _build_kpi_columns(execution_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = execution_summary.get("summary", {})

    kpis = [
        ("Ambiente", _safe_text(execution_summary.get("environment"))),
        ("Duração", _safe_text(execution_summary.get("duration_formatted"))),
        ("Linhas", _safe_text(summary.get("total_linhas_processadas"))),
        ("Processos", _safe_text(summary.get("total_processos"))),
    ]

    columns: List[Dict[str, Any]] = []
    for title, value in kpis:
        columns.append(
            {
                "type": "Column",
                "width": 1,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": title,
                        "weight": "Bolder",
                        "size": "Small",
                    },
                    {
                        "type": "TextBlock",
                        "text": value,
                        "wrap": True,
                    },
                ],
            }
        )

    return columns


def _build_fact_set(execution_summary: Dict[str, Any]) -> List[Dict[str, str]]:
    summary = execution_summary.get("summary", {})

    return [
        {"title": "Início", "value": _safe_text(execution_summary.get("started_at"))},
        {"title": "Fim", "value": _safe_text(execution_summary.get("finished_at"))},
        {"title": "Sucesso", "value": _safe_text(summary.get("processos_sucesso"))},
        {"title": "Sem dados", "value": _safe_text(summary.get("processos_sem_dados"))},
        {"title": "Erros", "value": _safe_text(summary.get("processos_erro"))},
    ]


def _build_table_header() -> Dict[str, Any]:
    return {
        "type": "ColumnSet",
        "columns": [
            {
                "type": "Column",
                "width": 8,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Processo",
                        "weight": "Bolder",
                        "size": "Small",
                    }
                ],
            },
            {
                "type": "Column",
                "width": 2,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Status",
                        "weight": "Bolder",
                        "size": "Small",
                    }
                ],
            },
            {
                "type": "Column",
                "width": 2,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Linhas",
                        "weight": "Bolder",
                        "size": "Small",
                        "horizontalAlignment": "Center",
                    }
                ],
            },
            {
                "type": "Column",
                "width": 2,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Tempo",
                        "weight": "Bolder",
                        "size": "Small",
                        "horizontalAlignment": "Center",
                    }
                ],
            },
        ],
    }


def _build_process_row(proc: Dict[str, Any]) -> Dict[str, Any]:
    status = _safe_text(proc.get("status"))
    emoji = _status_emoji(status)
    color = _status_color(status)

    return {
        "type": "ColumnSet",
        "separator": True,
        "columns": [
            {
                "type": "Column",
                "width": 5,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": _safe_text(proc.get("process_name")),
                        "weight": "Bolder",
                        "size": "Small",
                        "wrap": True,
                    }
                ],
            },
            {
                "type": "Column",
                "width": 2,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{emoji} {_status_upper(status)}",
                        "color": color,
                        "size": "Small",
                        "wrap": True,
                    }
                ],
            },
            {
                "type": "Column",
                "width": 2,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": _safe_text(proc.get("rows_processed")),
                        "horizontalAlignment": "Center",
                        "size": "Small",
                    }
                ],
            },
            {
                "type": "Column",
                "width": 2,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": _safe_text(proc.get("duration_formatted")),
                        "horizontalAlignment": "Center",
                        "size": "Small",
                    }
                ],
            },
        ],
    }


def _build_error_block(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not errors:
        return []

    lines: List[str] = []
    for err in errors[:5]:
        process_name = _safe_text(err.get("process_name"))
        error_msg = _safe_text(err.get("error"))
        lines.append(f"• {process_name}: {error_msg}")

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


def build_teams_adaptive_card(execution_summary: Dict[str, Any]) -> Dict[str, Any]:
    status = _safe_text(execution_summary.get("status"))
    status_emoji = _status_emoji(status)
    status_color = _status_color(status)
    process_name = _safe_text(execution_summary.get("process_name"))

    process_rows = [
        _build_process_row(proc)
        for proc in execution_summary.get("processos_executados", [])
    ]

    body: List[Dict[str, Any]] = [
        {
            "type": "Container",
            "style": "emphasis",
            "bleed": True,
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"🚀 {process_name}",
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": "Resumo de execução enviado automaticamente",
                    "spacing": "None",
                    "isSubtle": True,
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": f"{status_emoji} {_status_upper(status)}",
                    "weight": "Bolder",
                    "color": status_color,
                    "spacing": "Medium",
                    "wrap": True,
                },
            ],
        },
        {
            "type": "TextBlock",
            "text": "📊 Indicadores principais",
            "weight": "Bolder",
            "separator": True,
            "wrap": True,
        },
        {
            "type": "ColumnSet",
            "spacing": "Medium",
            "columns": _build_kpi_columns(execution_summary),
        },
        {
            "type": "FactSet",
            "facts": _build_fact_set(execution_summary),
        },
        {
            "type": "TextBlock",
            "text": "📦 Processos executados",
            "weight": "Bolder",
            "separator": True,
            "wrap": True,
        },
        {
            "type": "Container",
            "style": "default",
            "items": [_build_table_header(), *process_rows],
        },
    ]

    body.extend(_build_error_block(execution_summary.get("processos_com_erro", [])))

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }


def build_teams_payload(execution_summary: Dict[str, Any]) -> Dict[str, Any]:
    adaptive_card = build_teams_adaptive_card(execution_summary)

    return {
        "execution_summary": execution_summary,
        "adaptive_card": adaptive_card,
    }


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
    logger,
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