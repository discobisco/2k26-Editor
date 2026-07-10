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
    def test_worker_owns_progress_and_done_events(self) -> None:
        worker = BackgroundOperationWorker()

        def task() -> str:
            worker.report_progress(1, 2, "half")
            return "complete"

        self.assertTrue(worker.start("Example", task))
        events = wait_for_events(worker, 2)

        self.assertEqual(("progress", (1, 2, "half")), events[0])
        self.assertEqual(("done", ("complete", "complete", None)), events[1])

    def test_worker_rejects_concurrent_operation(self) -> None:
        worker = BackgroundOperationWorker()
        release = threading.Event()

        def task() -> str:
            release.wait(timeout=1.0)
            return "done"

        self.assertTrue(worker.start("First", task))
        self.assertFalse(worker.start("Second", lambda: "nope"))
        release.set()
        events = wait_for_events(worker, 1)

        self.assertEqual(("done", ("done", "complete", None)), events[-1])

    def test_worker_stays_busy_until_done_event_is_consumed(self) -> None:
        worker = BackgroundOperationWorker()

        self.assertTrue(worker.start("Instant", lambda: "done"))
        time.sleep(0.05)

        self.assertTrue(worker.is_running())
        self.assertFalse(worker.start("Duplicate", lambda: "nope"))
        self.assertEqual(("done", ("done", "complete", None)), worker.pop_events()[-1])
        self.assertFalse(worker.is_running())

    def test_worker_cancellation_uses_worker_state_not_ui_state(self) -> None:
        worker = BackgroundOperationWorker()

        def task() -> str:
            worker.request_cancel()
            worker.report_progress(1, 1, "cancel point")
            return "not reached"

        self.assertTrue(worker.start("Cancel Test", task))
        events = wait_for_events(worker, 1)

        self.assertEqual(("done", ("Cancel Test cancelled.", "cancelled", None)), events[-1])


if __name__ == "__main__":
    unittest.main()
