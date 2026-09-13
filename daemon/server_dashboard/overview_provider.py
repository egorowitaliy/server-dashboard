from __future__ import annotations

from typing import Any, Callable

from .docker_provider import collect_containers
from .fail2ban_provider import collect_jails
from .host import collect_host_metrics
from .config import module_enabled, system_component_enabled
from .schedule_provider import collect_schedule
from .smart_provider import collect_smart
from .storage import collect_storage_metrics
from .systemd_provider import (
    collect_failed_units,
    collect_services,
)


def _capture(
    function: Callable[[], Any],
    default: Any,
) -> tuple[Any, bool]:
    """
    Overview must degrade gracefully.

    Failure of one provider must not make the whole dashboard
    unavailable.
    """
    try:
        return function(), True
    except Exception:
        return default, False


def _aggregate_status(
    rows: list[dict[str, Any]],
) -> tuple[str, int]:
    errors = sum(
        1
        for row in rows
        if row.get("status") == "error"
    )

    warnings = sum(
        1
        for row in rows
        if row.get("status") == "warn"
    )

    if errors:
        return "error", errors + warnings

    if warnings:
        return "warn", warnings

    return "ok", 0


def _storage_attention(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    for row in rows:
        status = row.get("status")

        if status == "missing":
            output.append(
                {
                    "severity": "error",
                    "category": "storage",
                    "target": "system",
                    "title": f"{row['name']} недоступен",
                    "message": "Хранилище не смонтировано.",
                }
            )
            continue

        if status == "error":
            output.append(
                {
                    "severity": "error",
                    "category": "storage",
                    "target": "system",
                    "title": f"Ошибка хранилища «{row['name']}»",
                    "message": "Не удалось получить состояние хранилища.",
                }
            )
            continue

        if status == "warn":
            usage = row.get("usage_percent")

            if isinstance(usage, (int, float)):
                title = (
                    f"{row['name']} заполнен на "
                    f"{usage:.0f}%"
                )
            else:
                title = f"Мало места: {row['name']}"

            output.append(
                {
                    "severity": "warn",
                    "category": "storage",
                    "target": "system",
                    "title": title,
                    "message": "Рекомендуется освободить место.",
                }
            )

    return output


def _service_attention(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    for row in rows:
        status = row.get("status")

        if status == "ok":
            continue

        state = row.get("state")

        if state == "starting":
            title = f"{row['name']} запускается"
        elif state == "stopped":
            title = f"{row['name']} остановлен"
        elif state == "failed":
            title = f"{row['name']} работает с ошибкой"
        else:
            title = f"{row['name']} недоступен"

        output.append(
            {
                "severity": (
                    "warn"
                    if status == "warn"
                    else "error"
                ),
                "category": "services",
                "target": "services",
                "title": title,
                "message": "Проверьте состояние службы.",
            }
        )

    return output


def _docker_attention(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    for row in rows:
        status = row.get("status")

        if status == "ok":
            continue

        state = row.get("state")
        health = row.get("health")

        if health == "unhealthy":
            title = f"{row['name']} работает с ошибкой"
        elif health == "starting":
            title = f"{row['name']} ещё запускается"
        elif state == "restarting":
            title = f"{row['name']} перезапускается"
        elif state == "paused":
            title = f"{row['name']} приостановлен"
        elif state in {"exited", "dead"}:
            title = f"{row['name']} остановлен"
        else:
            title = f"Проблема контейнера «{row['name']}»"

        output.append(
            {
                "severity": (
                    "warn"
                    if status == "warn"
                    else "error"
                ),
                "category": "docker",
                "target": "docker",
                "title": title,
                "message": "Проверьте состояние контейнера.",
            }
        )

    return output


def _smart_attention(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    for row in rows:
        status = row.get("status")

        if status == "ok":
            continue

        if status == "warn":
            title = f"SMART предупреждение: {row['name']}"
        else:
            title = f"Проблема SMART: {row['name']}"

        output.append(
            {
                "severity": status,
                "category": "smart",
                "target": "system",
                "title": title,
                "message": "Проверьте состояние диска.",
            }
        )

    return output


def _schedule_attention(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    for row in rows:
        status = row.get("status")

        if status == "ok":
            continue

        output.append(
            {
                "severity": status,
                "category": "schedule",
                "target": "system",
                "title": f"Проблема расписания «{row['name']}»",
                "message": "Задача не находится в штатном состоянии.",
            }
        )

    return output


def _provider_unavailable(
    name: str,
    category: str,
    target: str,
) -> dict[str, str]:
    return {
        "severity": "error",
        "category": category,
        "target": target,
        "title": f"{name}: данные недоступны",
        "message": "Не удалось получить текущее состояние.",
    }


def collect_overview(
    config: dict[str, Any],
) -> dict[str, Any]:
    services_enabled = module_enabled(config, "services")
    docker_enabled = module_enabled(config, "docker")
    fail2ban_enabled = module_enabled(config, "fail2ban")
    system_enabled = module_enabled(config, "system")
    storage_enabled = system_enabled and system_component_enabled(config, "storage")
    smart_enabled = system_enabled and system_component_enabled(config, "smart")
    schedule_enabled = system_enabled and system_component_enabled(config, "schedule")

    host, host_ok = _capture(lambda: collect_host_metrics(config), None)

    if storage_enabled:
        storage, storage_ok = _capture(lambda: collect_storage_metrics(config), [])
    else:
        storage, storage_ok = [], True

    if services_enabled:
        services, services_ok = _capture(lambda: collect_services(config), [])
        failed_units, failed_units_ok = _capture(collect_failed_units, [])
    else:
        services, services_ok, failed_units, failed_units_ok = [], True, [], True

    if docker_enabled:
        containers, docker_ok = _capture(lambda: collect_containers(config), [])
    else:
        containers, docker_ok = [], True

    if fail2ban_enabled:
        jails, fail2ban_ok = _capture(lambda: collect_jails(config), [])
    else:
        jails, fail2ban_ok = [], True

    if smart_enabled:
        smart, smart_ok = _capture(lambda: collect_smart(config), [])
    else:
        smart, smart_ok = [], True

    if schedule_enabled:
        schedule, schedule_ok = _capture(lambda: collect_schedule(config), [])
    else:
        schedule, schedule_ok = [], True

    service_status, service_issues = _aggregate_status(services)
    if services_enabled and failed_units_ok and failed_units:
        service_status = "error"
        service_issues += len(failed_units)
    docker_status, docker_issues = _aggregate_status(containers)
    smart_status, smart_issues = _aggregate_status(smart)
    schedule_status, schedule_issues = _aggregate_status(schedule)

    active_bans = sum(
        row.get("currently_banned", 0)
        for row in jails
        if isinstance(row.get("currently_banned"), int)
    )
    fail2ban_errors = sum(1 for row in jails if row.get("status") != "ok")
    fail2ban_status = "error" if fail2ban_enabled and (not fail2ban_ok or fail2ban_errors) else "ok"

    attention: list[dict[str, str]] = []
    if not host_ok:
        attention.append(_provider_unavailable("Состояние сервера", "host", "overview"))
    if storage_enabled:
        if storage_ok:
            attention.extend(_storage_attention(storage))
        else:
            attention.append(
                _provider_unavailable("Хранилища", "storage", "system")
            )

    if services_enabled:
        if services_ok:
            attention.extend(_service_attention(services))
        else:
            attention.append(_provider_unavailable("Службы", "services", "services"))
        if failed_units_ok and failed_units:
            attention.append({
                "severity": "error",
                "category": "services",
                "target": "services",
                "title": "Обнаружены неисправные системные службы",
                "message": f"Количество: {len(failed_units)}.",
            })
        elif not failed_units_ok:
            attention.append(_provider_unavailable(
                "Проверка системных служб", "services", "services"
            ))

    if docker_enabled:
        if docker_ok:
            attention.extend(_docker_attention(containers))
        else:
            attention.append(_provider_unavailable("Docker", "docker", "docker"))

    if fail2ban_enabled:
        if not fail2ban_ok:
            attention.append(_provider_unavailable("Fail2Ban", "fail2ban", "fail2ban"))
        elif fail2ban_errors:
            attention.append({
                "severity": "error",
                "category": "fail2ban",
                "target": "fail2ban",
                "title": "Fail2Ban работает с ошибкой",
                "message": "Не удалось получить состояние одной или нескольких защит.",
            })

    if smart_enabled:
        if smart_ok:
            attention.extend(_smart_attention(smart))
        else:
            attention.append(_provider_unavailable("SMART", "smart", "system"))

    if schedule_enabled:
        if schedule_ok:
            attention.extend(_schedule_attention(schedule))
        else:
            attention.append(_provider_unavailable("Расписание", "schedule", "system"))

    severity_order = {"error": 0, "warn": 1, "ok": 2}
    attention.sort(key=lambda item: (
        severity_order.get(item.get("severity", "ok"), 9),
        item.get("title", "").casefold(),
    ))

    summary: dict[str, dict[str, Any]] = {}
    if services_enabled:
        summary["services"] = {
            "status": service_status if services_ok and failed_units_ok else "error",
            "issues": service_issues,
            "total": len(services),
        }
    if docker_enabled:
        summary["docker"] = {
            "status": docker_status if docker_ok else "error",
            "issues": docker_issues,
            "total": len(containers),
        }
    if fail2ban_enabled:
        summary["fail2ban"] = {
            "status": fail2ban_status,
            "jails": len(jails),
            "active_bans": active_bans,
        }
    if smart_enabled:
        summary["smart"] = {
            "status": smart_status if smart_ok else "error",
            "issues": smart_issues,
            "total": len(smart),
        }
    if schedule_enabled:
        summary["schedule"] = {
            "status": schedule_status if schedule_ok else "error",
            "issues": schedule_issues,
            "total": len(schedule),
        }

    return {
        "host": host,
        "storage": storage,
        "summary": summary,
        "attention": attention,
    }


def collect_system_snapshot(
    config: dict[str, Any],
) -> dict[str, Any]:
    enabled = {
        "storage": system_component_enabled(config, "storage"),
        "smart": system_component_enabled(config, "smart"),
        "schedule": system_component_enabled(config, "schedule"),
    }
    result: dict[str, Any] = {
        "storage": [],
        "smart": [],
        "schedule": [],
        "enabled": enabled,
        "sources": {},
    }

    if enabled["storage"]:
        result["storage"], result["sources"]["storage"] = _capture(
            lambda: collect_storage_metrics(config), []
        )
    if enabled["smart"]:
        result["smart"], result["sources"]["smart"] = _capture(
            lambda: collect_smart(config), []
        )
    if enabled["schedule"]:
        result["schedule"], result["sources"]["schedule"] = _capture(
            lambda: collect_schedule(config), []
        )
    return result
