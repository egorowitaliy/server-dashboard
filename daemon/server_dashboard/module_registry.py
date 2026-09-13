from __future__ import annotations

import ipaddress
import re
from typing import Any

from . import __version__
from .action_provider import (
    poweroff_system,
    reboot_system,
    restart_container,
    restart_service,
)
from .audit_provider import collect_audit
from .config import module_enabled, system_component_enabled
from .docker_provider import collect_containers
from .docs_provider import list_documents, read_document
from .extension_loader import load_extensions
from .fail2ban_detail_provider import collect_banned_ips, unban_ip
from .fail2ban_provider import collect_jails
from .host import collect_live_host_metrics
from .module_api import (
    DashboardOperationError,
    ModuleDescriptor,
    ModuleRegistry,
    OperationSpec,
    exact_string_params,
    no_params,
)
from .overview_provider import collect_overview, collect_system_snapshot
from .schedule_provider import collect_schedule
from .smart_provider import collect_smart
from .systemd_provider import collect_services


TARGET_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


BUILTIN_MODULES = (
    ("overview", "Обзор", "home", 10),
    ("services", "Службы", "gear", 20),
    ("docker", "Docker", "box", 30),
    ("fail2ban", "Fail2Ban", "shield", 40),
    ("system", "Система", "display", 50),
    ("docs", "Документация", "docs", 60),
    ("audit", "Аудит", "audit", 70),
)


def _target(params: dict[str, Any]) -> None:
    exact_string_params(("target",), max_length=128)(params)
    if TARGET_RE.fullmatch(params["target"]) is None:
        raise DashboardOperationError("invalid_target", "Некорректный target")


def _jail(params: dict[str, Any]) -> None:
    exact_string_params(("jail",), max_length=128)(params)
    if TARGET_RE.fullmatch(params["jail"]) is None:
        raise DashboardOperationError("invalid_target", "Некорректный jail")


def _unban(params: dict[str, Any]) -> None:
    exact_string_params(("jail", "ip"), max_length=128)(params)
    if TARGET_RE.fullmatch(params["jail"]) is None:
        raise DashboardOperationError("invalid_target", "Некорректный jail")
    try:
        ipaddress.ip_address(params["ip"])
    except ValueError as exc:
        raise DashboardOperationError("invalid_ip", "Некорректный IP-адрес") from exc


def _docs_read(params: dict[str, Any]) -> None:
    exact_string_params(("document",), max_length=512)(params)


def _system_component(
    config: dict[str, Any],
    component: str,
    function,
):
    if not system_component_enabled(config, component):
        raise DashboardOperationError(
            "component_disabled",
            f"Компонент system.{component} отключён",
        )
    return function(config)


def build_registry(config: dict[str, Any]) -> ModuleRegistry:
    registry = ModuleRegistry(config)

    for module_id, name, icon, order in BUILTIN_MODULES:
        registry.register_module(
            ModuleDescriptor(
                id=module_id,
                name=name,
                icon=icon,
                order=order,
                enabled=module_enabled(config, module_id),
                page=True,
            )
        )

    # Core operations are not tied to a page module.
    registry.register_operation(OperationSpec(
        "health", "read",
        lambda cfg, p: {"status": "ok", "version": __version__},
        no_params,
    ))
    registry.register_operation(OperationSpec(
        "modules.list", "read",
        lambda cfg, p: registry.describe_modules(
            server_name=str(
                cfg.get(
                    "dashboard",
                    {},
                ).get(
                    "server_name",
                    "Server",
                )
            ),
            product_name="Dashboard",
            version=__version__,
        ),
        no_params,
    ))
    registry.register_operation(OperationSpec(
        "operation.describe", "read",
        lambda cfg, p: registry.describe_operation(p["operation"]),
        exact_string_params(("operation",), max_length=128),
    ))

    registry.register_operation(OperationSpec(
        "extension.asset.describe", "read",
        lambda cfg, p: registry.describe_asset(p["module"], p["asset"]),
        exact_string_params(("module", "asset"), max_length=128),
    ))

    def add(name, kind, module_id, handler, validator=no_params):
        registry.register_operation(OperationSpec(
            name=name,
            kind=kind,
            module_id=module_id,
            handler=handler,
            validator=validator,
        ))

    add("overview", "read", "overview", lambda cfg, p: collect_overview(cfg))
    add("host.snapshot", "read", "overview", lambda cfg, p: collect_live_host_metrics(cfg))

    add("services.list", "read", "services", lambda cfg, p: collect_services(cfg))
    add("service.restart", "action", "services", lambda cfg, p: restart_service(cfg, p["target"]), _target)

    add("docker.list", "read", "docker", lambda cfg, p: collect_containers(cfg))
    add("docker.restart", "action", "docker", lambda cfg, p: restart_container(cfg, p["target"]), _target)

    add("fail2ban.list", "read", "fail2ban", lambda cfg, p: collect_jails(cfg))
    add("fail2ban.banned", "read", "fail2ban", lambda cfg, p: collect_banned_ips(cfg, p["jail"]), _jail)
    add("fail2ban.unban", "action", "fail2ban", lambda cfg, p: unban_ip(cfg, p["jail"], p["ip"]), _unban)

    add("system.snapshot", "read", "system", lambda cfg, p: collect_system_snapshot(cfg))
    add("schedule.list", "read", "system", lambda cfg, p: _system_component(cfg, "schedule", collect_schedule))
    add("smart.list", "read", "system", lambda cfg, p: _system_component(cfg, "smart", collect_smart))
    add("system.reboot", "action", "system", lambda cfg, p: reboot_system())
    add("system.poweroff", "action", "system", lambda cfg, p: poweroff_system())

    add("docs.list", "read", "docs", lambda cfg, p: list_documents(cfg))
    add("docs.read", "read", "docs", lambda cfg, p: read_document(cfg, p["document"]), _docs_read)

    add("audit.list", "read", "audit", lambda cfg, p: collect_audit(cfg))

    load_extensions(registry, config)
    return registry
