from __future__ import annotations

import subprocess
from typing import Any


SYSTEMCTL = "/usr/bin/systemctl"
DOCKER = "/usr/bin/docker"


class ActionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _service_restart_map(
    config: dict[str, Any],
) -> dict[str, str]:
    result: dict[str, str] = {}

    services = config.get(
        "services",
        [],
    )

    if not isinstance(
        services,
        list,
    ):
        return result

    for row in services:
        if not isinstance(
            row,
            dict,
        ):
            continue

        if row.get("restart") is not True:
            continue

        service_id = row.get("id")
        unit = row.get("unit")

        if (
            isinstance(service_id, str)
            and service_id
            and isinstance(unit, str)
            and unit
        ):
            result[service_id] = unit

    return result


def restart_service(
    config: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    allowed = _service_restart_map(
        config
    )

    unit = allowed.get(target)

    if unit is None:
        raise ActionError(
            "target_not_allowed",
            "Перезапуск этой службы запрещён",
        )

    try:
        result = subprocess.run(
            [
                SYSTEMCTL,
                "restart",
                unit,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise ActionError(
            "action_timeout",
            "Перезапуск службы превысил допустимое время",
        ) from exc

    except OSError as exc:
        raise ActionError(
            "action_failed",
            "Не удалось запустить systemctl",
        ) from exc

    if result.returncode != 0:
        raise ActionError(
            "action_failed",
            "Не удалось перезапустить службу",
        )

    return {
        "action": "service.restart",
        "id": target,
        "target": unit,
        "status": "ok",
    }


def restart_container(
    config: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    docker = config.get(
        "docker",
        {},
    )

    if not isinstance(
        docker,
        dict,
    ):
        raise ActionError(
            "configuration_error",
            "Некорректная конфигурация Docker",
        )

    allow = docker.get(
        "restart_allow",
        [],
    )

    if (
        not isinstance(allow, list)
        or target not in allow
    ):
        raise ActionError(
            "target_not_allowed",
            "Перезапуск этого контейнера запрещён",
        )

    try:
        result = subprocess.run(
            [
                DOCKER,
                "restart",
                target,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise ActionError(
            "action_timeout",
            "Перезапуск контейнера превысил допустимое время",
        ) from exc

    except OSError as exc:
        raise ActionError(
            "action_failed",
            "Не удалось запустить Docker CLI",
        ) from exc

    if result.returncode != 0:
        raise ActionError(
            "action_failed",
            "Не удалось перезапустить контейнер",
        )

    return {
        "action": "docker.restart",
        "id": target,
        "target": target,
        "status": "ok",
    }

def _system_power_action(
    action: str,
) -> dict[str, Any]:
    if action not in {
        "reboot",
        "poweroff",
    }:
        raise ActionError(
            "invalid_action",
            "Недопустимое системное действие",
        )

    try:
        result = subprocess.run(
            [
                SYSTEMCTL,
                "--no-block",
                action,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise ActionError(
            "action_timeout",
            "Systemd не принял команду вовремя",
        ) from exc

    except OSError as exc:
        raise ActionError(
            "action_failed",
            "Не удалось запустить systemctl",
        ) from exc

    if result.returncode != 0:
        raise ActionError(
            "action_failed",
            result.stderr.strip()
            or "Systemd не принял команду",
        )

    operation = (
        "system.reboot"
        if action == "reboot"
        else "system.poweroff"
    )

    return {
        "action": operation,
        "status": "accepted",
    }


def reboot_system() -> dict[str, Any]:
    return _system_power_action(
        "reboot"
    )


def poweroff_system() -> dict[str, Any]:
    return _system_power_action(
        "poweroff"
    )

