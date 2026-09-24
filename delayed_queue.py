"""Delayed task queue with a virtual clock (fixed implementation).

Design
------
* A custom indexed binary min-heap stores live entries only. Each entry is
  keyed by ``(deadline, seq)``: deadline gives time order and the monotonic
  submission counter makes equal deadlines resolve in FIFO submission order.
* A ``task_id -> heap position`` index makes cancel / reschedule a genuine
  O(log n) delete (followed by an O(log n) insert on reschedule) instead of
  tombstoning. Nothing dead is ever retained, so the physical heap size always
  equals the number of live tasks.
* A task may call :meth:`DelayedQueue.schedule` on itself from inside its own
  callback; the entry was already detached before the callback runs, so the
  re-scheduled instance is an ordinary new entry with no duplicates.

Complexity (n = number of currently live tasks):
  schedule   O(log n)
  cancel     O(log n)
  reschedule O(log n) + O(log n) = O(log n)
  advance    O((n - n') * log n) overall, i.e. O(log n) amortised per firing
"""


class Task:
    __slots__ = ("deadline", "seq", "task_id", "callback")

    def __init__(self, deadline, seq, task_id, callback):
        self.deadline = deadline
        self.seq = seq
        self.task_id = task_id
        self.callback = callback


class DelayedQueue:
    def __init__(self):
        self.now = 0
        self._heap = []                 # list[Task], live entries only
        self._index = {}               # task_id -> position in self._heap
        self._counter = 0

    def schedule(self, task_id, delay, callback):
        """Insert or replace a task; deadline is relative to the virtual now."""
        deadline = self.now + delay
        if task_id in self._index:
            self._remove(task_id)
        self._counter += 1
        self._push(Task(deadline, self._counter, task_id, callback))
        return deadline

    def cancel(self, task_id):
        """Remove a task immediately and permanently. Returns True if removed."""
        if task_id not in self._index:
            return False
        self._remove(task_id)
        return True

    def advance(self, delta):
        """Advance the virtual clock and fire every due task in time order."""
        self.now += delta
        fired = []
        while self._heap and self._heap[0].deadline <= self.now:
            task = self._heap[0]
            # Detach before invoking: self-reschedule inside the callback sees
            # no stale entry and cannot duplicate itself.
            self._pop()
            fired.append(task.task_id)
            task.callback(self)
        return fired

    def pending_count(self):
        return len(self._heap)

    def internal_size(self):
        """Physical slots used by the heap; equals the number of live tasks."""
        return len(self._heap)

    # -- indexed heap internals -------------------------------------------

    def _key(self, task):
        return (task.deadline, task.seq)

    def _push(self, task):
        pos = len(self._heap)
        self._heap.append(task)
        self._index[task.task_id] = pos
        self._sift_up(pos)

    def _pop(self):
        task = self._heap[0]
        del self._index[task.task_id]
        last = self._heap.pop()
        if self._heap:
            self._heap[0] = last
            self._index[last.task_id] = 0
            self._sift_down(0)
        return task

    def _remove(self, task_id):
        pos = self._index.pop(task_id)
        last = self._heap.pop()
        if pos < len(self._heap):
            self._heap[pos] = last
            self._index[last.task_id] = pos
            self._sift_up(pos)
            self._sift_down(pos)

    def _sift_up(self, pos):
        heap = self._heap
        index = self._index
        task = heap[pos]
        key = self._key(task)
        while pos > 0:
            parent = (pos - 1) >> 1
            if self._key(heap[parent]) <= key:
                break
            heap[pos] = heap[parent]
            index[heap[pos].task_id] = pos
            pos = parent
        heap[pos] = task
        index[task.task_id] = pos

    def _sift_down(self, pos):
        heap = self._heap
        index = self._index
        size = len(heap)
        task = heap[pos]
        key = self._key(task)
        while True:
            smallest = pos
            smallest_key = key
            left = pos * 2 + 1
            right = left + 1
            if left < size:
                left_key = self._key(heap[left])
                if left_key < smallest_key:
                    smallest = left
                    smallest_key = left_key
            if right < size:
                right_key = self._key(heap[right])
                if right_key < smallest_key:
                    smallest = right
                    smallest_key = right_key
            if smallest == pos:
                heap[pos] = task
                index[task.task_id] = pos
                return
            heap[pos] = heap[smallest]
            index[heap[pos].task_id] = pos
            pos = smallest
