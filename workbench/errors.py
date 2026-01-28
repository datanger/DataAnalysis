from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    details: dict | None = None


class ErrorCodes:
    CONFIG_MISSING = "CONFIG_MISSING"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    DATA_NOT_READY = "DATA_NOT_READY"
    RISK_CHECK_FAIL = "RISK_CHECK_FAIL"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
