# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
from fastapi import HTTPException, status


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def unauthorized(code: str = "unauthorized", message: str = "Authentication required") -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, code, message)


def forbidden(message: str = "You do not have permission for this action") -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "forbidden", message)


def not_found(message: str = "Not found") -> ApiError:
    # Used for cross-tenant access too, so the response does not reveal that the resource exists.
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message)


def too_many(message: str = "Too many attempts. Try again later.") -> ApiError:
    return ApiError(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", message)
