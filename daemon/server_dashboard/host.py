from __future__ import annotations

import time
from pathlib import Path
from typing import Any


PROC_STAT = Path("/proc/stat")
PROC_MEMINFO = Path("/proc/meminfo")
PROC_LOADAVG = Path("/proc/loadavg")
PROC_UPTIME = Path("/proc/uptime")
THERMAL_ROOT = Path("/sys/class/thermal")


class HostMetricError(RuntimeError):
    pass


def _read_cpu_counters() -> tuple[int, int]:
    try:
        first = PROC_STAT.read_text(encoding="ascii").splitlines()[0]
    except (OSError, IndexError) as exc:
        raise HostMetricError(f"Не удалось прочитать /proc/stat: {exc}") from exc

    parts = first.split()

    if not parts or parts[0] != "cpu":
        raise HostMetricError("В /proc/stat отсутствует общая строка CPU")

    try:
        values = [int(value) for value in parts[1:]]
    except ValueError as exc:
        raise HostMetricError("Некорректные CPU counters в /proc/stat") from exc

    if len(values) < 5:
        raise HostMetricError("Недостаточно CPU counters в /proc/stat")

    # user nice system idle iowait irq softirq steal
    # guest/guest_nice уже включены в user/nice и повторно не учитываются.
    counters = values[:8]
    total = sum(counters)
    idle = counters[3] + counters[4]

    return total, idle


def cpu_usage_percent(sample_seconds: float = 0.25) -> float:
    total_1, idle_1 = _read_cpu_counters()
    time.sleep(sample_seconds)
    total_2, idle_2 = _read_cpu_counters()

    total_delta = total_2 - total_1
    idle_delta = idle_2 - idle_1

    if total_delta <= 0:
        raise HostMetricError("CPU counters не изменились между измерениями")

    busy_delta = total_delta - idle_delta
    percent = busy_delta / total_delta * 100.0

    return round(max(0.0, min(100.0, percent)), 1)


def cpu_temperature_c(sensor_type: str) -> float | None:
    matches: list[float] = []

    for zone in sorted(THERMAL_ROOT.glob("thermal_zone*")):
        type_file = zone / "type"
        temp_file = zone / "temp"

        try:
            current_type = type_file.read_text(encoding="ascii").strip()
        except OSError:
            continue

        if current_type != sensor_type:
            continue

        try:
            raw = temp_file.read_text(encoding="ascii").strip()
            temperature = int(raw) / 1000.0
        except (OSError, ValueError):
            continue

        # Отбрасываем явно бессмысленные значения.
        if -20.0 <= temperature <= 150.0:
            matches.append(temperature)

    if not matches:
        return None

    return round(max(matches), 1)


def memory_metrics() -> dict[str, int | float]:
    values: dict[str, int] = {}

    try:
        lines = PROC_MEMINFO.read_text(encoding="ascii").splitlines()
    except OSError as exc:
        raise HostMetricError(
            f"Не удалось прочитать /proc/meminfo: {exc}"
        ) from exc

    for line in lines:
        if ":" not in line:
            continue

        key, raw = line.split(":", 1)
        fields = raw.strip().split()

        if not fields:
            continue

        try:
            value = int(fields[0])
        except ValueError:
            continue

        # meminfo отдаёт KiB.
        values[key] = value * 1024

    total = values.get("MemTotal")
    available = values.get("MemAvailable")

    if total is None or available is None or total <= 0:
        raise HostMetricError(
            "В /proc/meminfo нет MemTotal/MemAvailable"
        )

    used = max(0, total - available)
    percent = used / total * 100.0

    return {
        "used_bytes": used,
        "available_bytes": available,
        "total_bytes": total,
        "usage_percent": round(percent, 1),
    }


def load_average() -> dict[str, float]:
    try:
        fields = PROC_LOADAVG.read_text(encoding="ascii").split()
        one, five, fifteen = map(float, fields[:3])
    except (OSError, ValueError, IndexError) as exc:
        raise HostMetricError(
            f"Не удалось прочитать /proc/loadavg: {exc}"
        ) from exc

    return {
        "1m": round(one, 2),
        "5m": round(five, 2),
        "15m": round(fifteen, 2),
    }


def uptime_seconds() -> int:
    try:
        first = PROC_UPTIME.read_text(encoding="ascii").split()[0]
        value = float(first)
    except (OSError, ValueError, IndexError) as exc:
        raise HostMetricError(
            f"Не удалось прочитать /proc/uptime: {exc}"
        ) from exc

    return max(0, int(value))


def collect_live_host_metrics(
    config: dict[str, Any],
) -> dict[str, Any]:
    host_config = config.get("host", {})

    sensor_type = host_config.get(
        "cpu_temperature_type",
        "x86_pkg_temp",
    )

    return {
        "cpu": {
            "usage_percent": cpu_usage_percent(),
            "temperature_c": cpu_temperature_c(sensor_type),
        },
        "memory": memory_metrics(),
        "load": load_average(),
    }


def collect_host_metrics(
    config: dict[str, Any],
) -> dict[str, Any]:
    host_config = config.get("host", {})

    snapshot = collect_live_host_metrics(config)

    snapshot["uptime_seconds"] = uptime_seconds()

    refresh = host_config.get(
        "live_refresh_seconds",
        5,
    )

    snapshot["refresh_seconds"] = (
        refresh
        if isinstance(refresh, int)
        and not isinstance(refresh, bool)
        and 2 <= refresh <= 60
        else 5
    )

    return snapshot
