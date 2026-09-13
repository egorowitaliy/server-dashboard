from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, timezone as datetime_timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .process import CommandError, find_command, run_command


class ScheduleProviderError(RuntimeError):
    pass


SYSTEMD_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\b"
)


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


def _host_timezone() -> tzinfo:
    timezone_file = Path("/etc/timezone")

    try:
        name = timezone_file.read_text(encoding="utf-8").strip()
        if name:
            return ZoneInfo(name)
    except (OSError, UnicodeError, ZoneInfoNotFoundError):
        pass

    try:
        target = Path("/etc/localtime").resolve(strict=True)
        marker = "/zoneinfo/"
        value = str(target)
        if marker in value:
            return ZoneInfo(value.split(marker, 1)[1])
    except (OSError, ZoneInfoNotFoundError):
        pass

    return datetime.now().astimezone().tzinfo or datetime_timezone.utc


def _systemd_time_to_iso(
    value: str | None,
    source_timezone: tzinfo,
    target_timezone: ZoneInfo,
) -> str | None:
    if not value or value in {"n/a", "0"}:
        return None

    match = SYSTEMD_DATE_RE.search(value)

    if match is None:
        return None

    try:
        parsed = datetime.strptime(
            f"{match.group(1)} {match.group(2)}",
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return None

    # systemctl форматирует timestamp в timezone хоста. Не назначаем
    # ему timezone Dashboard: сначала локализуем в зоне хоста, затем
    # конвертируем в целевую зону интерфейса.
    localized = parsed.replace(tzinfo=source_timezone)

    return localized.astimezone(
        target_timezone
    ).isoformat(timespec="seconds")


def collect_schedule(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = config.get("schedule", [])

    if not isinstance(configured, list):
        raise ScheduleProviderError("schedule должен быть массивом")

    timezone_name = (
        config.get("dashboard", {})
        .get("timezone", "UTC")
    )

    timezone = ZoneInfo(str(timezone_name))
    source_timezone = _host_timezone()

    timers = [
        row["timer"]
        for row in configured
        if isinstance(row, dict)
        and isinstance(row.get("timer"), str)
    ]

    if not timers:
        return []

    try:
        systemctl = find_command("systemctl")

        result = run_command(
            [
                systemctl,
                "show",
                *timers,
                "--no-pager",
                "-p", "Id",
                "-p", "LoadState",
                "-p", "ActiveState",
                "-p", "SubState",
                "-p", "LastTriggerUSec",
                "-p", "NextElapseUSecRealtime",
                "-p", "Triggers",
            ],
            timeout=10,
        )
    except CommandError as exc:
        raise ScheduleProviderError(str(exc)) from exc

    if result.returncode != 0 and not result.stdout:
        raise ScheduleProviderError(
            result.stderr or "systemctl show timers завершился с ошибкой"
        )

    blocks: dict[str, dict[str, str]] = {}

    for block in _parse_blocks(result.stdout):
        unit = block.get("Id")
        if unit:
            blocks[unit] = block

    triggered_units = sorted(
        {
            unit
            for block in blocks.values()
            for unit in block.get("Triggers", "").split()
            if unit.endswith(".service")
        }
    )

    triggered_blocks: dict[str, dict[str, str]] = {}

    if triggered_units:
        try:
            triggered_result = run_command(
                [
                    systemctl,
                    "show",
                    *triggered_units,
                    "--no-pager",
                    "-p", "Id",
                    "-p", "LoadState",
                    "-p", "ActiveState",
                    "-p", "SubState",
                ],
                timeout=10,
            )
        except CommandError as exc:
            raise ScheduleProviderError(str(exc)) from exc

        if (
            triggered_result.returncode != 0
            and not triggered_result.stdout
        ):
            raise ScheduleProviderError(
                triggered_result.stderr
                or "systemctl show triggered units завершился с ошибкой"
            )

        for triggered_block in _parse_blocks(
            triggered_result.stdout
        ):
            unit = triggered_block.get("Id")

            if unit:
                triggered_blocks[unit] = triggered_block

    output: list[dict[str, Any]] = []

    for row in configured:
        if not isinstance(row, dict):
            continue

        item_id = row.get("id")
        name = row.get("name")
        timer = row.get("timer")

        if not all(
            (
                isinstance(item_id, str),
                isinstance(name, str),
                isinstance(timer, str),
            )
        ):
            continue

        block = blocks.get(timer)

        if block is None:
            output.append(
                {
                    "id": item_id,
                    "name": name,
                    "status": "error",
                    "running": False,
                    "last_run_at": None,
                    "next_run_at": None,
                }
            )
            continue

        active = block.get("ActiveState")
        load = block.get("LoadState")

        if load != "loaded":
            status = "error"
        elif active == "active":
            status = "ok"
        elif active == "activating":
            status = "warn"
        else:
            status = "error"

        running = False

        for triggered_unit in block.get(
            "Triggers",
            "",
        ).split():
            triggered_block = triggered_blocks.get(
                triggered_unit
            )

            if triggered_block is None:
                continue

            if (
                triggered_block.get("LoadState") == "loaded"
                and triggered_block.get("ActiveState")
                in {
                    "activating",
                    "active",
                    "reloading",
                    "deactivating",
                }
            ):
                running = True
                break

        output.append(
            {
                "id": item_id,
                "name": name,
                "status": status,
                "running": running,
                "last_run_at": _systemd_time_to_iso(
                    block.get("LastTriggerUSec"),
                    source_timezone,
                    timezone,
                ),
                "next_run_at": _systemd_time_to_iso(
                    block.get("NextElapseUSecRealtime"),
                    source_timezone,
                    timezone,
                ),
            }
        )

    return output
