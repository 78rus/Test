"""Small synchronous event bus used by the GUI and the core services."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class CoreEvent:
    """An immutable event emitted by a core object."""

    name: str
    source_id: str | None
    payload: Mapping[str, Any]


EventHandler = Callable[[CoreEvent], None]


class EventBus:
    """Thread-safe pub/sub without a GUI dependency.

    Qt adapters can subscribe to this bus and forward events as signals. Handlers
    are called synchronously in the publishing thread and are isolated from each
    other: an exception in one subscriber does not prevent the others from
    receiving the event.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_name: str, handler: EventHandler) -> Callable[[], None]:
        """Register *handler* and return an unsubscribe callback."""

        if not event_name:
            raise ValueError("event_name must not be empty")
        with self._lock:
            self._handlers[event_name].append(handler)

        def unsubscribe() -> None:
            self.unsubscribe(event_name, handler)

        return unsubscribe

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_name, [])
            if handler in handlers:
                handlers.remove(handler)
            if not handlers:
                self._handlers.pop(event_name, None)

    def emit(self, event_name: str, source_id: str | None = None, **payload: Any) -> CoreEvent:
        event = CoreEvent(event_name, source_id, dict(payload))
        with self._lock:
            handlers = tuple(self._handlers.get(event_name, ()))
            wildcard_handlers = tuple(self._handlers.get("*", ()))

        for handler in (*handlers, *wildcard_handlers):
            try:
                handler(event)
            except Exception:
                # A UI listener must not be able to break a connection lifecycle.
                # The application logger can wrap handlers when it needs details.
                continue
        return event
