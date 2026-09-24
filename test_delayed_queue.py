"""Regression tests for the fixed delayed queue (stdlib unittest only)."""

import random
import unittest

from delayed_queue import DelayedQueue


class DelayedQueueTest(unittest.TestCase):
    def _assert_invariant(self, q):
        heap = q._heap
        index = q._index
        self.assertEqual(len(heap), len(index))
        for pos, task in enumerate(heap):
            self.assertEqual(index[task.task_id], pos)
            if pos:
                parent = (pos - 1) >> 1
                self.assertLessEqual(
                    (heap[parent].deadline, heap[parent].seq),
                    (task.deadline, task.seq),
                )

    def test_basic_fire_on_deadline(self):
        q = DelayedQueue()
        fired = []
        q.schedule("a", 3, lambda _: fired.append("a"))
        q.advance(2)
        self.assertEqual(fired, [])
        self.assertEqual(q.advance(1), ["a"])  # fires exactly at deadline
        self.assertEqual(q.pending_count(), 0)
        self._assert_invariant(q)

    def test_cancel_before_due_never_runs(self):
        q = DelayedQueue()
        fired = []
        q.schedule("a", 5, lambda _: fired.append("a"))
        self.assertTrue(q.cancel("a"))
        self.assertFalse(q.cancel("a"))
        q.advance(100)
        self.assertEqual(fired, [])
        self.assertEqual(q.internal_size(), 0)

    def test_cancel_is_permanent_across_reschedules(self):
        q = DelayedQueue()
        fired = []
        cb = lambda _: fired.append("t")
        for _ in range(50):
            q.schedule("t", 10, cb)
            q.cancel("t")
        q.advance(1000)
        self.assertEqual(fired, [])
        self.assertEqual(q.pending_count(), 0)
        self.assertEqual(q.internal_size(), 0)

    def test_reschedule_after_cancel_is_a_fresh_task(self):
        q = DelayedQueue()
        fired = []
        q.schedule("t", 5, lambda _: fired.append("old"))
        q.cancel("t")
        q.schedule("t", 3, lambda _: fired.append("new"))
        q.advance(10)
        self.assertEqual(fired, ["new"])

    def test_reschedule_moves_deadline_with_single_entry(self):
        q = DelayedQueue()
        for i in range(100):
            q.schedule("m", 100 + i, lambda _: None)
        self.assertEqual(q.pending_count(), 1)
        self.assertEqual(q.internal_size(), 1)
        q.cancel("m")
        self.assertEqual(q.internal_size(), 0)
        self._assert_invariant(q)

    def test_same_deadline_fires_all_in_submission_order(self):
        q = DelayedQueue()
        fired = []
        for name in ("a", "b", "c", "d", "e"):
            q.schedule(name, 7, lambda _, n=name: fired.append(n))
        q.advance(7)
        self.assertEqual(fired, ["a", "b", "c", "d", "e"])
        self._assert_invariant(q)

    def test_reschedule_keeps_fifo_among_equal_new_deadlines(self):
        q = DelayedQueue()
        fired = []
        q.schedule("old", 1, lambda _, n="old": fired.append(n))
        q.schedule("keep", 5, lambda _, n="keep": fired.append(n))
        q.schedule("old", 5, lambda _, n="moved": fired.append(n))
        q.advance(5)
        self.assertEqual(fired, ["keep", "moved"])

    def test_deadline_order_is_monotonic(self):
        q = DelayedQueue()
        seen = []
        for deadline in (3, 1, 4, 1, 5, 9, 2, 6):
            q.schedule("t%d" % deadline, deadline,
                       lambda _, d=deadline: seen.append(d))
        q.advance(20)
        self.assertEqual(seen, sorted(seen))
        self._assert_invariant(q)

    def test_reschedule_to_earlier_is_ordered_correctly(self):
        q = DelayedQueue()
        fired = []
        q.schedule("a", 1, lambda _: fired.append("a"))
        q.schedule("b", 3, lambda _: fired.append("b"))
        q.schedule("c", 4, lambda _: fired.append("c"))
        q.schedule("c", 0, lambda _: fired.append("c"))
        q.schedule("b", 5, lambda _: fired.append("b"))
        q.advance(2)
        self.assertEqual(fired, ["c", "a"])
        q.advance(3)
        self.assertEqual(fired, ["c", "a", "b"])

    def test_periodic_self_reschedule(self):
        q = DelayedQueue()
        ticks = []

        def periodic(queue):
            ticks.append(queue.now)
            if queue.now < 25:
                queue.schedule("p", 5, periodic)

        q.schedule("p", 5, periodic)
        for _ in range(5):
            q.advance(5)
            self.assertEqual(q.pending_count(), 1 if q.now < 25 else 0)
        self.assertEqual(ticks, [5, 10, 15, 20, 25])
        self.assertEqual(q.internal_size(), 0)

    def test_self_reschedule_at_zero_delay_interleaves_fifo(self):
        q = DelayedQueue()
        fired = []
        q.schedule("peer1", 2, lambda _: fired.append("peer1"))

        def repeating(queue):
            fired.append("r@%d" % queue.now)
            if queue.now < 6:
                queue.schedule("r", 2, repeating)

        q.schedule("r", 2, repeating)
        q.schedule("peer2", 4, lambda _: fired.append("peer2"))
        q.schedule("peer3", 6, lambda _: fired.append("peer3"))
        for _ in range(5):
            q.advance(2)
        self.assertEqual(fired, [
            "peer1", "r@2", "peer2", "r@4", "peer3", "r@6",
        ])

    def test_callback_cancels_a_due_peer(self):
        q = DelayedQueue()
        fired = []

        def first(_):
            fired.append("first")
            q.cancel("second")

        q.schedule("first", 1, first)
        q.schedule("second", 1, lambda _: fired.append("second"))
        q.advance(1)
        self.assertEqual(fired, ["first"])
        self._assert_invariant(q)

    def test_cancel_unknown_id_is_noop(self):
        q = DelayedQueue()
        self.assertFalse(q.cancel("nope"))
        q.advance(5)

    def test_random_drive_matches_sorted_model(self):
        rng = random.Random(20260924)
        q = DelayedQueue()
        active = {}   # task_id -> deadline
        fired = []

        def make_cb(tid, deadline):
            def cb(_):
                fired.append((tid, deadline))
                # only the live schedule fires; remove the model entry lazily
                if active.get(tid) == deadline:
                    del active[tid]
            return cb

        for i in range(6000):
            roll = rng.random()
            if roll < 0.65 or not active:
                tid = "t%d" % rng.randrange(400)
                delay = rng.randrange(0, 20)
                deadline = q.now + delay
                active[tid] = deadline
                q.schedule(tid, delay, make_cb(tid, deadline))
            else:
                tid = rng.choice(list(active))
                active.pop(tid)
                self.assertTrue(q.cancel(tid))
            if rng.random() < 0.4:
                q.advance(rng.randrange(0, 8))
                # everything fired must be due and non-decreasing
                for _, deadline in fired:
                    self.assertLessEqual(deadline, q.now)
                deadlines = [d for _, d in fired]
                self.assertEqual(deadlines, sorted(deadlines))
            self._assert_invariant(q)

        q.advance(1000)
        # Model follow-up: any id still active at the end must have fired at the
        # deadline the model recorded last (tasks don't reschedule themselves
        # in this drive, so every active id fires exactly once more).
        fired_final = dict(fired)
        for tid, deadline in active.items():
            self.assertEqual(fired_final.get(tid), deadline)
        self.assertEqual(q.pending_count(), 0)

    def test_100k_schedule_cancel_leaves_zero_entries(self):
        q = DelayedQueue()
        for i in range(100000):
            tid = "task-%d" % i
            q.schedule(tid, 1000, lambda _: None)
            q.cancel(tid)
        self.assertEqual(q.pending_count(), 0)
        self.assertEqual(q.internal_size(), 0)
        self.assertEqual(len(q._index), 0)
        q.advance(1000)

    def test_100k_churn_with_live_set_stays_bounded(self):
        q = DelayedQueue()
        width = 500
        for i in range(width):
            q.schedule("live-%d" % i, 10000, lambda _: None)
        baseline = q.internal_size()
        for i in range(100000):
            tid = "live-%d" % (i % width)
            q.cancel(tid)
            q.schedule(tid, 10000, lambda _: None)
        self.assertEqual(q.pending_count(), width)
        self.assertEqual(q.internal_size(), width)
        self.assertEqual(baseline, width)
        self._assert_invariant(q)


if __name__ == "__main__":
    unittest.main(verbosity=2)
