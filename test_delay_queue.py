"""delay_queue 修复版回归测试。运行：python3 -m unittest test_delay_queue -v"""

import random
import unittest

from delay_queue import DelayQueue


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


class TestCancel(unittest.TestCase):
    def test_cancel_is_immediate_and_irreversible(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        q.schedule("job", 10, "v1")
        self.assertTrue(q.cancel("job"))
        self.assertEqual(len(q), 0)
        clock.advance(100)
        self.assertEqual(q.pop_due(), [])          # 取消后绝不执行
        self.assertFalse(q.cancel("job"))          # 不可逆：不能重复取消
        q.schedule("job", 5, "v2")                 # 同名任务可重新提交（新实例）
        clock.advance(5)
        self.assertEqual(q.pop_due(), [("job", "v2")])

    def test_cancel_after_reschedule_removes_all_copies(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        q.schedule("job", 10, "v1")
        q.schedule("job", 20, "v2")                # 重新调度 = 替换，而非副本
        self.assertEqual(len(q), 1)
        self.assertTrue(q.cancel("job"))
        clock.advance(100)
        self.assertEqual(q.pop_due(), [])


class TestSameDeadline(unittest.TestCase):
    def test_same_deadline_fifo_no_loss(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        n = 1000
        for i in range(n):
            q.schedule(f"t{i}", 50, i)
        clock.advance(50)                          # 恰好到期时刻（边界）
        ran = q.pop_due()
        self.assertEqual(len(ran), n)              # 一个不漏
        self.assertEqual([p for _, p in ran], list(range(n)))  # 严格提交序

    def test_boundary_deadline_equals_now_is_due(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        q.schedule("x", 10)
        clock.advance(10)
        self.assertEqual(len(q.pop_due()), 1)


class TestOrdering(unittest.TestCase):
    def test_monotonic_order_after_clock_advances(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        rng = random.Random(20260924)
        expected = []
        seq_of = {}
        # 交织“推进时钟 + 随机延迟入队”，覆盖时钟推进后的顺序
        for i in range(5000):
            clock.advance(rng.uniform(0, 5))
            d = rng.uniform(0, 100)
            q.schedule(f"t{i}", d, i)
            expected.append((clock.now + d, i))
            seq_of[i] = i
        clock.advance(1000)
        ran = q.pop_due()
        deadlines = [dl for dl, _ in sorted(expected, key=lambda x: (x[0], x[1]))]
        got_ids = [p for _, p in ran]
        want_ids = [i for _, i in sorted(expected, key=lambda x: (x[0], x[1]))]
        self.assertEqual(got_ids, want_ids)        # 到期顺序单调 + 同时刻 FIFO
        self.assertEqual(sorted(got_ids), list(range(5000)))   # 不丢不重

    def test_interleaved_pop_stays_monotonic(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        rng = random.Random(99)
        last = -1.0
        for round_ in range(100):
            for i in range(10):
                q.schedule(f"r{round_}t{i}", rng.uniform(0, 30))
            clock.advance(rng.uniform(0, 5))
            while q and q.next_deadline() <= clock.now:
                dl = q.next_deadline()
                self.assertGreaterEqual(dl, last)  # 严格单调非降
                last = dl
                q.pop_due()


class TestPeriodicReschedule(unittest.TestCase):
    def test_self_rescheduling_periodic_task(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        runs = []

        def make_handler(period, total):
            def handler(task_id, payload):
                runs.append((task_id, clock.now))
                if len([r for r in runs if r[0] == task_id]) < total:
                    q.schedule(task_id, period)    # 执行期间重新调度自身
            return handler

        q.schedule("heartbeat", 10)
        handler = make_handler(10, 5)
        for _ in range(5):
            clock.advance(10)
            q.run_due(handler)
            self.assertEqual(len(q), 1 if len(runs) < 5 else 0)  # 无重复条目
        self.assertEqual([t for _, t in runs], [10.0 * k for k in range(1, 6)])
        clock.advance(1000)
        self.assertEqual(q.pop_due(), [])          # 无残留实例被漏掉或重复

    def test_multiple_periodic_tasks_no_cross_talk(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        counts = {"a": 0, "b": 0}

        def handler(task_id, payload):
            counts[task_id] += 1
            if counts[task_id] < 4:
                q.schedule(task_id, 3 if task_id == "a" else 7)

        q.schedule("a", 3)
        q.schedule("b", 7)
        for _ in range(30):
            clock.advance(1)
            q.run_due(handler)
        self.assertEqual(counts, {"a": 4, "b": 4})
        self.assertEqual(len(q), 0)


class TestMemory(unittest.TestCase):
    def test_no_growth_after_100k_insert_cancel(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        n = 100_000
        for i in range(n):
            q.schedule(f"t{i}", 10)
            q.cancel(f"t{i}")
            clock.advance(1)
        self.assertEqual(len(q), 0)
        self.assertEqual(q.internal_size(), len(q))  # 存活条目 == 待执行条目

    def test_live_entries_match_pending_during_churn(self):
        clock = FakeClock()
        q = DelayQueue(clock)
        live = set()
        rng = random.Random(42)
        for i in range(50_000):
            tid = f"t{i}"
            q.schedule(tid, rng.uniform(1, 100))
            live.add(tid)
            if live and rng.random() < 0.7:        # 大概率取消一个存活任务
                victim = rng.choice(tuple(live))
                if q.cancel(victim):
                    live.discard(victim)
            if i % 5000 == 0:
                self.assertEqual(len(q), len(live))
                self.assertEqual(q.internal_size(), len(live))
        self.assertEqual(len(q), len(live))


if __name__ == "__main__":
    unittest.main()
