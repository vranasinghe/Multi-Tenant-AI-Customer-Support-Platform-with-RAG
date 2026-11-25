"""RFC 9457 Problem Details responses (docs/API_SPEC.md §1.4)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_TYPE_BASE = "https://docs.example.com/errors/"

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


class ApiError(Exception):
    """A domain error rendered as an RFC 9457 problem (status + stable machine-readable code)."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        *,
        detail: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"{code}: {title}")
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors
        self.headers = headers


def unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "Authentication required")


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Not Found")


def forbidden(detail: str | None = None, code: str = "forbidden") -> ApiError:
    return ApiError(403, code, "Forbidden", detail=detail)


def invalid_token() -> ApiError:
    return ApiError(400, "invalid_token", "This link is invalid or has expired")


def validation_error(field: str, message: str, code: str = "invalid") -> ApiError:
    return ApiError(
        422,
        "validation_error",
        "Request validation failed",
        errors=[{"field": field, "code": code, "message": message}],
    )


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    request_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{ERROR_TYPE_BASE}{code}",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail is not None:
        body["detail"] = detail
    if request_id is not None:
        body["request_id"] = request_id
    if errors:
        body["errors"] = errors
    return JSONResponse(
        jsonable_encoder(body), status_code=status, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # narrowing for mypy  # noqa: S101
    status = exc.status_code
    title = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else "Error"
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != title else None
    return problem_response(
        status=status,
        code=_STATUS_CODES.get(status, "error"),
        title=title,
        detail=detail,
        request_id=_request_id(request),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
            "code": err.get("type", "invalid"),
            "message": err.get("msg", "Invalid value"),
        }
        for err in exc.errors()
    ]
    return problem_response(
        status=422,
        code="validation_error",
        title="Request validation failed",
        request_id=_request_id(request),
        errors=errors,
    )


async def _api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101
    return problem_response(
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        request_id=_request_id(request),
        errors=exc.errors,
        headers=exc.headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
