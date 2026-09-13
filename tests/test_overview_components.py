from __future__ import annotations

import unittest
from unittest.mock import patch

from server_dashboard.overview_provider import collect_overview


class OverviewComponentTests(unittest.TestCase):
    def test_storage_disabled_does_not_poll(self) -> None:
        config = {
            "modules": {
                "overview": True,
                "services": False,
                "docker": False,
                "fail2ban": False,
                "system": True,
                "docs": False,
                "audit": False,
            },
            "system": {"storage": False, "smart": False, "schedule": False},
        }
        with patch(
            "server_dashboard.overview_provider.collect_host_metrics",
            return_value={"cpu": {}, "memory": {}, "load": {}, "uptime_seconds": 1, "refresh_seconds": 5},
        ), patch(
            "server_dashboard.overview_provider.collect_storage_metrics",
            side_effect=AssertionError("storage must not be polled"),
        ):
            data = collect_overview(config)
        self.assertEqual(data["storage"], [])


if __name__ == "__main__":
    unittest.main()
