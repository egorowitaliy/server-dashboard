from __future__ import annotations

import os
from pathlib import Path
from typing import Any


MOUNTINFO = Path("/proc/self/mountinfo")


class StorageMetricError(RuntimeError):
    pass


def _decode_mountinfo_path(value: str) -> str:
    # Формат mountinfo экранирует пробелы и несколько специальных символов.
    replacements = {
        r"\040": " ",
        r"\011": "\t",
        r"\012": "\n",
        r"\134": "\\",
    }

    for encoded, decoded in replacements.items():
        value = value.replace(encoded, decoded)

    return value


def current_mountpoints() -> set[str]:
    try:
        lines = MOUNTINFO.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StorageMetricError(
            f"Не удалось прочитать /proc/self/mountinfo: {exc}"
        ) from exc

    mountpoints: set[str] = set()

    for line in lines:
        fields = line.split()

        # mount point — пятое поле до разделителя " - ".
        if len(fields) < 6:
            continue

        mountpoints.add(_decode_mountinfo_path(fields[4]))

    return mountpoints


def _status_for_usage(
    usage_percent: float,
    warn_percent: int,
    error_percent: int,
) -> str:
    if usage_percent >= error_percent:
        return "error"

    if usage_percent >= warn_percent:
        return "warn"

    return "ok"


def collect_storage_metrics(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = config.get("storage", [])

    if not isinstance(configured, list):
        raise StorageMetricError("storage должен быть массивом")

    mounted = current_mountpoints()
    result: list[dict[str, Any]] = []

    for item in configured:
        if not isinstance(item, dict):
            continue

        item_id = item.get("id")
        name = item.get("name")
        path = item.get("path")
        warn = item.get("warn_percent")
        error = item.get("error_percent")

        if not all(
            (
                isinstance(item_id, str),
                isinstance(name, str),
                isinstance(path, str),
                isinstance(warn, int),
                isinstance(error, int),
            )
        ):
            continue

        is_mounted = path in mounted

        row: dict[str, Any] = {
            "id": item_id,
            "name": name,
            "mounted": is_mounted,
        }

        if not is_mounted:
            row.update(
                {
                    "used_bytes": None,
                    "available_bytes": None,
                    "total_bytes": None,
                    "usage_percent": None,
                    "status": "missing",
                }
            )
            result.append(row)
            continue

        try:
            stats = os.statvfs(path)
        except OSError:
            row.update(
                {
                    "used_bytes": None,
                    "available_bytes": None,
                    "total_bytes": None,
                    "usage_percent": None,
                    "status": "error",
                }
            )
            result.append(row)
            continue

        total = stats.f_blocks * stats.f_frsize
        available = stats.f_bavail * stats.f_frsize
        used = max(0, total - available)

        usage_percent = (
            used / total * 100.0
            if total > 0
            else 0.0
        )

        usage_percent = round(usage_percent, 1)

        row.update(
            {
                "used_bytes": used,
                "available_bytes": available,
                "total_bytes": total,
                "usage_percent": usage_percent,
                "status": _status_for_usage(
                    usage_percent,
                    warn,
                    error,
                ),
            }
        )

        result.append(row)

    return result
