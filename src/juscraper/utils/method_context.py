"""Context for preserving the public method name through scraper wrappers."""
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import ParamSpec, TypeVar

_PUBLIC_METHOD_ERROR_NAME: ContextVar[str | None] = ContextVar("public_method_error_name", default=None)
_P = ParamSpec("_P")
_R = TypeVar("_R")


def current_public_method_error_name() -> str | None:
    """Return the current public method label, if a wrapper set one."""
    return _PUBLIC_METHOD_ERROR_NAME.get()


def preserve_public_method_error_name(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Keep a public endpoint name while it delegates to a download method."""

    @wraps(method)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        token = _PUBLIC_METHOD_ERROR_NAME.set(f"{type(args[0]).__name__}.{method.__name__}()")
        try:
            return method(*args, **kwargs)
        finally:
            _PUBLIC_METHOD_ERROR_NAME.reset(token)

    return wrapped
