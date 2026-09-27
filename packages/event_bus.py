"""Small deterministic in-process event bus.

The bus is synchronous and ordered. Non-critical observer failures are recorded without
bringing down the runtime; critical handler failures are surfaced to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from .events import RuntimeEvent


@dataclass(frozen=True)
class HandlerFailure:
    event_type: str
    handler_name: str
    error_type: str
    message: str


@dataclass(frozen=True)
class Subscription:
    event_type: type[RuntimeEvent] | None
    handler: Callable[[RuntimeEvent], None]
    critical: bool


class EventBus:
    def __init__(self, *, history_limit: int = 500) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        self._history_limit = history_limit
        self._history: list[RuntimeEvent] = []
        self._failures: list[HandlerFailure] = []
        self._subscriptions: list[Subscription] = []
        self._lock = RLock()

    def subscribe(
        self,
        event_type: type[RuntimeEvent] | None,
        handler: Callable[[RuntimeEvent], None],
        *,
        critical: bool = False,
    ) -> Subscription:
        subscription = Subscription(event_type, handler, critical)
        with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    def publish(self, event: RuntimeEvent) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]
            subscriptions = tuple(self._subscriptions)

        for sub in subscriptions:
            if sub.event_type is not None and not isinstance(event, sub.event_type):
                continue
            try:
                sub.handler(event)
            except Exception as exc:
                failure = HandlerFailure(
                    type(event).__name__,
                    getattr(sub.handler, "__name__", repr(sub.handler)),
                    type(exc).__name__,
                    str(exc),
                )
                with self._lock:
                    self._failures.append(failure)
                    if len(self._failures) > self._history_limit:
                        del self._failures[: len(self._failures) - self._history_limit]
                if sub.critical:
                    raise

    def history(self) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._history)

    def failures(self) -> tuple[HandlerFailure, ...]:
        with self._lock:
            return tuple(self._failures)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._failures.clear()


__all__ = ["EventBus", "HandlerFailure", "Subscription"]
