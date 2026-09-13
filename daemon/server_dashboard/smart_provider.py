from __future__ import annotations

import json
from typing import Any

from .process import CommandError, find_command, run_command


class SmartProviderError(RuntimeError):
    pass


def _smartctl_exit_status(
    data: dict[str, Any],
    fallback: int,
) -> int:
    smartctl = data.get("smartctl")

    if isinstance(smartctl, dict):
        value = smartctl.get("exit_status")

        if isinstance(value, int):
            return value

    return fallback


def _temperature(
    data: dict[str, Any],
) -> float | None:
    obj = data.get("temperature")

    if isinstance(obj, dict):
        value = obj.get("current")

        if isinstance(value, (int, float)):
            return round(float(value), 1)

    nvme = data.get("nvme_smart_health_information_log")

    if isinstance(nvme, dict):
        value = nvme.get("temperature")

        if isinstance(value, (int, float)):
            return round(float(value), 1)

    return None


def _power_on_hours(
    data: dict[str, Any],
) -> int | None:
    obj = data.get("power_on_time")

    if isinstance(obj, dict):
        value = obj.get("hours")

        if isinstance(value, int):
            return value

    return None


def _health(
    data: dict[str, Any],
    exit_status: int,
) -> tuple[str, str]:
    # smartctl bits 0..2 означают ошибку CLI/открытия устройства/команды.
    # Standby обрабатывается раньше по stderr/stdout и сюда не попадает.
    if exit_status & 0b00000111:
        return "error", "unavailable"

    smart_status = data.get("smart_status")

    if isinstance(smart_status, dict):
        passed = smart_status.get("passed")

        if passed is True:
            # smartctl exit bits 3..7 указывают на SMART-проблемы.
            if exit_status & 0b11111000:
                return "warn", "warning"

            return "ok", "healthy"

        if passed is False:
            return "error", "failed"

    nvme = data.get("nvme_smart_health_information_log")

    if isinstance(nvme, dict):
        critical = nvme.get("critical_warning")

        if isinstance(critical, int):
            if critical == 0:
                return "ok", "healthy"
            return "error", "failed"

    if exit_status & 0b11111000:
        return "warn", "warning"

    return "warn", "unknown"


def _is_standby(
    stdout: str,
    stderr: str,
) -> bool:
    text = f"{stdout}\n{stderr}".lower()

    return (
        "standby" in text
        and (
            "device is in standby" in text
            or "device is in low-power mode" in text
        )
    )


def _read_disk(
    smartctl: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    item_id = str(row["id"])
    name = str(row["name"])
    path = str(row["path"])
    disk_type = str(row["type"])

    if disk_type == "ata":
        args = [
            smartctl,
            "-j",
            "-n",
            "standby,0",
            "-a",
            path,
        ]
    else:
        args = [
            smartctl,
            "-j",
            "-a",
            path,
        ]

    try:
        result = run_command(
            args,
            timeout=8,
        )
    except CommandError as exc:
        return {
            "id": item_id,
            "name": name,
            "status": "error",
            "state": "unavailable",
            "temperature_c": None,
            "power_on_hours": None,
            "message": str(exc),
        }

    # ATA disk в standby специально НЕ будим.
    if disk_type == "ata" and _is_standby(
        result.stdout,
        result.stderr,
    ):
        return {
            "id": item_id,
            "name": name,
            "status": "ok",
            "state": "standby",
            "temperature_c": None,
            "power_on_hours": None,
            "message": None,
        }

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "id": item_id,
            "name": name,
            "status": "error",
            "state": "unavailable",
            "temperature_c": None,
            "power_on_hours": None,
            "message": "Некорректный ответ SMART",
        }

    exit_status = _smartctl_exit_status(
        data,
        result.returncode,
    )

    status, state = _health(
        data,
        exit_status,
    )

    return {
        "id": item_id,
        "name": name,
        "status": status,
        "state": state,
        "temperature_c": _temperature(data),
        "power_on_hours": _power_on_hours(data),
        "message": (
            "smartctl сообщил об ошибке выполнения"
            if state == "unavailable"
            else None
        ),
    }


def collect_smart(
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    section = config.get("smart", {})

    if not isinstance(section, dict):
        raise SmartProviderError(
            "smart должен быть таблицей"
        )

    disks = section.get("disks", [])

    if not isinstance(disks, list):
        raise SmartProviderError(
            "smart.disks должен быть массивом"
        )

    try:
        smartctl = find_command("smartctl")
    except CommandError as exc:
        raise SmartProviderError(str(exc)) from exc

    result: list[dict[str, Any]] = []

    for row in disks:
        if not isinstance(row, dict):
            continue

        result.append(
            _read_disk(
                smartctl,
                row,
            )
        )

    return result
