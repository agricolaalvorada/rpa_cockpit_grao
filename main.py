# -*- coding: utf-8 -*-
"""Entrypoint do monitor de escrituração.

A orquestração vive em src/orchestration/application.py. Mantido como
`python main.py` por compatibilidade operacional.
"""
from __future__ import annotations

from typing import Any, Dict

from src.orchestration.application import Application


def main() -> Dict[str, Any]:
    return Application().run()


if __name__ == "__main__":
    main()
