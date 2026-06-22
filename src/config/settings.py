from __future__ import annotations

import os
import warnings
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# O campo `schema` (atributo de negócio) sombreia um atributo herdado do
# BaseModel do Pydantic. O acesso `config.schema` funciona normalmente; apenas
# silenciamos o aviso cosmético para não poluir a saída do monitor.
warnings.filterwarnings("ignore", message=r'Field name "schema"', category=UserWarning)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# =========================================================
# PATHS DO PROJETO
# =========================================================
BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
LOG_DIR = BASE_DIR / "logs"
SQL_DIR = BASE_DIR / "sql"
DATA_DIR = BASE_DIR / "data"
ENV_FILE = BASE_DIR / ".env"

LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

if load_dotenv and ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)


# =========================================================
# HELPERS
# =========================================================
def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key, default)
    if isinstance(value, str):
        value = value.strip()
    return value


def _get_env_int(key: str, default: Optional[int] = None) -> Optional[int]:
    value = _get_env(key)
    if value in (None, ""):
        return default
    return int(value)


def _get_env_float(key: str, default: Optional[float] = None) -> Optional[float]:
    value = _get_env(key)
    if value in (None, ""):
        return default
    return float(value)


def _get_env_bool(key: str, default: bool = False) -> bool:
    value = _get_env(key)
    if value in (None, ""):
        return default
    return value.lower() in {"1", "true", "yes", "sim", "y"}


# =========================================================
# CONFIGURAÇÕES (Pydantic, imutáveis)
# =========================================================
class SapConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str
    port: int
    database: str
    schema: str
    user: str
    password: str
    connection_delay: float = 1.0
    query_delay: float = 0.5
    # Ano da safra usado no filtro das consultas HANA (substitui o YEAR=2026 hardcoded).
    safra_ano: int = Field(default_factory=lambda: date.today().year)

    @classmethod
    def from_env(cls) -> "SapConfig":
        return cls(
            host=_get_env("SAP_HOST", "") or "",
            port=_get_env_int("SAP_PORT", 0) or 0,
            database=_get_env("SAP_DATABASE", "") or "",
            schema=_get_env("SAP_SCHEMA", "") or "",
            user=_get_env("SAP_USER", "") or "",
            password=_get_env("SAP_PASSWORD", "") or "",
            connection_delay=_get_env_float("SAP_CONNECTION_DELAY", 1.0) or 1.0,
            query_delay=_get_env_float("SAP_QUERY_DELAY", 0.5) or 0.5,
            safra_ano=_get_env_int("SAFRA_ANO", date.today().year) or date.today().year,
        )

    def validate(self) -> None:
        missing: list[str] = []

        if not self.host:
            missing.append("SAP_HOST")
        if not self.port:
            missing.append("SAP_PORT")
        if not self.database:
            missing.append("SAP_DATABASE")
        if not self.schema:
            missing.append("SAP_SCHEMA")
        if not self.user:
            missing.append("SAP_USER")
        if not self.password:
            missing.append("SAP_PASSWORD")

        if missing:
            raise ValueError(
                f"Variáveis obrigatórias do SAP não encontradas no .env: {', '.join(missing)}"
            )


class PostgresConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str

    @classmethod
    def from_env(cls) -> "PostgresConfig":
        return cls(
            host=_get_env("POSTGRES_HOST", "") or "",
            port=_get_env_int("POSTGRES_PORT", 5432) or 5432,
            database=_get_env("POSTGRES_DB", "") or "",
            user=_get_env("POSTGRES_USER", "") or "",
            password=_get_env("POSTGRES_PASSWORD", "") or "",
            schema=_get_env("POSTGRES_SCHEMA", "public") or "public",
        )

    def validate(self) -> None:
        missing: list[str] = []

        if not self.host:
            missing.append("POSTGRES_HOST")
        if not self.port:
            missing.append("POSTGRES_PORT")
        if not self.database:
            missing.append("POSTGRES_DB")
        if not self.user:
            missing.append("POSTGRES_USER")
        if not self.password:
            missing.append("POSTGRES_PASSWORD")
        if not self.schema:
            missing.append("POSTGRES_SCHEMA")

        if missing:
            raise ValueError(
                f"Variáveis obrigatórias do PostgreSQL não encontradas no .env: {', '.join(missing)}"
            )


class AutomationAnywhereConfig(BaseModel):
    """Control Room do Automation Anywhere (A360) — para acionar robôs."""

    model_config = ConfigDict(frozen=True)

    control_room_url: str
    username: str
    password: str = ""
    api_key: str = ""
    verify_ssl: bool = True
    timeout: float = 60.0
    # Endpoint de autenticação do CR (alguns ambientes usam /v2/authentication).
    auth_path: str = "/v1/authentication"
    # Runners em ordem de preferência: candidato 1 → candidato 2 (fallback).
    run_as_user_ids: tuple = ()

    @classmethod
    def from_env(cls) -> "AutomationAnywhereConfig":
        ids_str = _get_env("AA_RUN_AS_USER_IDS", "") or ""
        run_as_user_ids = tuple(
            int(x.strip()) for x in ids_str.split(",") if x.strip().isdigit()
        )
        return cls(
            control_room_url=_get_env("AA_CONTROL_ROOM_URL", "") or "",
            username=_get_env("AA_USERNAME", "") or "",
            password=_get_env("AA_PASSWORD", "") or "",
            api_key=_get_env("AA_API_KEY", "") or "",
            verify_ssl=_get_env_bool("AA_VERIFY_SSL", True),
            timeout=_get_env_float("AA_TIMEOUT", 60.0) or 60.0,
            auth_path=_get_env("AA_AUTH_PATH", "/v1/authentication") or "/v1/authentication",
            run_as_user_ids=run_as_user_ids,
        )

    def validate(self) -> None:
        missing: list[str] = []

        if not self.control_room_url:
            missing.append("AA_CONTROL_ROOM_URL")
        if not self.username:
            missing.append("AA_USERNAME")
        if not self.password and not self.api_key:
            missing.append("AA_PASSWORD ou AA_API_KEY")

        if missing:
            raise ValueError(
                f"Variáveis obrigatórias do Automation Anywhere não encontradas no .env: {', '.join(missing)}"
            )


class LogConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: str
    dir: Path
    save_file: bool

    @classmethod
    def from_env(cls) -> "LogConfig":
        return cls(
            level=_get_env("LOG_LEVEL", "INFO") or "INFO",
            dir=Path(_get_env("LOG_DIR", str(LOG_DIR)) or str(LOG_DIR)),
            save_file=_get_env_bool("LOG_SAVE_FILE", True),
        )


sap_config = SapConfig.from_env()
postgres_config = PostgresConfig.from_env()
aa_config = AutomationAnywhereConfig.from_env()
log_config = LogConfig.from_env()
