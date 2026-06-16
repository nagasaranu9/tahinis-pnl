import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)


def _error_response(status_code: int, code: str, message: str, detail: list | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "errors": [{"code": code, "message": message, **({"detail": detail} if detail else {})}],
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error",
        error_code=exc.error_code,
        message=exc.message,
        path=request.url.path,
    )
    return _error_response(exc.status_code, exc.error_code, exc.message)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"code": "VALIDATION_ERROR", "field": ".".join(str(l) for l in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"data": None, "errors": errors},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path, exc_info=exc)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "An unexpected error occurred",
    )
