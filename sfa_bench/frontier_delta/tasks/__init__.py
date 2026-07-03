"""Loader for the frozen Frontier Delta v0 task set.

Tasks are plain JSON files in this directory (one per lane). They are loaded
deterministically (sorted by ``task_id``) and validated against the schema.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import schemas

TASKS_DIR = Path(__file__).resolve().parent


def task_files() -> list[Path]:
    return sorted(TASKS_DIR.glob("*.json"))


def load_tasks(validate: bool = True) -> list[dict[str, Any]]:
    """Load all suite tasks, sorted by ``task_id``. Raises on an invalid task."""
    tasks: list[dict[str, Any]] = []
    for path in task_files():
        with path.open("r", encoding="utf-8") as fh:
            task = json.load(fh)
        if validate:
            schemas.assert_valid_task(task)
        tasks.append(task)
    tasks.sort(key=lambda t: t["task_id"])
    return tasks


def load_task(task_id: str) -> dict[str, Any]:
    for task in load_tasks():
        if task["task_id"] == task_id:
            return task
    raise KeyError(f"unknown task_id: {task_id!r}")
