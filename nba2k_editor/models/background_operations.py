from __future__ import annotations

import queue
import threading
from typing import Any, Callable


class OperationCancelled(Exception):
    """Raised by background tasks when the user requested cancellation."""


class BackgroundOperationWorker:
    """Model-side worker for cancellable long-running editor operations."""

    def __init__(self) -> None:
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._active = False
        self._cancel_requested = False

    def is_running(self) -> bool:
        return self._active

    def start(self, title: str, task: Callable[[], str], *, done_callback: Callable[[], None] | None = None) -> bool:
        if self._active:
            return False
        self._active = True
        self._cancel_requested = False

        def run_task() -> None:
            try:
                message = task()
            except OperationCancelled:
                self._events.put(("done", (f"{title} cancelled.", "cancelled", done_callback)))
            except Exception as exc:
                self._events.put(("done", (f"{title} failed: {exc}", "failed", done_callback)))
            else:
                self._events.put(("done", (message, "complete", done_callback)))

        self._thread = threading.Thread(
            target=run_task,
            name=f"nba2k-editor-{title.lower().replace(' ', '-')}",
            daemon=True,
        )
        self._thread.start()
        return True

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def raise_if_cancelled(self) -> None:
        if self._cancel_requested:
            raise OperationCancelled("operation cancelled")

    def report_progress(self, current: int, total: int, message: str) -> None:
        self.raise_if_cancelled()
        self._events.put(("progress", (current, total, message)))

    def pop_events(self) -> list[tuple[str, Any]]:
        events: list[tuple[str, Any]] = []
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return events
            events.append(event)
            if event[0] == "done":
                self._active = False
