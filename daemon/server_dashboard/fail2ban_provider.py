from __future__ import annotations

import re
from typing import Any

from .process import CommandError, find_command, run_command


class Fail2BanProviderError(RuntimeError):
    pass


NUMBER_FIELDS = {
    "currently_failed": r"Currently failed:\s*(\d+)",
    "total_failed": r"Total failed:\s*(\d+)",
    "currently_banned": r"Currently banned:\s*(\d+)",
    "total_banned": r"Total banned:\s*(\d+)",
}


def _jail_list(output: str) -> list[str]:
    for line in output.splitlines():
        if "Jail list:" not in line:
            continue

        _, value = line.split("Jail list:", 1)

        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    return []


def _parse_jail_status(output: str) -> dict[str, int] | None:
    result: dict[str, int] = {}

    for key, pattern in NUMBER_FIELDS.items():
        match = re.search(pattern, output)

        if match is None:
            return None

        result[key] = int(match.group(1))

    return result


def collect_jails(config: dict[str, Any]) -> list[dict[str, Any]]:
    section = config.get("fail2ban", {})

    if not isinstance(section, dict):
        raise Fail2BanProviderError("fail2ban должен быть таблицей")

    names = section.get("names", {})
    if not isinstance(names, dict):
        names = {}

    unban_allow = section.get("unban_allow", [])
    if not isinstance(unban_allow, list):
        unban_allow = []

    unban_set = {
        item
        for item in unban_allow
        if isinstance(item, str)
    }

    try:
        client = find_command("fail2ban-client")

        summary = run_command(
            [client, "status"],
            timeout=5,
        )
    except CommandError as exc:
        raise Fail2BanProviderError(str(exc)) from exc

    if summary.returncode != 0:
        raise Fail2BanProviderError(
            summary.stderr or "fail2ban-client status завершился с ошибкой"
        )

    jails = _jail_list(summary.stdout)
    output: list[dict[str, Any]] = []

    for jail in jails:
        try:
            result = run_command(
                [
                    client,
                    "status",
                    jail,
                ],
                timeout=3,
            )
        except CommandError:
            result = None

        if result is None or result.returncode != 0:
            output.append(
                {
                    "id": jail,
                    "name": str(names.get(jail, jail)),
                    "status": "error",
                    "currently_failed": None,
                    "total_failed": None,
                    "currently_banned": None,
                    "total_banned": None,
                    "unban_allowed": jail in unban_set,
                }
            )
            continue

        parsed = _parse_jail_status(result.stdout)

        if parsed is None:
            output.append(
                {
                    "id": jail,
                    "name": str(names.get(jail, jail)),
                    "status": "error",
                    "currently_failed": None,
                    "total_failed": None,
                    "currently_banned": None,
                    "total_banned": None,
                    "unban_allowed": jail in unban_set,
                }
            )
            continue

        output.append(
            {
                "id": jail,
                "name": str(names.get(jail, jail)),
                "status": "ok",
                **parsed,
                "unban_allowed": jail in unban_set,
            }
        )

    output.sort(key=lambda row: row["name"].casefold())

    return output
