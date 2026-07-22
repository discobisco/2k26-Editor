from __future__ import annotations

import threading
import time
import unittest

from nba2k_editor.models.background_operations import BackgroundOperationWorker


def wait_for_events(worker: BackgroundOperationWorker, expected_count: int, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    events = []
    while time.monotonic() < deadline:
        events.extend(worker.pop_events())
        if len(events) >= expected_count:
            return events
        time.sleep(0.01)
    events.extend(worker.pop_events())
    return events


class BackgroundOperationWorkerTests(unittest.TestCase):
    def test_worker_owns_request_scoped_progress_and_typed_done_events(self) -> None:
        worker = BackgroundOperationWorker()
        result = {"rows": (1, 2, 3)}

        def task() -> object:
            worker.report_progress(1, 2, "half")
            return result

        request_id = worker.start("Example", task)
        self.assertEqual(1, request_id)
        events = wait_for_events(worker, 2)

        self.assertEqual(("progress", (request_id, 1, 2, "half")), events[0])
        self.assertEqual(("done", (request_id, result, "complete", None)), events[1])

    def test_worker_rejects_concurrent_operation(self) -> None:
        worker = BackgroundOperationWorker()
        release = threading.Event()

        def task() -> str:
            release.wait(timeout=1.0)
            return "done"

        request_id = worker.start("First", task)
        self.assertEqual(1, request_id)
        self.assertIsNone(worker.start("Second", lambda: "nope"))
        release.set()
        events = wait_for_events(worker, 1)

        self.assertEqual(("done", (request_id, "done", "complete", None)), events[-1])

    def test_worker_stays_busy_until_done_event_is_consumed(self) -> None:
        worker = BackgroundOperationWorker()

        request_id = worker.start("Instant", lambda: "done")
        time.sleep(0.05)

        self.assertTrue(worker.is_running())
        self.assertIsNone(worker.start("Duplicate", lambda: "nope"))
        self.assertEqual(("done", (request_id, "done", "complete", None)), worker.pop_events()[-1])
        self.assertFalse(worker.is_running())

    def test_worker_cancellation_uses_worker_state_not_ui_state(self) -> None:
        worker = BackgroundOperationWorker()

        def task() -> str:
            worker.request_cancel()
            worker.report_progress(1, 1, "cancel point")
            return "not reached"

        request_id = worker.start("Cancel Test", task)
        events = wait_for_events(worker, 1)

        self.assertEqual(("done", (request_id, "Cancel Test cancelled.", "cancelled", None)), events[-1])

    def test_worker_exceptions_keep_request_identity(self) -> None:
        worker = BackgroundOperationWorker()

        def task() -> object:
            raise ValueError("broken task")

        request_id = worker.start("Failure", task)
        events = wait_for_events(worker, 1)

        self.assertEqual(("done", (request_id, "Failure failed: broken task", "failed", None)), events[-1])

    def test_done_callback_is_returned_for_qt_thread_invocation(self) -> None:
        worker = BackgroundOperationWorker()
        called: list[object] = []

        def callback(result: object) -> None:
            called.append(result)

        request_id = worker.start("Callback", lambda: ("prepared",), done_callback=callback)
        event = wait_for_events(worker, 1)[-1]

        self.assertEqual([], called)
        self.assertEqual("done", event[0])
        self.assertEqual(request_id, event[1][0])
        self.assertIs(event[1][3], callback)
        event[1][3](event[1][1])
        self.assertEqual([("prepared",)], called)

    def test_request_ids_increase_after_completed_requests(self) -> None:
        worker = BackgroundOperationWorker()

        first = worker.start("First", lambda: "one")
        wait_for_events(worker, 1)
        second = worker.start("Second", lambda: "two")
        wait_for_events(worker, 1)

        self.assertEqual(1, first)
        self.assertEqual(2, second)


if __name__ == "__main__":
    unittest.main()
