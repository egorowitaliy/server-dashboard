from __future__ import annotations

import unittest
from zoneinfo import ZoneInfo

from server_dashboard.schedule_provider import _systemd_time_to_iso


class ScheduleProviderTests(unittest.TestCase):
    def test_source_timezone_is_converted_to_dashboard_timezone(self) -> None:
        value = _systemd_time_to_iso(
            "Sun 2026-09-13 12:00:00 UTC",
            ZoneInfo("UTC"),
            ZoneInfo("Europe/Moscow"),
        )
        self.assertEqual(value, "2026-09-13T15:00:00+03:00")

    def test_dst_source_timezone_conversion(self) -> None:
        value = _systemd_time_to_iso(
            "Wed 2026-07-01 12:00:00 CEST",
            ZoneInfo("Europe/Berlin"),
            ZoneInfo("UTC"),
        )
        self.assertEqual(value, "2026-07-01T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
