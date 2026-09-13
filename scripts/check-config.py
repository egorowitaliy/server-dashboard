#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PRIMARY_CONFIG = Path("/etc/server-dashboard/config.toml")
LEGACY_CONFIG = Path("/opt/server-dashboard/config.toml")
DEFAULT_CONFIG = PRIMARY_CONFIG if PRIMARY_CONFIG.is_file() else LEGACY_CONFIG
MODULE_IDS = {
    "overview",
    "services",
    "docker",
    "fail2ban",
    "system",
    "docs",
    "audit",
}
SYSTEM_COMPONENTS = {
    "storage",
    "smart",
    "schedule",
}
TOP_LEVEL = {
    "schema",
    "dashboard",
    "modules",
    "system",
    "extensions",
    "host",
    "storage",
    "services",
    "docker",
    "fail2ban",
    "smart",
    "schedule",
    "docs",
}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Checker:
    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        print(f"[ OK ] {message}")

    def info(self, message: str) -> None:
        print(f"[INFO] {message}")

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f"[WARN] {message}")

    def error(self, message: str) -> None:
        self.errors += 1
        print(f"[ERR ] {message}")


def table(cfg: dict, key: str) -> dict | None:
    value = cfg.get(key)
    return value if isinstance(value, dict) else None


def module_enabled(cfg: dict, module_id: str) -> bool:
    modules = table(cfg, "modules") or {}
    return modules.get(module_id) is True


def component_enabled(cfg: dict, component_id: str) -> bool:
    system = table(cfg, "system") or {}
    return system.get(component_id) is True


def check_unknown(checker: Checker, where: str, obj: dict, allowed: set[str]) -> None:
    for key in sorted(set(obj) - allowed):
        checker.error(f"{where}: неизвестный параметр {key!r}")


def need_string(checker: Checker, where: str, obj: dict, key: str) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        checker.error(f"{where}: {key} должен быть непустой строкой")
        return None
    return value


def need_bool(checker: Checker, where: str, obj: dict, key: str) -> bool | None:
    value = obj.get(key)
    if not isinstance(value, bool):
        checker.error(f"{where}: {key} должен быть true или false")
        return None
    return value


def check_id(checker: Checker, where: str, value: object) -> None:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        checker.error(f"{where}: некорректный id")


def check_unique_rows(checker: Checker, where: str, rows: object) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        checker.error(f"{where}: ожидается непустой массив таблиц")
        return []
    result: list[dict] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            checker.error(f"{where}[{index}]: ожидается таблица")
            continue
        item_id = row.get("id")
        check_id(checker, f"{where}[{index}]", item_id)
        if isinstance(item_id, str):
            if item_id in seen:
                checker.error(f"{where}: повторяющийся id {item_id!r}")
            seen.add(item_id)
        result.append(row)
    return result


def validate_structure(checker: Checker, cfg: dict) -> None:
    print("===== КОНФИГУРАЦИЯ =====")
    check_unknown(checker, "корень", cfg, TOP_LEVEL)

    if cfg.get("schema") == 1:
        checker.ok("schema = 1")
    else:
        checker.error("поддерживается только schema = 1")

    dashboard = table(cfg, "dashboard")
    if dashboard is None:
        checker.error("dashboard: секция отсутствует")
    else:
        check_unknown(
            checker,
            "dashboard",
            dashboard,
            {"server_name", "timezone"},
        )

        need_string(
            checker,
            "dashboard",
            dashboard,
            "server_name",
        )
        timezone = need_string(checker, "dashboard", dashboard, "timezone")
        if timezone:
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError:
                checker.error(f"dashboard.timezone: неизвестная зона {timezone!r}")

    modules = table(cfg, "modules")
    if modules is None:
        checker.error("modules: секция отсутствует")
    else:
        check_unknown(checker, "modules", modules, MODULE_IDS)
        enabled = 0
        for module_id in sorted(MODULE_IDS):
            if need_bool(checker, "modules", modules, module_id) is True:
                enabled += 1
        if enabled == 0:
            checker.error("modules: должен быть включён хотя бы один модуль")

    system = table(cfg, "system")
    if system is None:
        checker.error("system: секция отсутствует")
    else:
        check_unknown(checker, "system", system, SYSTEM_COMPONENTS)
        for component in sorted(SYSTEM_COMPONENTS):
            need_bool(checker, "system", system, component)

    extensions = table(cfg, "extensions")
    if extensions is None:
        checker.error("extensions: секция отсутствует")
    else:
        check_unknown(checker, "extensions", extensions, {"root", "enabled"})
        root = need_string(checker, "extensions", extensions, "root")
        if root and not Path(root).is_absolute():
            checker.error("extensions.root должен быть абсолютным")
        enabled = extensions.get("enabled")
        if not isinstance(enabled, list):
            checker.error("extensions.enabled: ожидается массив")
        else:
            seen: set[str] = set()
            for item in enabled:
                if not isinstance(item, str) or ID_RE.fullmatch(item) is None:
                    checker.error(f"extensions.enabled: некорректный id {item!r}")
                    continue
                if item in MODULE_IDS:
                    checker.error(
                        f"extensions.enabled: id {item!r} зарезервирован встроенным модулем"
                    )
                if item in seen:
                    checker.error(f"extensions.enabled: повторяется {item!r}")
                seen.add(item)

    if module_enabled(cfg, "overview"):
        host = table(cfg, "host")
        if host is None:
            checker.error("host: секция обязательна для overview")
        else:
            check_unknown(checker, "host", host, {"cpu_temperature_type", "live_refresh_seconds"})
            need_string(checker, "host", host, "cpu_temperature_type")
            refresh = host.get("live_refresh_seconds")
            if not isinstance(refresh, int) or isinstance(refresh, bool) or not 2 <= refresh <= 60:
                checker.error("host.live_refresh_seconds должен быть целым от 2 до 60")

    if module_enabled(cfg, "system") and component_enabled(cfg, "storage"):
        rows = check_unique_rows(checker, "storage", cfg.get("storage"))
        allowed = {"id", "name", "path", "warn_percent", "error_percent"}
        for index, row in enumerate(rows, 1):
            where = f"storage[{index}]"
            check_unknown(checker, where, row, allowed)
            need_string(checker, where, row, "name")
            path = need_string(checker, where, row, "path")
            if path and not Path(path).is_absolute():
                checker.error(f"{where}.path должен быть абсолютным")
            warn = row.get("warn_percent")
            error = row.get("error_percent")
            if not isinstance(warn, int) or isinstance(warn, bool) or not 1 <= warn <= 99:
                checker.error(f"{where}.warn_percent должен быть 1..99")
            if not isinstance(error, int) or isinstance(error, bool) or not 2 <= error <= 100:
                checker.error(f"{where}.error_percent должен быть 2..100")
            if isinstance(warn, int) and isinstance(error, int) and warn >= error:
                checker.error(f"{where}: warn_percent должен быть меньше error_percent")

    if module_enabled(cfg, "services"):
        rows = check_unique_rows(checker, "services", cfg.get("services"))
        allowed = {"id", "name", "unit", "mode", "restart"}
        units: set[str] = set()
        for index, row in enumerate(rows, 1):
            where = f"services[{index}]"
            check_unknown(checker, where, row, allowed)
            need_string(checker, where, row, "name")
            unit = need_string(checker, where, row, "unit")
            mode = need_string(checker, where, row, "mode")
            need_bool(checker, where, row, "restart")
            if unit:
                if not unit.endswith(".service"):
                    checker.error(f"{where}.unit должен оканчиваться на .service")
                if unit in units:
                    checker.error(f"services: unit {unit!r} повторяется")
                units.add(unit)
            if mode not in {"daemon", "oneshot"}:
                checker.error(f"{where}.mode: допустимы daemon/oneshot")

    if module_enabled(cfg, "docker"):
        docker = table(cfg, "docker")
        if docker is None:
            checker.error("docker: секция обязательна")
        else:
            check_unknown(checker, "docker", docker, {"restart_allow", "names"})
            allow = docker.get("restart_allow")
            if not isinstance(allow, list) or not all(isinstance(x, str) and x for x in allow):
                checker.error("docker.restart_allow: ожидается массив строк")
            names = docker.get("names")
            if not isinstance(names, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in names.items()):
                checker.error("docker.names: ожидается таблица строк")

    if module_enabled(cfg, "fail2ban"):
        f2b = table(cfg, "fail2ban")
        if f2b is None:
            checker.error("fail2ban: секция обязательна")
        else:
            check_unknown(checker, "fail2ban", f2b, {"unban_allow", "names"})
            allow = f2b.get("unban_allow")
            if not isinstance(allow, list) or not all(isinstance(x, str) and x for x in allow):
                checker.error("fail2ban.unban_allow: ожидается массив строк")
            names = f2b.get("names")
            if not isinstance(names, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in names.items()):
                checker.error("fail2ban.names: ожидается таблица строк")

    if module_enabled(cfg, "system") and component_enabled(cfg, "smart"):
        smart = table(cfg, "smart")
        rows = smart.get("disks") if smart else None
        rows = check_unique_rows(checker, "smart.disks", rows)
        allowed = {"id", "name", "path", "type"}
        for index, row in enumerate(rows, 1):
            where = f"smart.disks[{index}]"
            check_unknown(checker, where, row, allowed)
            need_string(checker, where, row, "name")
            path = need_string(checker, where, row, "path")
            dtype = need_string(checker, where, row, "type")
            if path and not Path(path).is_absolute():
                checker.error(f"{where}.path должен быть абсолютным")
            if dtype not in {"ata", "nvme"}:
                checker.error(f"{where}.type: допустимы ata/nvme")

    if module_enabled(cfg, "system") and component_enabled(cfg, "schedule"):
        rows = check_unique_rows(checker, "schedule", cfg.get("schedule"))
        allowed = {"id", "name", "timer"}
        timers: set[str] = set()
        for index, row in enumerate(rows, 1):
            where = f"schedule[{index}]"
            check_unknown(checker, where, row, allowed)
            need_string(checker, where, row, "name")
            timer = need_string(checker, where, row, "timer")
            if timer:
                if not timer.endswith(".timer"):
                    checker.error(f"{where}.timer должен оканчиваться на .timer")
                if timer in timers:
                    checker.error(f"schedule: timer {timer!r} повторяется")
                timers.add(timer)

    if module_enabled(cfg, "docs"):
        docs = table(cfg, "docs")
        if docs is None:
            checker.error("docs: секция обязательна")
        else:
            check_unknown(checker, "docs", docs, {"path", "recursive", "extension"})
            path = need_string(checker, "docs", docs, "path")
            need_bool(checker, "docs", docs, "recursive")
            extension = need_string(checker, "docs", docs, "extension")
            if path and not Path(path).is_absolute():
                checker.error("docs.path должен быть абсолютным")
            if extension and not extension.startswith("."):
                checker.error("docs.extension должен начинаться с точки")

    if checker.errors == 0:
        checker.ok("структура config.toml корректна")


def run(args: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def command(name: str) -> str | None:
    return shutil.which(name, path="/usr/sbin:/usr/bin:/sbin:/bin")


def load_state(unit: str) -> str | None:
    systemctl = command("systemctl")
    if not systemctl:
        return None
    rc, out, _ = run([systemctl, "show", unit, "-p", "LoadState", "--value", "--no-pager"])
    return out if rc == 0 or out else None


def validate_host(checker: Checker, cfg: dict) -> None:
    print()
    print("===== ПРОВЕРКА ХОСТА =====")

    if module_enabled(cfg, "overview"):
        expected = (table(cfg, "host") or {}).get("cpu_temperature_type")
        found = []
        if isinstance(expected, str):
            for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
                try:
                    if (zone / "type").read_text().strip() == expected:
                        found.append(zone.name)
                except OSError:
                    pass
        if found:
            checker.ok(f"CPU temperature: найдено зон {len(found)}")
        else:
            checker.warn(f"CPU temperature: thermal zone {expected!r} не найдена")

    if module_enabled(cfg, "system") and component_enabled(cfg, "storage"):
        for row in cfg.get("storage", []):
            if not isinstance(row, dict):
                continue
            path = row.get("path")
            name = row.get("name", path)
            if isinstance(path, str) and Path(path).exists():
                checker.ok(f"хранилище {name}: путь доступен")
            elif isinstance(path, str):
                checker.warn(f"хранилище {name}: {path} отсутствует")

    if module_enabled(cfg, "services"):
        found = 0
        for row in cfg.get("services", []):
            if not isinstance(row, dict) or not isinstance(row.get("unit"), str):
                continue
            state = load_state(row["unit"])
            if state == "loaded":
                found += 1
            else:
                checker.warn(f"служба {row.get('name', row['unit'])}: LoadState={state!r}")
        checker.ok(f"systemd: найдено {found} настроенных служб")

    if module_enabled(cfg, "docker"):
        docker = command("docker")
        if not docker:
            checker.warn("Docker CLI не найден")
        else:
            rc, out, err = run([docker, "ps", "-a", "--format", "{{.Names}}"], 12)
            if rc == 0:
                checker.ok(f"Docker: обнаружено контейнеров: {len([x for x in out.splitlines() if x])}")
            else:
                checker.warn(f"Docker: {err or 'не удалось получить список'}")

    if module_enabled(cfg, "fail2ban"):
        client = command("fail2ban-client")
        if not client:
            checker.warn("fail2ban-client не найден")
        else:
            rc, out, err = run([client, "status"], 10)
            if rc == 0:
                checker.ok("Fail2Ban: status доступен")
            else:
                checker.warn(f"Fail2Ban: {err or 'status недоступен'}")

    if module_enabled(cfg, "system") and component_enabled(cfg, "smart"):
        found = 0
        for row in (table(cfg, "smart") or {}).get("disks", []):
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                continue
            if Path(row["path"]).exists():
                found += 1
            else:
                checker.warn(f"SMART: {row.get('name', row['path'])}: устройство отсутствует")
        checker.ok(f"SMART: найдено настроенных дисков: {found}")

    if module_enabled(cfg, "system") and component_enabled(cfg, "schedule"):
        found = 0
        for row in cfg.get("schedule", []):
            if not isinstance(row, dict) or not isinstance(row.get("timer"), str):
                continue
            state = load_state(row["timer"])
            if state == "loaded":
                found += 1
            else:
                checker.warn(f"timer {row.get('name', row['timer'])}: LoadState={state!r}")
        checker.ok(f"systemd: найдено {found} настроенных timers")

    if module_enabled(cfg, "docs"):
        docs = table(cfg, "docs") or {}
        path = docs.get("path")
        if isinstance(path, str) and Path(path).is_dir():
            checker.ok(f"документация: каталог {path} доступен")
        else:
            checker.warn(f"документация: каталог {path!r} недоступен")

    # Проверяем не только manifest, но и реальную сборку module registry.
    try:
        daemon_root = Path(__file__).resolve().parents[1] / "daemon"
        if str(daemon_root) not in sys.path:
            sys.path.insert(0, str(daemon_root))
        from server_dashboard.module_registry import build_registry

        registry = build_registry(cfg)
        if registry.extension_errors:
            for item in registry.extension_errors:
                checker.warn(
                    f"extension {item.get('id', '?')}: "
                    f"{item.get('message', 'ошибка загрузки')}"
                )
        else:
            checker.ok("module registry: расширения загружены")
    except Exception as exc:
        checker.warn(f"module registry: {exc}")

    extensions = table(cfg, "extensions") or {}
    root = extensions.get("root")
    enabled = extensions.get("enabled", [])
    if isinstance(root, str) and isinstance(enabled, list):
        for extension_id in enabled:
            if not isinstance(extension_id, str):
                continue
            ext = Path(root) / extension_id
            manifest = ext / "manifest.toml"
            if not manifest.is_file():
                checker.warn(f"extension {extension_id}: manifest.toml не найден")
                continue
            try:
                with manifest.open("rb") as fh:
                    data = tomllib.load(fh)
                if data.get("api") != 1 or data.get("id") != extension_id:
                    checker.warn(f"extension {extension_id}: manifest несовместим")
                else:
                    checker.ok(f"extension {extension_id}: manifest корректен")
            except (OSError, tomllib.TOMLDecodeError) as exc:
                checker.warn(f"extension {extension_id}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка конфигурации Server Dashboard")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--no-host", action="store_true")
    args = parser.parse_args()

    checker = Checker()
    print("Server Dashboard — проверка конфигурации")
    print(f"Файл: {args.config}")
    print()

    try:
        with args.config.open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        checker.error(f"не удалось прочитать TOML: {exc}")
        return 1

    checker.ok("TOML разобран")
    validate_structure(checker, cfg)

    if not args.no_host and checker.errors == 0:
        validate_host(checker, cfg)

    print()
    print("===== ИТОГ =====")
    print(f"Ошибок: {checker.errors}")
    print(f"Предупреждений: {checker.warnings}")

    if checker.errors:
        print("Конфигурация НЕ принята.")
        return 1

    print("Конфигурация корректна.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
