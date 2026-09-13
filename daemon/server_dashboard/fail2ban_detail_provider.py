from __future__ import annotations

import ast
import ipaddress
from typing import Any

from .process import CommandError, find_command, run_command


class Fail2BanDetailError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail2ban_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    section = config.get(
        "fail2ban",
        {},
    )

    if not isinstance(
        section,
        dict,
    ):
        raise Fail2BanDetailError(
            "configuration_error",
            "Некорректная конфигурация Fail2Ban",
        )

    return section


def _known_jails(
    config: dict[str, Any],
) -> dict[str, str]:
    section = _fail2ban_config(
        config
    )

    names = section.get(
        "names",
        {},
    )

    if not isinstance(
        names,
        dict,
    ):
        return {}

    return {
        str(jail): str(name)
        for jail, name in names.items()
        if isinstance(jail, str)
        and jail
        and isinstance(name, str)
        and name
    }


def _unban_allow(
    config: dict[str, Any],
) -> set[str]:
    section = _fail2ban_config(
        config
    )

    values = section.get(
        "unban_allow",
        [],
    )

    if not isinstance(
        values,
        list,
    ):
        return set()

    return {
        value
        for value in values
        if isinstance(value, str)
        and value
    }


def _require_known_jail(
    config: dict[str, Any],
    jail: str,
) -> str:
    names = _known_jails(
        config
    )

    if jail not in names:
        raise Fail2BanDetailError(
            "target_not_allowed",
            "Jail не разрешён конфигурацией",
        )

    return names[jail]


def _parse_banned(
    output: str,
) -> list[str]:
    value = output.strip()

    if not value:
        return []

    try:
        parsed = ast.literal_eval(
            value
        )
    except (
        SyntaxError,
        ValueError,
    ) as exc:
        raise Fail2BanDetailError(
            "backend_error",
            "Не удалось разобрать список блокировок",
        ) from exc

    if not isinstance(
        parsed,
        list,
    ):
        raise Fail2BanDetailError(
            "backend_error",
            "Некорректный ответ Fail2Ban",
        )

    result: list[str] = []

    for item in parsed:
        if not isinstance(
            item,
            str,
        ):
            continue

        try:
            canonical = str(
                ipaddress.ip_address(
                    item
                )
            )
        except ValueError:
            continue

        result.append(
            canonical
        )

    return result


def collect_banned_ips(
    config: dict[str, Any],
    jail: str,
) -> dict[str, Any]:
    name = _require_known_jail(
        config,
        jail,
    )

    try:
        client = find_command(
            "fail2ban-client"
        )

        result = run_command(
            [
                client,
                "get",
                jail,
                "banned",
            ],
            timeout=10,
        )

    except CommandError as exc:
        raise Fail2BanDetailError(
            "backend_error",
            str(exc),
        ) from exc

    if result.returncode != 0:
        raise Fail2BanDetailError(
            "backend_error",
            result.stderr.strip()
            or "Не удалось получить блокировки Fail2Ban",
        )

    banned = _parse_banned(
        result.stdout
    )

    return {
        "id": jail,
        "name": name,
        "count": len(banned),
        "unban_allowed":
            jail in _unban_allow(
                config
            ),
        "banned_ips": banned,
    }


def unban_ip(
    config: dict[str, Any],
    jail: str,
    address: str,
) -> dict[str, Any]:
    _require_known_jail(
        config,
        jail,
    )

    if jail not in _unban_allow(
        config
    ):
        raise Fail2BanDetailError(
            "target_not_allowed",
            "Разблокировка для этого jail запрещена",
        )

    try:
        canonical = str(
            ipaddress.ip_address(
                address
            )
        )
    except ValueError as exc:
        raise Fail2BanDetailError(
            "invalid_ip",
            "Некорректный IP-адрес",
        ) from exc

    try:
        client = find_command(
            "fail2ban-client"
        )

        result = run_command(
            [
                client,
                "set",
                jail,
                "unbanip",
                canonical,
            ],
            timeout=10,
        )

    except CommandError as exc:
        raise Fail2BanDetailError(
            "action_failed",
            str(exc),
        ) from exc

    if result.returncode != 0:
        raise Fail2BanDetailError(
            "action_failed",
            result.stderr.strip()
            or "Fail2Ban не выполнил разблокировку",
        )

    return {
        "action": "fail2ban.unban",
        "jail": jail,
        "ip": canonical,
        "status": "ok",
    }
