"""Circuit breaker: N подряд ошибок → временное отключение провайдера (fail-open)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreaker:
    """Обёртка над вызовом провайдера: считает подряд ошибки, открывается на кулдаун.

    Поведение fail-open: пока цепь открыта (или вызов упал), возвращает ``fallback``,
    не роняя прогон. Число отказов доступно через ``failure_count`` для мониторинга.
    """

    def __init__(
        self, failure_threshold: int = 3, cooldown_seconds: float = 60.0
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._consecutive = 0
        self._open_until = 0.0
        self.failure_count = 0

    def is_open(self) -> bool:
        return monotonic() < self._open_until

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        fallback: T | None = None,
        **kwargs: Any,
    ) -> T | None:
        if self.is_open():
            return fallback
        try:
            result = func(*args, **kwargs)
        except Exception:
            self._consecutive += 1
            self.failure_count += 1
            if self._consecutive >= self._threshold:
                self._open_until = monotonic() + self._cooldown
                self._consecutive = 0
                logger.warning("circuit breaker открыт на %.0fс", self._cooldown)
            return fallback
        self._consecutive = 0
        return result
