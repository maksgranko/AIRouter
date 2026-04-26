from typing import Any, Optional, Tuple

import httpx
from fastapi import HTTPException

from .key_cycle_utils import rotate_key_and_detect_full_cycle


def with_reason(base_message: str, reason: str) -> str:
    return f"{base_message} ({reason})"


def raise_http_with_reason(
    status_code: int,
    base_message: str,
    reason: str,
    logger: Any = None,
    log_level: str = "error",
) -> None:
    detail = with_reason(base_message, reason)
    if logger is not None:
        log_method = getattr(logger, log_level, None)
        if callable(log_method):
            log_method(detail)
    raise HTTPException(status_code=status_code, detail=detail)


def try_rotate_proxy(proxy_manager: Any) -> bool:
    return bool(getattr(proxy_manager, "active", False) and proxy_manager.rotate_proxy())


def map_httpx_exception_to_status(exc: Exception, proxy_hint: bool = False) -> int:
    if isinstance(exc, httpx.TimeoutException):
        return 504
    if isinstance(exc, (httpx.NetworkError, httpx.ConnectError, httpx.ProxyError)):
        return 502
    if proxy_hint:
        return 503
    return 500


def map_openai_exception_to_status(exc: Exception, openai_module: Any) -> int:
    if isinstance(exc, openai_module.error.RateLimitError):
        return 429
    if isinstance(exc, openai_module.error.APIConnectionError):
        return 502
    if isinstance(exc, openai_module.error.Timeout):
        return 504
    if isinstance(exc, openai_module.error.ServiceUnavailableError):
        return 503
    return 500


def advance_proxy_or_key(
    proxy_manager: Any,
    api_key_manager: Any,
    service_name: str,
    first_key_in_overall_cycle: Optional[str],
    previous_key: Optional[str],
) -> Tuple[str, bool]:
    if try_rotate_proxy(proxy_manager):
        return "proxy_rotated", False
    rotated, full_cycle_completed = rotate_key_and_detect_full_cycle(
        api_key_manager,
        service_name,
        first_key_in_overall_cycle,
        previous_key,
    )
    if not rotated:
        return "key_exhausted", False
    return "key_rotated", full_cycle_completed
