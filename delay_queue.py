"""延迟任务队列（修复版），仅依赖标准库。

设计要点
--------
* 索引二叉最小堆：堆元素为 _Entry，堆序键为 (deadline, seq)。
  - schedule / cancel / pop 均为 O(log n)，不扫描全表；
  - _pos 维护 task_id -> 堆下标，取消时直接定位并物理删除，
    取消立即生效且不可逆，不留墓碑，内存不随churn增长。
* seq 为单调递增的提交序号：同一到期时刻的任务严格按提交顺序执行；
  整体取出顺序按 (deadline, seq) 字典序，到期时间严格单调（非降）。
* 堆键使用绝对到期时刻，时钟任意推进不影响内部顺序。
* 任务可在执行期间通过 run_due 的回调重新调度自身（周期性任务）：
  旧实例已被物理弹出，新实例是唯一新条目，不产生重复、不漏后续实例。
"""

import time


class _Entry:
    __slots__ = ("deadline", "seq", "task_id", "payload")

    def __init__(self, deadline, seq, task_id, payload):
        self.deadline = deadline
        self.seq = seq
        self.task_id = task_id
        self.payload = payload


class DelayQueue:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._heap = []   # list[_Entry]，按 (deadline, seq) 排列的二叉最小堆
        self._pos = {}    # task_id -> 堆下标
        self._seq = 0     # 单调提交序号，同时刻任务的 FIFO 依据

    # ------------------------------------------------------------------
    # 堆内部操作（均为 O(log n)）
    # ------------------------------------------------------------------
    @staticmethod
    def _less(a, b):
        return (a.deadline, a.seq) < (b.deadline, b.seq)

    def _swap(self, i, j):
        heap = self._heap
        heap[i], heap[j] = heap[j], heap[i]
        self._pos[heap[i].task_id] = i
        self._pos[heap[j].task_id] = j

    def _sift_up(self, i):
        heap = self._heap
        while i > 0:
            parent = (i - 1) // 2
            if self._less(heap[i], heap[parent]):
                self._swap(i, parent)
                i = parent
            else:
                break

    def _sift_down(self, i):
        heap = self._heap
        n = len(heap)
        while True:
            child = 2 * i + 1
            if child >= n:
                break
            if child + 1 < n and self._less(heap[child + 1], heap[child]):
                child += 1
            if self._less(heap[child], heap[i]):
                self._swap(i, child)
                i = child
            else:
                break

    def _remove_at(self, i):
        heap = self._heap
        entry = heap[i]
        last = heap.pop()
        del self._pos[entry.task_id]
        if i < len(heap):
            heap[i] = last
            self._pos[last.task_id] = i
            self._sift_down(i)
            self._sift_up(i)
        return entry

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    def schedule_at(self, task_id, deadline, payload=None):
        """按绝对到期时刻入队；task_id 已存在时先移除旧条目（重新调度）。"""
        if task_id in self._pos:
            self._remove_at(self._pos[task_id])
        entry = _Entry(deadline, self._seq, task_id, payload)
        self._seq += 1
        self._pos[task_id] = len(self._heap)
        self._heap.append(entry)
        self._sift_up(len(self._heap) - 1)
        return deadline

    def schedule(self, task_id, delay, payload=None):
        """按相对延迟入队，返回绝对到期时刻。"""
        return self.schedule_at(task_id, self._clock() + delay, payload)

    def cancel(self, task_id):
        """取消任务：立即物理删除，不可逆。返回是否确有该任务。"""
        i = self._pos.get(task_id)
        if i is None:
            return False
        self._remove_at(i)
        return True

    def pop_due(self, now=None):
        """取出全部到期任务，按 (deadline, seq) 顺序返回 [(task_id, payload)]。"""
        now = self._clock() if now is None else now
        out = []
        heap = self._heap
        while heap and heap[0].deadline <= now:
            entry = self._remove_at(0)
            out.append((entry.task_id, entry.payload))
        return out

    def run_due(self, fn, now=None):
        """逐个取出到期任务并立刻以 fn(task_id, payload) 执行。

        回调内可安全地 cancel 其他任务或重新调度自身（周期性任务）：
        新实例按新的到期时刻入队，只要 delay > 0 就不会在本轮被重复执行。
        """
        now = self._clock() if now is None else now
        ran = 0
        heap = self._heap
        while heap and heap[0].deadline <= now:
            entry = self._remove_at(0)
            fn(entry.task_id, entry.payload)
            ran += 1
            heap = self._heap
        return ran

    def next_deadline(self):
        """最早到期时刻；队列为空时返回 None。"""
        return self._heap[0].deadline if self._heap else None

    def __len__(self):
        return len(self._heap)

    def __contains__(self, task_id):
        return task_id in self._pos

    def internal_size(self):
        """内部实际占用条目数（堆 + 索引共享同一批 _Entry，无墓碑）。"""
        return len(self._heap)
