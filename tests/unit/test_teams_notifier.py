# -*- coding: utf-8 -*-
"""Unitários do teams_notifier (builders puros + notify_teams_safe sem rede)."""
from __future__ import annotations

import json

import pytest

from src.utils import teams_notifier as tn

SUMMARY = {
    "status": "PARCIAL",
    "process_name": "SAP_ESCRITURAR_V2",
    "environment": "dev",
    "duration_formatted": "00:00:30",
    "started_at": "2026-01-01T12:00:00",
    "finished_at": "2026-01-01T12:00:30",
    "summary": {
        "total_processos": 3, "processos_sucesso": 1, "processos_sem_dados": 1,
        "processos_erro": 1, "total_linhas_processadas": 42,
        "total_notas_aptas": 30, "total_notas_pendentes": 12,
    },
    "processos_executados": [
        {"process_name": "P1", "status": "SUCESSO", "rows_processed": 42, "rows_aptas": 30, "duration_formatted": "00:00:10"},
        {"process_name": "P2", "status": "SEM_DADOS", "rows_processed": 0, "rows_aptas": 0, "duration_formatted": "00:00:05"},
    ],
    "processos_com_erro": [{"process_name": "P3", "error": "boom"}],
}


# ---------- helpers puros ----------
def test_safe_text():
    assert tn._safe_text(None) == "-"
    assert tn._safe_text("   ") == "-"
    assert tn._safe_text("  x  ") == "x"
    assert tn._safe_text(0) == "0"
    assert tn._safe_text(123) == "123"


@pytest.mark.parametrize("status,emoji", [
    ("SUCESSO", "✅"), ("PARCIAL", "🟡"), ("ERRO", "❌"), ("SEM_DADOS", "⚠️"),
    ("qualquer", "ℹ️"), ("sucesso", "✅"),  # case-insensitive
])
def test_status_emoji(status, emoji):
    assert tn._status_emoji(status) == emoji


@pytest.mark.parametrize("status,color", [
    ("SUCESSO", "Good"), ("PARCIAL", "Warning"), ("ERRO", "Attention"),
    ("SEM_DADOS", "Warning"), ("outro", "Accent"),
])
def test_status_color(status, color):
    assert tn._status_color(status) == color


def test_error_block_vazio_e_trunca_em_5():
    assert tn._build_error_block([]) == []

    muitos = [{"process_name": f"P{i}", "error": f"e{i}"} for i in range(7)]
    bloco = tn._build_error_block(muitos)
    assert bloco[0]["text"] == "🧨 Erros encontrados"
    linhas = bloco[1]["text"].split("\n")
    assert len(linhas) == 5  # trunca em 5
    assert linhas[0] == "• P0: e0"


# ---------- card / payload ----------
def test_adaptive_card_estrutura():
    card = tn.build_teams_adaptive_card(SUMMARY)
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert card["msteams"]["width"] == "Full"  # card alargado no Teams
    assert isinstance(card["body"], list) and card["body"]
    dump = json.dumps(card, ensure_ascii=False)
    assert "SAP_ESCRITURAR_V2" in dump
    assert "P1" in dump and "P2" in dump
    assert "🧨 Erros encontrados" in dump  # bloco de erro presente
    assert '"color": "Good"' in dump       # aptas em verde
    assert "30 aptas" in dump              # resumo por processo
    assert "aguardando" in dump            # barra de totais presente


def test_summary_bar():
    bar = tn._build_summary_bar(SUMMARY)
    cols = bar["items"][0]["columns"]
    values = [c["items"][1]["text"] for c in cols]   # items[1] = número
    assert any("42" in t for t in values)   # total linhas
    assert any("30" in t for t in values)   # aptas
    assert any("12" in t for t in values)   # pendentes
    assert cols[1]["items"][1]["color"] == "Good"
    assert cols[2]["items"][1]["color"] == "Warning"


def test_adaptive_card_sem_erros_omite_bloco():
    s = {**SUMMARY, "processos_com_erro": []}
    dump = json.dumps(tn.build_teams_adaptive_card(s), ensure_ascii=False)
    assert "🧨 Erros encontrados" not in dump


def test_build_teams_payload():
    payload = tn.build_teams_payload(SUMMARY)
    assert payload["execution_summary"] is SUMMARY
    assert payload["adaptive_card"] == tn.build_teams_adaptive_card(SUMMARY)


# ---------- notify_teams_safe (sem rede) ----------
class _FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, *a, **k):
        self.infos.append(a)

    def warning(self, *a, **k):
        self.warnings.append(a)


def test_notify_sucesso(monkeypatch):
    monkeypatch.setattr(tn, "send_to_power_automate", lambda **k: {"status_code": 200})
    log = _FakeLogger()
    tn.notify_teams_safe(logger=log, url="http://x", execution_summary=SUMMARY)
    assert len(log.infos) == 1 and not log.warnings


def test_notify_falha_nao_propaga(monkeypatch):
    def _boom(**k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(tn, "send_to_power_automate", _boom)
    log = _FakeLogger()
    tn.notify_teams_safe(logger=log, url="http://x", execution_summary=SUMMARY)  # não levanta
    assert len(log.warnings) == 1 and not log.infos


def test_send_to_power_automate_monta_payload(monkeypatch):
    capturado = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def _fake_post(url, json=None, timeout=None, headers=None):
        capturado["url"] = url
        capturado["payload"] = json
        return _Resp()

    monkeypatch.setattr(tn.requests, "post", _fake_post)
    out = tn.send_to_power_automate("http://x", SUMMARY)
    assert out["success"] is True and out["status_code"] == 200
    assert "adaptive_card" in capturado["payload"]
