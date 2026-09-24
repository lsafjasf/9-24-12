"""原始（带缺陷）的延迟队列实现。

保留此文件仅用于回归对比：reproduce_issues.py 用它确定性地复现现网四类问题。
缺陷点均以 ``# BUG n`` 标注，与修复版 delay_queue.py 一一对应。
"""

import heapq


class BuggyDelayQueue:
    def __init__(self, clock):
        self._clock = clock
        self._heap = []           # 堆元素: (delay, task_id, payload)
        self._cancelled = set()   # 取消墓碑，永不清理
        self._history = []        # 每次 schedule 都追加，永不清理

    def schedule(self, task_id, delay, payload=None):
        # BUG 3: 堆的键是“相对延迟”而非绝对到期时刻。
        # 时钟推进后再入队的任务，键与早前入队的任务不可比，内部顺序错乱。
        heapq.heappush(self._heap, (delay, task_id, payload))
        self._history.append(task_id)  # BUG 4: 之一：只增不减

    def cancel(self, task_id):
        # BUG 1: 只删除第一个匹配的堆记录。同一 task_id 重复调度产生的
        # 其余副本仍然留在堆里，之后仍会被执行（“取消后偶尔仍执行”）。
        for i, item in enumerate(self._heap):
            if item[1] == task_id:
                del self._heap[i]
                heapq.heapify(self._heap)
                break
        # BUG 4 之二：墓碑只增不减，且从不校验/清理。
        self._cancelled.add(task_id)

    def pop_due(self, now=None):
        now = self._clock() if now is None else now
        due = []
        for delay, task_id, payload in self._heap:
            # BUG 2 之一：严格小于，deadline == now 的任务本轮取不到。
            if delay < now:
                due.append((task_id, payload))
        # BUG 2 之二：把 deadline <= now 的记录当作“过期”直接丢弃，
        # 于是同一到期时刻（deadline == now）的任务被永久漏掉。
        self._heap = [item for item in self._heap if item[0] > now]
        heapq.heapify(self._heap)
        return due

    def pending(self):
        return len(self._heap)

    def internal_size(self):
        """内部占用的条目总数（含墓碑与历史），用于观察内存增长。"""
        return len(self._heap) + len(self._cancelled) + len(self._history)
