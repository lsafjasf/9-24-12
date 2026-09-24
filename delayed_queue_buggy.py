"""Buggy delayed queue (the "production" version under repair).

Deterministic virtual clock; no threads and no real waiting.

Known defects demonstrated here:
  1. A cancelled task can still run after it was re-scheduled once, because the
     cancelled marker is consumed by the first popped (stale) heap entry.
  2. The ready test uses a strict `< now`, so tasks scheduled exactly at the
     current tick are silently dropped.
  3. Re-scheduling mutates a heap entry in place instead of restoring the heap
     invariant, corrupting ordering after the clock advances.
  4. Cancellation leaves the dead entry in the heap, so long-running
     schedule/cancel churn grows memory without bound.
"""

import heapq


class DelayedQueue:
    def __init__(self):
        self.now = 0
        self._heap = []          # entries: [deadline, seq, task_id, callback]
        self._entries = {}       # task_id -> current heap entry
        self._cancelled = set()  # task ids that were cancelled

    def schedule(self, task_id, delay, callback):
        deadline = self.now + delay
        old = self._entries.get(task_id)
        if old is not None:
            # BUG: mutate a live heap node in place; the heap ordering is now
            # corrupted (and the old deadline's duplicate semantics rely on the
            # cancelled-set hack below).
            old[0] = deadline
            old[3] = callback
            entry = old
        else:
            entry = [deadline, 0, task_id, callback]
            heapq.heappush(self._heap, entry)
        self._entries[task_id] = entry
        return deadline

    def cancel(self, task_id):
        # BUG: one-shot marker; a stale duplicate popped later "un-cancels" it.
        self._cancelled.add(task_id)
        self._entries.pop(task_id, None)

    def advance(self, delta):
        self.now += delta
        fired = []
        while self._heap:
            entry = self._heap[0]
            deadline, _seq, task_id, callback = entry
            # BUG: strict comparison drops tasks whose deadline == now.
            if not (deadline < self.now):
                break
            heapq.heappop(self._heap)
            if task_id in self._cancelled:
                # BUG: removing the marker here lets a later duplicate for the
                # same id execute even though cancellation is supposed to be
                # permanent... and re-scheduling also leaves this marker set,
                # suppressing the freshly scheduled instance.
                self._cancelled.discard(task_id)
                continue
            # BUG: the popped entry is left dangling in the index. A task that
            # re-schedules itself from inside its callback will "update" this
            # dead node, so every later instance is lost.
            fired.append(task_id)
            callback(self)
        return fired

    def pending_count(self):
        return len(self._entries)

    def internal_size(self):
        """Number of physical slots retained inside the heap."""
        return len(self._heap)
