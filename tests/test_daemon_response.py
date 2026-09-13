from __future__ import annotations

import json
import socket
import unittest

from server_dashboard.daemon import DashboardDaemon


class DaemonResponseTests(unittest.TestCase):
    def receive(self, response, request_id="r1"):
        left, right = socket.socketpair()
        try:
            DashboardDaemon.send_response(left, response, request_id)
            raw = right.recv(4 * 1024 * 1024)
        finally:
            left.close()
            right.close()
        return json.loads(raw.decode("utf-8"))

    def test_nonserializable_response_becomes_typed_error(self) -> None:
        data = self.receive({"version": 1, "id": "r1", "ok": True, "data": {1, 2}})
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "invalid_response")

    def test_oversized_response_becomes_typed_error(self) -> None:
        data = self.receive({"version": 1, "id": "r1", "ok": True, "data": "x" * (3 * 1024 * 1024)})
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "response_too_large")


if __name__ == "__main__":
    unittest.main()
