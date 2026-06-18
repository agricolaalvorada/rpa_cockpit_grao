# -*- coding: utf-8 -*-
"""Protocols dos conectores — contratos usados pela orquestração e pelos fakes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class QueryConnector(Protocol):
    def connect(self) -> Any: ...
    def execute_query(self, sql: str, params: Optional[Any] = None) -> List[Dict[str, Any]]: ...
    def close(self) -> None: ...


@runtime_checkable
class HanaLike(QueryConnector, Protocol):
    def render_sql_template(self, sql: str) -> str: ...
    def wait_between_queries(self) -> None: ...
