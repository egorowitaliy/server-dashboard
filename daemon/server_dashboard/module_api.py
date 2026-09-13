from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


Handler = Callable[[dict[str, Any], dict[str, Any]], Any]
Validator = Callable[[dict[str, Any]], None]


class DashboardOperationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ModuleDescriptor:
    id: str
    name: str
    icon: str
    order: int
    enabled: bool
    page: bool = True
    placements: tuple[str, ...] = ()
    builtin: bool = True
    version: str | None = None
    assets: tuple[dict[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "order": self.order,
            "enabled": self.enabled,
            "page": self.page,
            "placements": list(self.placements),
            "builtin": self.builtin,
            "version": self.version,
            "assets": [dict(item) for item in self.assets],
        }


@dataclass(frozen=True)
class OperationSpec:
    name: str
    kind: str
    handler: Handler
    validator: Validator
    module_id: str | None = None


@dataclass(frozen=True)
class ExtensionContext:
    id: str
    root: Path
    config: dict[str, Any]
    dashboard_config: dict[str, Any]


class ExtensionRegistry:
    """Ограниченный интерфейс регистрации для одного расширения.

    Backend-расширение не получает внутренний ModuleRegistry напрямую.
    Это не песочница для недоверенного Python-кода, но такой интерфейс
    фиксирует контракт Extension API и не позволяет случайно регистрировать
    операции от имени другого модуля или как core-операции.
    """

    def __init__(self, registry: "ModuleRegistry", module_id: str) -> None:
        self._registry = registry
        self._module_id = module_id

    def register_operation(self, spec: OperationSpec) -> None:
        if spec.module_id != self._module_id:
            raise DashboardOperationError(
                "configuration_error",
                (
                    f"Операция {spec.name!r} должна принадлежать "
                    f"модулю {self._module_id!r}"
                ),
            )
        self._registry.register_operation(spec)


class ModuleRegistry:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.modules: dict[str, ModuleDescriptor] = {}
        self.operations: dict[str, OperationSpec] = {}
        self.extension_errors: list[dict[str, str]] = []
        self.assets: dict[tuple[str, str], dict[str, str]] = {}

    def register_module(self, descriptor: ModuleDescriptor) -> None:
        if descriptor.id in self.modules:
            raise DashboardOperationError(
                "configuration_error",
                f"Повторяющийся модуль: {descriptor.id}",
            )
        self.modules[descriptor.id] = descriptor

    def register_operation(self, spec: OperationSpec) -> None:
        if spec.kind not in {"read", "action"}:
            raise DashboardOperationError(
                "configuration_error",
                f"Некорректный kind операции {spec.name}",
            )
        if spec.name in self.operations:
            raise DashboardOperationError(
                "configuration_error",
                f"Повторяющаяся операция: {spec.name}",
            )
        self.operations[spec.name] = spec

    def dispatch(self, operation: str, params: dict[str, Any]) -> Any:
        spec = self.operations.get(operation)
        if spec is None:
            raise DashboardOperationError(
                "unknown_operation",
                "Операция не поддерживается",
            )
        if spec.module_id is not None:
            module = self.modules.get(spec.module_id)
            if module is None or not module.enabled:
                raise DashboardOperationError(
                    "module_disabled",
                    f"Модуль {spec.module_id!r} отключён",
                )
        spec.validator(params)

        try:
            return spec.handler(self.config, params)
        except DashboardOperationError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None)

            if isinstance(code, str) and code and isinstance(message, str) and message:
                raise DashboardOperationError(code, message) from exc

            raise

    def describe_operation(self, operation: str) -> dict[str, Any]:
        spec = self.operations.get(operation)
        if spec is None:
            raise DashboardOperationError(
                "unknown_operation",
                "Операция не поддерживается",
            )
        if spec.module_id is not None:
            module = self.modules.get(spec.module_id)
            if module is None or not module.enabled:
                raise DashboardOperationError(
                    "module_disabled",
                    f"Модуль {spec.module_id!r} отключён",
                )
        return {
            "operation": spec.name,
            "kind": spec.kind,
            "module": spec.module_id,
        }


    def register_asset(
        self,
        module_id: str,
        name: str,
        path: Path,
        mime: str,
    ) -> None:
        key = (module_id, name)
        if key in self.assets:
            raise DashboardOperationError(
                "configuration_error",
                f"Повторяющийся asset: {module_id}/{name}",
            )
        self.assets[key] = {
            "path": str(path),
            "mime": mime,
        }

    def describe_asset(self, module_id: str, name: str) -> dict[str, str]:
        module = self.modules.get(module_id)
        if module is None or not module.enabled:
            raise DashboardOperationError(
                "module_disabled",
                f"Модуль {module_id!r} отключён",
            )
        asset = self.assets.get((module_id, name))
        if asset is None:
            raise DashboardOperationError(
                "asset_not_found",
                "Asset не найден",
            )
        return dict(asset)

    def describe_modules(
        self,
        *,
        server_name: str,
        product_name: str,
        version: str,
    ) -> dict[str, Any]:
        modules = sorted(
            (item.as_dict() for item in self.modules.values()),
            key=lambda item: (item["order"], item["name"].casefold()),
        )
        default_page = next(
            (
                item["id"]
                for item in modules
                if item["enabled"] and item["page"]
            ),
            None,
        )
        title = (
            f"{server_name} {product_name}"
        ).strip()

        return {
            "server_name": server_name,
            "product_name": product_name,
            "title": title,
            "version": version,
            "default_page": default_page,
            "modules": modules,
            "extension_errors": list(self.extension_errors),
        }


def no_params(params: dict[str, Any]) -> None:
    if params:
        raise DashboardOperationError(
            "invalid_params",
            "Эта операция не принимает параметры",
        )


def exact_string_params(
    names: tuple[str, ...],
    *,
    max_length: int = 512,
) -> Validator:
    expected = set(names)

    def validate(params: dict[str, Any]) -> None:
        if set(params) != expected:
            raise DashboardOperationError(
                "invalid_params",
                "Некорректный набор параметров",
            )
        for name in names:
            value = params.get(name)
            if (
                not isinstance(value, str)
                or not value
                or len(value) > max_length
                or "\x00" in value
            ):
                raise DashboardOperationError(
                    "invalid_params",
                    f"Некорректный параметр {name}",
                )

    return validate
