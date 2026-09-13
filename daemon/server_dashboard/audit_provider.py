from __future__ import annotations

import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


AUDIT_PATH = Path(
    "/var/log/server-dashboard/audit.log"
)

MAX_ENTRIES = 500
MAX_FILE_BYTES = 4 * 1024 * 1024


class AuditProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_timestamp(
    value: str,
) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(
            value
        )
    except ValueError:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None

    return parsed.astimezone(timezone.utc)


def _parse_line(
    line: str,
) -> dict[str, Any] | None:
    parts = line.strip().split()

    if len(parts) < 5:
        return None

    timestamp = parts[0]

    parsed_time = _parse_timestamp(
        timestamp
    )

    if parsed_time is None:
        return None

    user: str | None = None
    client_ip: str | None = None
    action: str | None = None
    result: str | None = None

    extras: dict[str, str] = {}

    action_seen = False

    for token in parts[1:]:
        if "=" not in token:
            continue

        key, value = token.split(
            "=",
            1,
        )

        if key == "user" and user is None:
            user = value
            continue

        if (
            key == "ip"
            and client_ip is None
            and not action_seen
        ):
            client_ip = value
            continue

        if key == "action" and action is None:
            action = value
            action_seen = True
            continue

        if key == "result":
            result = value
            continue

        if action_seen:
            extras[key] = value

    if (
        user is None
        or client_ip is None
        or action is None
        or result is None
    ):
        return None

    return {
        "timestamp": timestamp,
        "_sort": parsed_time,
        "user": user,
        "client_ip": client_ip,
        "action": action,
        "result": result,
        "details": extras,
    }


def _open_log(
    path: Path,
) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(
            path,
            "rt",
            encoding="utf-8",
            errors="replace",
        )

    return path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    )


def _candidate_logs() -> list[Path]:
    parent = AUDIT_PATH.parent
    name = AUDIT_PATH.name

    candidates: list[Path] = []

    for path in parent.glob(
        f"{name}*"
    ):
        try:
            if path.is_symlink():
                continue

            if not path.is_file():
                continue

            if (
                path != AUDIT_PATH
                and not path.name.startswith(
                    f"{name}."
                )
            ):
                continue

            if path.stat().st_size > MAX_FILE_BYTES:
                continue

        except OSError:
            continue

        candidates.append(
            path
        )

    return candidates


def collect_audit(
    config: dict[str, Any],
) -> dict[str, Any]:
    del config

    if not AUDIT_PATH.parent.is_dir():
        raise AuditProviderError(
            "audit_unavailable",
            "Каталог журнала аудита недоступен",
        )

    entries: list[
        dict[str, Any]
    ] = []

    for path in _candidate_logs():
        try:
            with _open_log(path) as fh:
                for line in fh:
                    parsed = _parse_line(
                        line
                    )

                    if parsed is not None:
                        entries.append(
                            parsed
                        )

        except (
            OSError,
            gzip.BadGzipFile,
        ):
            continue

    entries.sort(
        key=lambda row:
            row["_sort"],
        reverse=True,
    )

    entries = entries[
        :MAX_ENTRIES
    ]

    for row in entries:
        row.pop(
            "_sort",
            None,
        )

    return {
        "count": len(entries),
        "limit": MAX_ENTRIES,
        "entries": entries,
    }
