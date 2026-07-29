from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, public_message: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.public_message = public_message or message


def bad_request(message: str) -> AppError:
    return AppError(message=message, status_code=400, public_message=message)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.public_message,
            "message": str(exc),
        },
    )


async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Unexpected server failure",
        },
    )
