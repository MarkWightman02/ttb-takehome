import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.models.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An expected, safe-to-display API error."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Framework/API messages are public; never put uploaded content in HTTPException.detail.
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    code = "not_found" if exc.status_code == 404 else "http_error"
    response = error_response(exc.status_code, code, message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Validation errors can contain submitted values; keep them out of responses and logs.
    return error_response(
        422, "validation_error", "The request contains invalid or missing values."
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the route template and exception type, never bodies, query values, or exception text.
    route = getattr(request.scope.get("route"), "path", "<unmatched>")
    logger.error(
        "Unhandled error method=%s route=%s type=%s", request.method, route, type(exc).__name__
    )
    return error_response(500, "internal_error", "An unexpected error occurred. Please try again.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
