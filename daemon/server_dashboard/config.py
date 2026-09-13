from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


PRIMARY_CONFIG = Path("/etc/server-dashboard/config.toml")
LEGACY_CONFIG = Path("/opt/server-dashboard/config.toml")
DEFAULT_CONFIG = Path(
    os.environ.get(
        "SERVER_DASHBOARD_CONFIG",
        str(
            PRIMARY_CONFIG
            if PRIMARY_CONFIG.is_file()
            else LEGACY_CONFIG
        ),
    )
)


class ConfigError(RuntimeError):
    pass


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            config = tomllib.load(fh)
    except OSError as exc:
        raise ConfigError(f"Не удалось прочитать {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Некорректный TOML в {path}: {exc}") from exc

    if config.get("schema") != 1:
        raise ConfigError(
            f"Неподдерживаемая schema: {config.get('schema')!r}"
        )

    return config


def module_enabled(config: dict[str, Any], module_id: str) -> bool:
    section = config.get("modules", {})
    return isinstance(section, dict) and section.get(module_id) is True


def system_component_enabled(
    config: dict[str, Any],
    component_id: str,
) -> bool:
    section = config.get("system", {})
    return isinstance(section, dict) and section.get(component_id) is True
