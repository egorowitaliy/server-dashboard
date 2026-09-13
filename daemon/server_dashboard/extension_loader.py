from __future__ import annotations

import importlib.util
import re
import stat
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

from .module_api import (
    DashboardOperationError,
    ExtensionContext,
    ExtensionRegistry,
    ModuleDescriptor,
    ModuleRegistry,
)


EXTENSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ICON_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
SAFE_ASSET_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}\.(?:js|css|svg)$")


def _secure_path(
    path: Path,
    *,
    directory: bool | None = None,
) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False

    if stat.S_ISLNK(info.st_mode):
        return False
    if info.st_uid != 0:
        return False
    if info.st_mode & 0o022:
        return False
    if directory is True and not stat.S_ISDIR(info.st_mode):
        return False
    if directory is False and not stat.S_ISREG(info.st_mode):
        return False
    return True


def _secure_ancestor_chain(path: Path) -> bool:
    """Проверяет все компоненты абсолютного пути до самого объекта.

    Root-daemon не должен загружать trusted extension из дерева, которое
    можно подменить через writable/symlink родительский каталог.
    """
    if not path.is_absolute():
        return False

    current = Path("/")

    for part in path.parts[1:]:
        current = current / part

        try:
            info = current.lstat()
        except OSError:
            return False

        if stat.S_ISLNK(info.st_mode):
            return False
        if info.st_uid != 0:
            return False
        if info.st_mode & 0o022:
            return False

    return True


def _strict_table(
    manifest: dict[str, Any],
    key: str,
    allowed: set[str],
) -> dict[str, Any]:
    if key not in manifest:
        return {}

    value = manifest[key]

    if not isinstance(value, dict):
        raise RuntimeError(f"{key} должен быть таблицей")

    unknown = set(value) - allowed
    if unknown:
        raise RuntimeError(
            f"{key}: неизвестные поля: {', '.join(sorted(unknown))}"
        )

    return value


def _load_python(path: Path, extension_id: str) -> ModuleType:
    name = f"server_dashboard_extension_{extension_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Не удалось загрузить backend расширения")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_extensions(
    registry: ModuleRegistry,
    dashboard_config: dict[str, Any],
) -> None:
    section = dashboard_config.get("extensions", {})
    if not isinstance(section, dict):
        return

    root_value = section.get("root", "/opt/server-dashboard-extensions")
    enabled_value = section.get("enabled", [])
    if not isinstance(root_value, str) or not root_value:
        registry.extension_errors.append({
            "id": "extensions",
            "message": "Некорректный extensions.root",
        })
        return
    if not isinstance(enabled_value, list):
        registry.extension_errors.append({
            "id": "extensions",
            "message": "Некорректный extensions.enabled",
        })
        return

    root = Path(root_value)

    if enabled_value and (
        not _secure_path(root, directory=True)
        or not _secure_ancestor_chain(root)
    ):
        registry.extension_errors.append({
            "id": "extensions",
            "message": (
                "Каталог расширений или один из его родительских каталогов "
                "отсутствует/имеет небезопасные права"
            ),
        })
        return

    seen_enabled: set[str] = set()

    for raw_id in enabled_value:
        if not isinstance(raw_id, str) or EXTENSION_ID_RE.fullmatch(raw_id) is None:
            registry.extension_errors.append({
                "id": str(raw_id),
                "message": "Некорректный id расширения",
            })
            continue

        extension_id = raw_id

        if extension_id in seen_enabled:
            registry.extension_errors.append({
                "id": extension_id,
                "message": "Повторяющийся id расширения в extensions.enabled",
            })
            continue

        seen_enabled.add(extension_id)

        if extension_id in registry.modules:
            registry.extension_errors.append({
                "id": extension_id,
                "message": "ID расширения конфликтует с уже зарегистрированным модулем",
            })
            continue

        ext_root = root / extension_id
        manifest_path = ext_root / "manifest.toml"

        modules_before = dict(registry.modules)
        operations_before = dict(registry.operations)
        assets_before = dict(registry.assets)

        try:
            if not _secure_path(ext_root, directory=True):
                raise RuntimeError("Каталог расширения отсутствует или небезопасен")
            if not _secure_path(manifest_path, directory=False):
                raise RuntimeError("manifest.toml отсутствует или небезопасен")
            try:
                if ext_root.resolve().parent != root.resolve():
                    raise RuntimeError("Каталог расширения выходит за extensions.root")
            except OSError as exc:
                raise RuntimeError("Не удалось проверить путь расширения") from exc
            if not _secure_path(ext_root) or not _secure_path(manifest_path):
                raise RuntimeError(
                    "Расширение должно принадлежать root и не быть доступно на запись группе/остальным"
                )
            with manifest_path.open("rb") as fh:
                manifest = tomllib.load(fh)

            allowed_manifest_keys = {
                "api",
                "id",
                "name",
                "version",
                "icon",
                "order",
                "page",
                "placements",
                "backend",
                "assets",
            }
            unknown_manifest_keys = set(manifest) - allowed_manifest_keys
            if unknown_manifest_keys:
                raise RuntimeError(
                    "manifest: неизвестные поля: "
                    + ", ".join(sorted(unknown_manifest_keys))
                )

            if manifest.get("api") != 1:
                raise RuntimeError("Неподдерживаемая версия extension API")
            if manifest.get("id") != extension_id:
                raise RuntimeError("id в manifest не совпадает с именем каталога")

            name = manifest.get("name")
            icon = manifest.get("icon", "activity")
            order = manifest.get("order", 100)
            version = manifest.get("version")
            page = manifest.get("page", False)
            placements_value = manifest.get("placements", [])

            if not isinstance(name, str) or not name.strip() or len(name) > 128:
                raise RuntimeError("Не задано или слишком длинное name")
            if not isinstance(icon, str) or ICON_ID_RE.fullmatch(icon) is None:
                raise RuntimeError("Некорректный icon")
            if not isinstance(order, int) or isinstance(order, bool) or not 0 <= order <= 10000:
                raise RuntimeError("Некорректный order")
            if version is not None and (
                not isinstance(version, str) or VERSION_RE.fullmatch(version) is None
            ):
                raise RuntimeError("Некорректный version")
            if not isinstance(page, bool):
                raise RuntimeError("Некорректный page")
            if (
                not isinstance(placements_value, list)
                or len(set(placements_value)) != len(placements_value)
                or not all(
                    isinstance(item, str) and item in {"overview", "system"}
                    for item in placements_value
                )
            ):
                raise RuntimeError("Некорректный placements")

            assets: list[dict[str, str]] = []
            assets_section = _strict_table(
                manifest,
                "assets",
                {"css", "js"},
            )

            for kind in ("css", "js"):
                value = assets_section.get(kind)
                if value is None:
                    continue
                if not isinstance(value, str) or SAFE_ASSET_RE.fullmatch(value) is None:
                    raise RuntimeError(f"Некорректный assets.{kind}")
                asset_path = ext_root / "public" / value
                if (
                    not _secure_path(asset_path.parent, directory=True)
                    or not _secure_path(asset_path, directory=False)
                ):
                    raise RuntimeError(f"Asset {value} отсутствует или небезопасен")
                assets.append({
                    "type": kind,
                    "name": value,
                    "url": (
                        f"/api/extensions/{extension_id}/asset/{value}"
                        f"?v={version if version is not None else '0'}"
                    ),
                })

            if (page or placements_value) and not isinstance(
                assets_section.get("js"),
                str,
            ):
                raise RuntimeError(
                    "UI-расширение (page/placements) требует assets.js"
                )

            config_path = ext_root / "config.toml"
            extension_config: dict[str, Any] = {}
            if config_path.exists() or config_path.is_symlink():
                if not _secure_path(config_path, directory=False):
                    raise RuntimeError("config.toml расширения имеет небезопасные права")
                with config_path.open("rb") as fh:
                    extension_config = tomllib.load(fh)

            descriptor = ModuleDescriptor(
                id=extension_id,
                name=name,
                icon=icon,
                order=order,
                enabled=True,
                page=page,
                placements=tuple(placements_value),
                builtin=False,
                version=str(version) if version is not None else None,
                assets=tuple(assets),
            )
            registry.register_module(descriptor)

            mime_by_suffix = {
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml",
            }
            public_root = ext_root / "public"
            if _secure_path(public_root, directory=True):
                for asset_path in public_root.iterdir():
                    if (
                        SAFE_ASSET_RE.fullmatch(asset_path.name) is None
                        or not _secure_path(asset_path, directory=False)
                    ):
                        continue
                    registry.register_asset(
                        extension_id,
                        asset_path.name,
                        asset_path,
                        mime_by_suffix.get(
                            asset_path.suffix.lower(),
                            "application/octet-stream",
                        ),
                    )

            backend_section = _strict_table(
                manifest,
                "backend",
                {"entrypoint"},
            )
            entrypoint = backend_section.get("entrypoint")

            if entrypoint is not None:
                if entrypoint != "backend.py":
                    raise RuntimeError("В extension API v1 поддерживается только backend.py")
                backend_path = ext_root / entrypoint
                if not _secure_path(backend_path, directory=False):
                    raise RuntimeError("backend.py отсутствует или имеет небезопасные права")
                module = _load_python(backend_path, extension_id)
                register = getattr(module, "register", None)
                if not callable(register):
                    raise RuntimeError("backend.py не экспортирует register()")
                context = ExtensionContext(
                    id=extension_id,
                    root=ext_root,
                    config=extension_config,
                    dashboard_config=dashboard_config,
                )
                register(ExtensionRegistry(registry, extension_id), context)

        except Exception as exc:
            registry.modules = modules_before
            registry.operations = operations_before
            registry.assets = assets_before
            registry.extension_errors.append({
                "id": extension_id,
                "message": str(exc),
            })
