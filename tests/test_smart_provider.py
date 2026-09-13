from __future__ import annotations

import unittest

from server_dashboard.smart_provider import _health


class SmartProviderTests(unittest.TestCase):
    def test_execution_bits_zero_to_two_are_errors(self) -> None:
        data = {"smart_status": {"passed": True}}
        for status in (1, 2, 4, 3, 5, 6, 7):
            with self.subTest(exit_status=status):
                self.assertEqual(_health(data, status), ("error", "unavailable"))

    def test_smart_health_bits_remain_warning(self) -> None:
        data = {"smart_status": {"passed": True}}
        self.assertEqual(_health(data, 8), ("warn", "warning"))

    def test_clean_health_is_ok(self) -> None:
        self.assertEqual(_health({"smart_status": {"passed": True}}, 0), ("ok", "healthy"))


if __name__ == "__main__":
    unittest.main()
