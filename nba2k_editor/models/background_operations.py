from __future__ import annotations

import queue
import threading
from typing import Any, Callable


DoneCallback = Callable[[object], None]
WorkerEvent = tuple[str, Any]


class OperationCancelled(Exception):
    """Raised by background tasks when the user requested cancellation."""


class BackgroundOperationWorker:
    """Single serialized worker for cancellable editor model/game operations."""

    def __init__(self) -> None:
        self._events: queue.Queue[WorkerEvent] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._active = False
        self._cancel_requested = False
        self._next_request_id = 1
        self._active_request_id: int | None = None
        self._state_lock = threading.Lock()

    def is_running(self) -> bool:
        with self._state_lock:
            return self._active

    def active_request_id(self) -> int | None:
        with self._state_lock:
            return self._active_request_id

    def start(
        self,
        title: str,
        task: Callable[[], object],
        *,
        done_callback: DoneCallback | None = None,
    ) -> int | None:
        with self._state_lock:
            if self._active:
                return None
            request_id = self._next_request_id
            self._next_request_id += 1
            self._active = True
            self._active_request_id = request_id
            self._cancel_requested = False

        def run_task() -> None:
            try:
                result = task()
            except OperationCancelled:
                result = f"{title} cancelled."
                outcome = "cancelled"
            except Exception as exc:
                result = f"{title} failed: {exc}"
                outcome = "failed"
            else:
                outcome = "complete"
            self._events.put(("done", (request_id, result, outcome, done_callback)))

        self._thread = threading.Thread(
            target=run_task,
            name=f"nba2k-editor-{title.lower().replace(' ', '-')}",
            daemon=True,
        )
        self._thread.start()
        return request_id

    def request_cancel(self) -> None:
        with self._state_lock:
            if self._active:
                self._cancel_requested = True

    def raise_if_cancelled(self) -> None:
        with self._state_lock:
            cancelled = self._cancel_requested
        if cancelled:
            raise OperationCancelled("operation cancelled")

    def report_progress(self, current: int, total: int, message: str) -> None:
        self.raise_if_cancelled()
        request_id = self.active_request_id()
        if request_id is None:
            raise RuntimeError("cannot report progress without an active request")
        self._events.put(("progress", (request_id, current, total, message)))

    def pop_events(self) -> list[WorkerEvent]:
        events: list[WorkerEvent] = []
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return events
            events.append(event)
            if event[0] == "done":
                request_id = int(event[1][0])
                with self._state_lock:
                    if request_id == self._active_request_id:
                        self._active = False
                        self._active_request_id = None
