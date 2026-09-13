from __future__ import annotations

import grp
import json
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, ConfigError, load_config
from .module_api import DashboardOperationError
from .module_registry import build_registry
from .protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    ProtocolError,
    error_response,
    success_response,
    validate_request,
)


SOCKET_PATH = Path("/run/server-dashboard/dashboard.sock")
SOCKET_GROUP = "server-dashboard"
SOCKET_MODE = 0o660
ACCEPT_TIMEOUT = 1.0
CLIENT_TIMEOUT = 8.0


class DashboardDaemon:
    def __init__(self) -> None:
        self.running = True
        self.listener: socket.socket | None = None

    def stop(self, signum: int, frame: object) -> None:
        self.running = False
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass

    def prepare_socket(self) -> socket.socket:
        SOCKET_PATH.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        if SOCKET_PATH.exists() or SOCKET_PATH.is_socket():
            SOCKET_PATH.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(SOCKET_PATH))
        try:
            gid = grp.getgrnam(SOCKET_GROUP).gr_gid
        except KeyError as exc:
            listener.close()
            raise RuntimeError(f"Группа {SOCKET_GROUP!r} не существует") from exc
        os.chown(SOCKET_PATH, 0, gid)
        os.chmod(SOCKET_PATH, SOCKET_MODE)
        listener.listen(16)
        listener.settimeout(ACCEPT_TIMEOUT)
        return listener

    @staticmethod
    def receive_request(client: socket.socket) -> bytes:
        buffer = bytearray()
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > MAX_REQUEST_BYTES:
                raise ProtocolError("request_too_large", "Запрос слишком большой")
            if b"\n" in buffer:
                break
        if not buffer:
            raise ProtocolError("empty_request", "Получен пустой запрос")
        line, _, _ = bytes(buffer).partition(b"\n")
        return line

    @staticmethod
    def send_response(
        client: socket.socket,
        response: dict[str, Any],
        request_id: str | None,
    ) -> None:
        try:
            payload = (
                json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            response = error_response(
                request_id,
                "invalid_response",
                "Операция вернула некорректный ответ",
            )
            payload = (
                json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")

        if len(payload) > MAX_RESPONSE_BYTES:
            response = error_response(
                request_id,
                "response_too_large",
                "Ответ операции превышает допустимый размер",
            )
            payload = (
                json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")

        client.sendall(payload)

    def handle_client(self, client: socket.socket) -> None:
        request_id: str | None = None
        try:
            raw = self.receive_request(client)
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProtocolError("invalid_encoding", "Запрос должен быть UTF-8") from exc
            try:
                request = json.loads(decoded)
            except json.JSONDecodeError as exc:
                raise ProtocolError("invalid_json", "Некорректный JSON") from exc

            request_id, operation, params = validate_request(request)
            config = load_config(DEFAULT_CONFIG)
            registry = build_registry(config)
            data = registry.dispatch(operation, params)
            response = success_response(request_id, data)

        except DashboardOperationError as exc:
            response = error_response(request_id, exc.code, exc.message)
        except ConfigError as exc:
            response = error_response(request_id, "configuration_error", str(exc))
        except ProtocolError as exc:
            response = error_response(exc.request_id or request_id, exc.code, exc.message)
        except Exception as exc:
            response = error_response(request_id, "operation_failed", str(exc))

        self.send_response(client, response, request_id)

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.listener = self.prepare_socket()
        try:
            while self.running:
                try:
                    client, _ = self.listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        raise
                    break
                with client:
                    client.settimeout(CLIENT_TIMEOUT)
                    try:
                        self.handle_client(client)
                    except (ConnectionError, TimeoutError, socket.timeout):
                        continue
        finally:
            if self.listener is not None:
                try:
                    self.listener.close()
                except OSError:
                    pass
            try:
                SOCKET_PATH.unlink()
            except FileNotFoundError:
                pass
        return 0


def main() -> int:
    daemon = DashboardDaemon()
    try:
        return daemon.run()
    except Exception as exc:
        print(f"server-dashboard-daemon: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
