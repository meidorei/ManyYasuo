"""Global mutual exclusion for compression, extraction and renaming."""

from __future__ import annotations

import threading
from collections.abc import Callable


class JobCoordinator:
    def __init__(self):
        self._lock = threading.RLock()
        self._owner: str | None = None
        self._listeners: list[Callable[[str | None], None]] = []

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def subscribe(self, listener: Callable[[str | None], None]) -> None:
        self._listeners.append(listener)

    def try_acquire(self, owner: str) -> bool:
        with self._lock:
            if self._owner is not None:
                return False
            self._owner = owner
        self._notify()
        return True

    def release(self, owner: str) -> bool:
        with self._lock:
            if self._owner != owner:
                return False
            self._owner = None
        self._notify()
        return True

    def _notify(self) -> None:
        owner = self.owner
        for listener in tuple(self._listeners):
            listener(owner)
