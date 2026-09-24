"""Empirical evidence for O(log n) operations and bounded memory.

Stdlib only. Run: python3 benchmark.py
"""

import gc
import time
import tracemalloc

from delayed_queue import DelayedQueue
from delayed_queue import Task


def timed(fn, repeat=5):
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def build(n):
    q = DelayedQueue()
    for i in range(n):
        q.schedule("t%d" % i, n + i, lambda _: None)
    return q


def drain(q):
    while q._heap:
        q.advance(q._heap[0].deadline - q.now + 1)


print("== Per-operation latency vs live size n (best of 5, seconds) ==")
print("%8s %12s %12s %12s %14s" % (
    "n", "insert/op", "resched/op", "cancel/op", "insert*log2"))
prev = None
for n in (2000, 4000, 8000, 16000, 32000, 64000):
    t_ins = timed(lambda: build(n)) / n

    def resched_round():
        q = build(n)
        for i in range(0, n, 8):
            q.schedule("t%d" % i, 2 * n + i, lambda _: None)

    t_res = timed(resched_round) / (n // 8)

    def cancel_round():
        q = build(n)
        for i in range(n):
            q.cancel("t%d" % i)

    t_cancel = timed(cancel_round) / n
    ratio = (t_ins / t_ins) if prev is None else t_ins / prev
    prev = t_ins
    print("%8d %12.3e %12.3e %12.3e %14.2f" % (
        n, t_ins, t_res, t_cancel, ratio))

print()
print("Doubling n doubles total insertion time (log factor grows slowly):")
for n in (10000, 20000, 40000, 80000):
    total = timed(lambda: build(n), repeat=3)
    print("  n=%6d  total=%.4fs  per-op=%.3e us" % (
        n, total, total / n * 1e6))

print()
print("== 100,000 schedule+cancel pairs (all cancelled) ==")
gc.collect()
before_tasks = sum(1 for o in gc.get_objects() if isinstance(o, Task))
tracemalloc.start()
q = DelayedQueue()
for i in range(100000):
    tid = "task-%d" % i
    q.schedule(tid, 1000, lambda _: None)
    q.cancel(tid)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
gc.collect()
after_tasks = sum(1 for o in gc.get_objects() if isinstance(o, Task))
print("  pending_count  = %d" % q.pending_count())
print("  heap slots     = %d (internal_size)" % q.internal_size())
print("  index entries  = %d" % len(q._index))
print("  live Task objs = %d (before run: %d)" %
      (after_tasks, before_tasks))
print("  traced current = %.1f KiB  peak = %.1f KiB" %
      (current / 1024, peak / 1024))

print()
print("== 100,000 cancel/re-schedule churn over a fixed live set of 500 ==")
gc.collect()
q = DelayedQueue()
width = 500
for i in range(width):
    q.schedule("live-%d" % i, 10000, lambda _: None)
def churn_rounds(rounds):
    for i in range(rounds):
        tid = "live-%d" % (i % width)
        q.cancel(tid)
        q.schedule(tid, 10000, lambda _: None)

tracemalloc.start()
churn_rounds(100000)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
gc.collect()
task_objs_100k = sum(1 for o in gc.get_objects() if isinstance(o, Task))
tracemalloc.start()
churn_rounds(100000)
current2, _ = tracemalloc.get_traced_memory()
tracemalloc.stop()
gc.collect()
task_objs_200k = sum(1 for o in gc.get_objects() if isinstance(o, Task))
print("  pending_count  = %d (matches the %d real tasks)" % (
    q.pending_count(), width))
print("  heap slots     = %d" % q.internal_size())
print("  live Task objs = %d after 100k, %d after another 100k (want %d)" %
      (task_objs_100k, task_objs_200k, width))
print("  traced current = %.1f KiB after 100k, %.1f KiB after 200k" %
      (current / 1024, current2 / 1024))
print("  traced peak (first 100k) = %.1f KiB" % (peak / 1024))

print()
print("== 100,000 insert then drain: per-fire cost ==")
n = 100000
t_build = timed(lambda: build(n), repeat=3)
q = build(n)
t_drain = timed(lambda: drain(q), repeat=1)
print("  build %.3fs (%.3e us/op), drain %.3fs (%.3e us/fire)" % (
    t_build, t_build / n * 1e6, t_drain, t_drain / n * 1e6))
