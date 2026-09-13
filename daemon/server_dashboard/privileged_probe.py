from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, ConfigError, load_config
from .module_api import DashboardOperationError
from .module_registry import build_registry


PROTOCOL_VERSION = 1


def dispatch(
    operation: str,
    config: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> Any:
    registry = build_registry(config)
    return registry.dispatch(operation, params or {})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Server Dashboard privileged probe",
    )
    parser.add_argument("operation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--params-json", default="{}")
    args = parser.parse_args()

    try:
        params = json.loads(args.params_json)
        if not isinstance(params, dict):
            raise ValueError("params-json должен быть JSON-объектом")
        config = load_config(args.config)
        data = dispatch(args.operation, config, params)
        response = {"version": PROTOCOL_VERSION, "ok": True, "data": data}
        rc = 0
    except (ConfigError, DashboardOperationError, ValueError) as exc:
        code = getattr(exc, "code", "operation_failed")
        message = getattr(exc, "message", str(exc))
        response = {
            "version": PROTOCOL_VERSION,
            "ok": False,
            "error": {"code": code, "message": message},
        }
        rc = 1
    except Exception as exc:
        response = {
            "version": PROTOCOL_VERSION,
            "ok": False,
            "error": {"code": "operation_failed", "message": str(exc)},
        }
        rc = 1

    print(json.dumps(
        response,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    ))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
