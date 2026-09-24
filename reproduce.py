"""Deterministic repro cases for the four production incidents.

No real waiting: every queue owns a virtual clock advanced explicitly.

Usage:
    python3 reproduce.py --impl buggy
    python3 reproduce.py --impl fixed

Each scenario prints OBSERVED vs EXPECTED. With the buggy implementation every
scenario diverges in a fixed, reproducible way; with the fixed implementation
they all match.
"""

import argparse
import importlib


def scenario_cancel_is_final(mod):
    """Cancellation must be immediate and irreversible across re-schedules."""
    q = mod.DelayedQueue()
    fired = []
    q.schedule("t", 10, lambda queue: fired.append("t"))
    q.advance(4)
    q.cancel("t")
    # A duplicate re-schedule + cancel sequence must not "revive" the task.
    q.schedule("t", 10, lambda queue: fired.append("t"))
    q.cancel("t")
    q.advance(100)
    return fired, []


def scenario_same_deadline_fifo(mod):
    """All tasks at one deadline fire, in submission order (deadline == now)."""
    q = mod.DelayedQueue()
    fired = []
    for name in ("a", "b", "c", "d"):
        q.schedule(name, 5, lambda queue, n=name: fired.append(n))
    q.advance(5)  # land exactly on the deadline: strict-< bug drops everything
    return fired, ["a", "b", "c", "d"]


def scenario_ordering_after_reschedule(mod):
    """Deadlines fired must be strictly monotonic after clock advancement."""
    q = mod.DelayedQueue()
    fired = []
    order = []
    q.schedule("a", 1, lambda queue: (fired.append("a"), order.append(1)))
    q.schedule("b", 3, lambda queue: (fired.append("b"), order.append(3)))
    q.schedule("c", 4, lambda queue: (fired.append("c"), order.append(0)))
    # Pull a non-root heap node (c) *earlier* in place: the heap invariant is
    # now violated (c becomes due at deadline 0 but stays buried).
    q.schedule("c", 0, lambda queue: (fired.append("c"), order.append(0)))
    q.schedule("b", 5, lambda queue: (fired.append("b"), order.append(5)))
    q.advance(2)  # c(deadline 0) must fire before a(deadline 1)
    return (fired, order), (["c", "a"], [0, 1])


def scenario_memory_churn(mod, count=100000):
    """100k schedule/cancel pairs must leave zero live and zero stored slots."""
    q = mod.DelayedQueue()
    for i in range(count):
        tid = "task-%d" % i
        q.schedule(tid, 1000, lambda queue: None)
        q.cancel(tid)
    live = q.pending_count()
    stored = q.internal_size()
    return (live, stored), (0, 0)


def scenario_self_reschedule(mod):
    """A periodic task re-scheduling itself must not duplicate or get lost."""
    q = mod.DelayedQueue()
    fired = []

    def periodic(queue):
        fired.append(queue.now)
        if queue.now < 20:
            queue.schedule("p", 5, periodic)

    q.schedule("p", 5, periodic)
    for _ in range(5):
        q.advance(5)
    return fired, [5, 10, 15, 20]


SCENARIOS = [
    ("1. cancelled task still executed", scenario_cancel_is_final),
    ("2. same-deadline tasks lost", scenario_same_deadline_fifo),
    ("3. ordering corrupted after reschedule", scenario_ordering_after_reschedule),
    ("4. unbounded memory after churn", scenario_memory_churn),
    ("5. periodic self-reschedule lost", scenario_self_reschedule),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--impl", choices=("buggy", "fixed"), required=True)
    args = parser.parse_args()
    mod_name = "delayed_queue" if args.impl == "fixed" else "delayed_queue_buggy"
    mod = importlib.import_module(mod_name)

    failures = 0
    for title, fn in SCENARIOS:
        observed, expected = fn(mod)
        ok = observed == expected
        failures += not ok
        status = "OK " if ok else "BUG"
        print("[%s] %s" % (status, title))
        if not ok:
            print("      observed: %s" % (observed,))
            print("      expected: %s" % (expected,))
    print()
    print("%s: %d/%d scenarios correct" % (mod_name, len(SCENARIOS) - failures,
                                           len(SCENARIOS)))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
