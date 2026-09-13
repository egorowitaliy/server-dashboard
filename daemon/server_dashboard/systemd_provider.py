from __future__ import annotations

import time
from typing import Any

from .process import CommandError, find_command, run_command


class SystemdProviderError(RuntimeError):
    pass


def _parse_blocks(output: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        current[key] = value

    if current:
        blocks.append(current)

    return blocks


def _show_units(units: list[str]) -> dict[str, dict[str, str]]:
    if not units:
        return {}

    systemctl = find_command("systemctl")

    result = run_command(
        [
            systemctl,
            "show",
            *units,
            "--no-pager",
            "-p", "Id",
            "-p", "LoadState",
            "-p", "ActiveState",
            "-p", "SubState",
            "-p", "Result",
            "-p", "ActiveEnterTimestampMonotonic",
        ],
        timeout=10,
    )

    if result.returncode != 0 and not result.stdout:
        raise SystemdProviderError(
            result.stderr or "systemctl show завершился с ошибкой"
        )

    parsed: dict[str, dict[str, str]] = {}

    for block in _parse_blocks(result.stdout):
        unit = block.get("Id")
        if unit:
            parsed[unit] = block

    return parsed


def _uptime_seconds(block: dict[str, str]) -> int | None:
    raw = block.get("ActiveEnterTimestampMonotonic", "")

    try:
        entered_usec = int(raw)
    except ValueError:
        return None

    if entered_usec <= 0:
        return None

    now_usec = int(time.monotonic() * 1_000_000)

    if now_usec < entered_usec:
        return None

    return int((now_usec - entered_usec) / 1_000_000)


def _state_for(
    mode: str,
    block: dict[str, str],
) -> tuple[str, str]:
    load = block.get("LoadState")
    active = block.get("ActiveState")
    sub = block.get("SubState")
    result = block.get("Result")

    if load != "loaded":
        return "error", "unavailable"

    if mode == "daemon":
        if active == "active" and sub == "running":
            return "ok", "running"

        if active in {"activating", "reloading"}:
            return "warn", "starting"

        if active == "failed" or result == "failed":
            return "error", "failed"

        return "error", "stopped"

    if mode == "oneshot":
        if (
            active == "active"
            and sub == "exited"
            and result in {"", "success"}
        ):
            return "ok", "ready"

        if active == "activating":
            return "warn", "starting"

        if active == "failed" or result == "failed":
            return "error", "failed"

        return "error", "stopped"

    return "error", "unknown"


def collect_services(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = config.get("services", [])

    if not isinstance(configured, list):
        raise SystemdProviderError("services должен быть массивом")

    units = [
        row["unit"]
        for row in configured
        if isinstance(row, dict)
        and isinstance(row.get("unit"), str)
    ]

    try:
        current = _show_units(units)
    except CommandError as exc:
        raise SystemdProviderError(str(exc)) from exc

    output: list[dict[str, Any]] = []

    for row in configured:
        if not isinstance(row, dict):
            continue

        item_id = row.get("id")
        name = row.get("name")
        unit = row.get("unit")
        mode = row.get("mode")
        restart = row.get("restart")

        if not all(
            (
                isinstance(item_id, str),
                isinstance(name, str),
                isinstance(unit, str),
                isinstance(mode, str),
                isinstance(restart, bool),
            )
        ):
            continue

        block = current.get(unit)

        if block is None:
            output.append(
                {
                    "id": item_id,
                    "name": name,
                    "status": "error",
                    "state": "unavailable",
                    "uptime_seconds": None,
                    "restart_allowed": restart,
                }
            )
            continue

        status, state = _state_for(mode, block)

        uptime = (
            _uptime_seconds(block)
            if mode == "daemon" and state == "running"
            else None
        )

        output.append(
            {
                "id": item_id,
                "name": name,
                "status": status,
                "state": state,
                "uptime_seconds": uptime,
                "restart_allowed": restart,
            }
        )

    return output

def collect_failed_units() -> list[str]:
    """Return currently failed systemd service unit names."""
    try:
        systemctl = find_command("systemctl")

        result = run_command(
            [
                systemctl,
                "list-units",
                "--failed",
                "--type=service",
                "--no-legend",
                "--plain",
                "--no-pager",
            ],
            timeout=8,
        )
    except CommandError as exc:
        raise SystemdProviderError(str(exc)) from exc

    if result.returncode != 0:
        raise SystemdProviderError(
            result.stderr
            or "Не удалось получить failed systemd units"
        )

    units: list[str] = []

    for line in result.stdout.splitlines():
        fields = line.split()

        if not fields:
            continue

        unit = fields[0]

        if unit.endswith(".service"):
            units.append(unit)

    return units

