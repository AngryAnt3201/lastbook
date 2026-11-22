"""Deterministic progress-aware model startup timeout tests (no model process)."""
import threading
import unittest
from unittest.mock import patch

import llm_local


class FakeProcess:
    def poll(self):
        return None


class StartupTimeoutTests(unittest.TestCase):
    def make_local(self):
        local = llm_local.Local.__new__(llm_local.Local)
        local.lock = threading.RLock()
        local.state = "loading"
        local.pct = 0
        local.message = ""
        local.path = "fake-model"
        local.fit = {"fits": True}
        local.proc = FakeProcess()
        local.last_used = 0
        local.enabled = lambda: True
        local.stop = lambda why="": setattr(local, "state", "stopped")
        return local

    def run_clock(self, local, tick, max_ticks=200):
        clock = [0.0]
        steps = [0]
        def monotonic():
            return clock[0]
        def sleep(seconds):
            steps[0] += 1
            if steps[0] > max_ticks:
                raise AssertionError("startup wait did not terminate")
            clock[0] += tick
            return steps[0]
        return clock, steps, monotonic, sleep

    def test_stalled_load_times_out(self):
        local = self.make_local()
        _, _, monotonic, sleep = self.run_clock(local, 100)
        with patch.object(llm_local.time, "monotonic", side_effect=monotonic), \
             patch.object(llm_local.time, "sleep", side_effect=sleep):
            self.assertIn("too long", local.ensure_running())
        self.assertEqual(local.state, "stopped")

    def test_advancing_load_survives_original_ten_minute_limit(self):
        local = self.make_local()
        clock, steps, monotonic, original_sleep = self.run_clock(local, 200)
        def sleep(seconds):
            original_sleep(seconds)
            local.pct += 1
            if steps[0] == 5:  # 1000 seconds, longer than the original 600
                local.state = "ready"
        with patch.object(llm_local.time, "monotonic", side_effect=monotonic), \
             patch.object(llm_local.time, "sleep", side_effect=sleep):
            self.assertIsNone(local.ensure_running())
        self.assertGreater(clock[0], 600)

    def test_progress_cannot_extend_wait_forever(self):
        local = self.make_local()
        _, _, monotonic, original_sleep = self.run_clock(local, 200)
        def sleep(seconds):
            original_sleep(seconds)
            local.pct += 1
        with patch.object(llm_local.time, "monotonic", side_effect=monotonic), \
             patch.object(llm_local.time, "sleep", side_effect=sleep):
            self.assertIn("too long", local.ensure_running())
        self.assertEqual(local.state, "stopped")

    def test_progress_at_timeout_boundary_prevents_stale_stop(self):
        local = self.make_local()
        clock, steps, monotonic, original_sleep = self.run_clock(local, 600)
        def on_cancel_check():
            # This runs after the first expired check but before the stop lock.
            if clock[0] == 600 and local.pct == 0:
                local.pct = 10
            return False
        def sleep(seconds):
            original_sleep(seconds)
            if steps[0] == 2:
                local.state = "ready"
        with patch.object(llm_local.time, "monotonic", side_effect=monotonic), \
             patch.object(llm_local.time, "sleep", side_effect=sleep):
            self.assertIsNone(local.ensure_running(cancelled=on_cancel_check))
        self.assertEqual(local.state, "ready")

    def test_cancel_does_not_kill_load(self):
        local = self.make_local()
        self.assertEqual(local.ensure_running(cancelled=lambda: True), "stopped")
        self.assertEqual(local.state, "loading")


if __name__ == "__main__":
    unittest.main()
