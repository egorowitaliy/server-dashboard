from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DEFAULT_CONFIG, ConfigError, load_config
from .host import HostMetricError, collect_host_metrics
from .storage import StorageMetricError, collect_storage_metrics


def build_snapshot(config_path: Path) -> dict:
    config = load_config(config_path)

    timezone_name = config.get(
        "dashboard",
        {},
    ).get(
        "timezone",
        "UTC",
    )

    timezone = ZoneInfo(timezone_name)

    return {
        "schema": 1,
        "generated_at": datetime.now(timezone).isoformat(
            timespec="seconds"
        ),
        "host": collect_host_metrics(config),
        "storage": collect_storage_metrics(config),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Server Dashboard probe",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        snapshot = build_snapshot(args.config)
    except (
        ConfigError,
        HostMetricError,
        StorageMetricError,
        OSError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
