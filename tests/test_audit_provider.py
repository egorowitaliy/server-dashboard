from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server_dashboard.audit_provider import collect_audit


class AuditProviderTests(unittest.TestCase):
    def test_naive_timestamp_is_ignored_without_breaking_sort(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "audit.log"
            path.write_text(
                "2026-09-13T14:00:00+03:00 user=evs ip=127.0.0.1 action=auth.login result=ok\n"
                "2026-09-13T11:01:00 user=legacy ip=127.0.0.2 action=auth.login result=ok\n",
                encoding="utf-8",
            )
            with patch("server_dashboard.audit_provider.AUDIT_PATH", path):
                data = collect_audit({})
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["entries"][0]["user"], "evs")


if __name__ == "__main__":
    unittest.main()
