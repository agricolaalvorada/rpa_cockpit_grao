from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def _sanitize_file_name(value: str) -> str:
    """
    Sanitiza texto para uso em nome de arquivo.
    """
    invalid_chars = '<>:"/\\|?*'
    sanitized = "".join("_" if char in invalid_chars else char for char in value.strip())
    sanitized = sanitized.replace(" ", "_")
    return sanitized or "processo"


def setup_logger(process_name: str, log_dir: Path, level: str = "INFO", save_file: bool = True) -> logging.Logger:
    """
    Cria e configura um logger com saída em arquivo e console.
    """
    logger_name = f"V2_{process_name}"
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_file_name(process_name)
    log_file = log_dir / f"{safe_name}_{timestamp}.log"

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if save_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info("Logger iniciado.")
    if save_file:
        logger.info("Arquivo de log: %s", log_file)

    return logger