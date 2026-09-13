from __future__ import annotations

import re
from typing import Any


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class ProtocolError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id


def validate_request(data: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(data, dict):
        raise ProtocolError("invalid_request", "Запрос должен быть JSON-объектом")

    allowed = {"version", "id", "op", "params"}
    if set(data) - allowed:
        raise ProtocolError("invalid_request", "Запрос содержит неизвестные поля")

    if data.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported_version", "Неподдерживаемая версия протокола")

    request_id = data.get("id")
    if not isinstance(request_id, str) or REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ProtocolError("invalid_request_id", "Некорректный id запроса")

    operation = data.get("op")
    if not isinstance(operation, str) or OPERATION_RE.fullmatch(operation) is None:
        raise ProtocolError("invalid_operation", "Некорректная операция", request_id)

    params = data.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError("invalid_params", "params должен быть JSON-объектом", request_id)
    if len(params) > 32:
        raise ProtocolError("invalid_params", "Слишком много параметров", request_id)

    return request_id, operation, params


def success_response(request_id: str, data: Any) -> dict[str, Any]:
    return {"version": PROTOCOL_VERSION, "id": request_id, "ok": True, "data": data}


def error_response(
    request_id: str | None,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }
