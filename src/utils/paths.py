from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_data_dir() -> Path:
    path = get_project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_output_dir() -> Path:
    path = get_data_dir() / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_dir() -> Path:
    path = get_project_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_output_path(process_name: str, file_name: str) -> Path:
    process_dir = get_output_dir() / process_name
    process_dir.mkdir(parents=True, exist_ok=True)
    return process_dir / file_name