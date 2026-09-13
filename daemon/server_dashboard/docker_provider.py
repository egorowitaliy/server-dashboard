from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .process import CommandError, find_command, run_command


class DockerProviderError(RuntimeError):
    pass


def _parse_docker_datetime(value: str) -> datetime | None:
    if not value or value.startswith("0001-01-01"):
        return None

    # Docker часто отдаёт nanoseconds, а нам такая точность не нужна.
    value = re.sub(
        r"(\.\d{6})\d+(?=(?:Z|[+-]\d{2}:\d{2})$)",
        r"\1",
        value,
    )

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def _container_uptime_seconds(state: dict[str, Any]) -> int | None:
    if state.get("Status") != "running":
        return None

    started = _parse_docker_datetime(
        str(state.get("StartedAt", ""))
    )

    if started is None:
        return None

    delta = datetime.now(timezone.utc) - started.astimezone(timezone.utc)

    return max(0, int(delta.total_seconds()))


def _status_for_container(
    state_name: str,
    health: str | None,
    *,
    paused: bool = False,
    restarting: bool = False,
) -> str:
    # Docker pause хранится отдельным флагом:
    # State.Status при этом может оставаться "running".
    # Поэтому transitional state имеет приоритет над healthcheck.
    if paused or state_name == "paused":
        return "warn"

    if restarting or state_name == "restarting":
        return "warn"

    if state_name == "running":
        if health == "unhealthy":
            return "error"

        if health == "starting":
            return "warn"

        return "ok"

    if state_name == "created":
        return "warn"

    return "error"

def collect_containers(config: dict[str, Any]) -> list[dict[str, Any]]:
    section = config.get("docker", {})

    if not isinstance(section, dict):
        raise DockerProviderError("docker должен быть таблицей")

    names = section.get("names", {})
    if not isinstance(names, dict):
        names = {}

    restart_allow = section.get("restart_allow", [])
    if not isinstance(restart_allow, list):
        restart_allow = []

    restart_set = {
        item
        for item in restart_allow
        if isinstance(item, str)
    }

    try:
        docker = find_command("docker")

        ids_result = run_command(
            [
                docker,
                "ps",
                "-aq",
                "--no-trunc",
            ],
            timeout=10,
        )
    except CommandError as exc:
        raise DockerProviderError(str(exc)) from exc

    if ids_result.returncode != 0:
        raise DockerProviderError(
            ids_result.stderr or "docker ps завершился с ошибкой"
        )

    ids = [
        line.strip()
        for line in ids_result.stdout.splitlines()
        if line.strip()
    ]

    if not ids:
        return []

    try:
        inspect_result = run_command(
            [
                docker,
                "inspect",
                *ids,
            ],
            timeout=15,
        )
    except CommandError as exc:
        raise DockerProviderError(str(exc)) from exc

    if inspect_result.returncode != 0:
        raise DockerProviderError(
            inspect_result.stderr or "docker inspect завершился с ошибкой"
        )

    try:
        inspected = json.loads(inspect_result.stdout)
    except json.JSONDecodeError as exc:
        raise DockerProviderError(
            "Docker вернул некорректный JSON"
        ) from exc

    output: list[dict[str, Any]] = []

    for item in inspected:
        if not isinstance(item, dict):
            continue

        raw_name = str(item.get("Name", "")).lstrip("/")

        if not raw_name:
            continue

        state = item.get("State", {})
        if not isinstance(state, dict):
            state = {}

        state_name = str(state.get("Status", "unknown"))

        paused = bool(
            state.get("Paused", False)
        )

        restarting = bool(
            state.get("Restarting", False)
        )

        if paused:
            effective_state = "paused"
        elif (
            restarting
            or state_name == "restarting"
        ):
            effective_state = "restarting"
        else:
            effective_state = state_name

        health_obj = state.get("Health")
        health: str | None = None

        if isinstance(health_obj, dict):
            raw_health = health_obj.get("Status")
            if isinstance(raw_health, str) and raw_health:
                health = raw_health

        restart_count = item.get("RestartCount", 0)
        if not isinstance(restart_count, int):
            restart_count = 0

        output.append(
            {
                "id": raw_name,
                "name": str(names.get(raw_name, raw_name)),
                "status": _status_for_container(
                    state_name,
                    health,
                    paused=paused,
                    restarting=restarting,
                ),
                "state": effective_state,
                "health": health,
                "uptime_seconds": _container_uptime_seconds(state),
                "restart_count": restart_count,
                "restart_allowed": raw_name in restart_set,
            }
        )

    output.sort(
        key=lambda row: (
            row["status"] != "error",
            row["status"] != "warn",
            row["name"].casefold(),
        )
    )

    return output
