"""复杂度与内存实测。运行：python3 benchmark.py

* 复杂度：对不同规模 n 实测 schedule / cancel / pop 总耗时，
  若耗时 ~ O(n log n)，则 “每次操作耗时 / log2(n)” 应近似恒定。
* 内存：10 万次 插入+取消 churn，用 tracemalloc 对比首尾内存，
  并校验内部存活条目数始终等于实际待执行任务数。
"""

import math
import random
import time
import tracemalloc

from delay_queue import DelayQueue


def bench_ops(n, seed=1234):
    rng = random.Random(seed)
    q = DelayQueue()

    t0 = time.perf_counter()
    for i in range(n):
        q.schedule(f"t{i}", rng.uniform(0, 1e6))
    t_schedule = time.perf_counter() - t0

    ids = [f"t{i}" for i in range(n)]
    rng.shuffle(ids)
    t0 = time.perf_counter()
    for tid in ids[: n // 2]:          # 随机取消一半
        q.cancel(tid)
    t_cancel = time.perf_counter() - t0

    t0 = time.perf_counter()
    q.pop_due(now=2e6)                 # 一次性弹出剩余全部
    t_pop = time.perf_counter() - t0
    return t_schedule, t_cancel, t_pop


def bench_complexity():
    print("== 复杂度实测（每次操作平均耗时，及 耗时/log2(n) 的归一化值）==")
    header = f"{'n':>8} | {'schedule':>18} | {'cancel':>18} | {'pop':>18}"
    print(header)
    print("-" * len(header))
    for n in (10_000, 20_000, 40_000, 80_000, 160_000):
        ts, tc, tp = bench_ops(n)
        logn = math.log2(n)
        m = n // 2
        print(
            f"{n:>8} | {ts/n*1e6:7.2f}us {ts/n/logn*1e6:7.3f}us/logn |"
            f" {tc/m*1e6:7.2f}us {tc/m/logn*1e6:7.3f}us/logn |"
            f" {tp/m*1e6:7.2f}us {tp/m/logn*1e6:7.3f}us/logn"
        )
    print("说明：n 翻倍时 us/logn 列近似恒定 => 单次操作 O(log n)，总量 O(n log n)。")


def bench_memory():
    print("\n== 内存实测：100,000 次 插入+取消 churn ==")
    n = 100_000
    q = DelayQueue()

    # 预热 1 万次，排除解释器/解释层面的一次性分配
    for i in range(10_000):
        q.schedule(f"w{i}", 10)
        q.cancel(f"w{i}")

    tracemalloc.start()
    for round_ in range(2):
        for i in range(n):
            tid = f"r{round_}t{i}"
            q.schedule(tid, 10)
            q.cancel(tid)
        current, peak = tracemalloc.get_traced_memory()
        print(
            f"第 {round_ + 1} 个 10 万次 churn 后: "
            f"待执行={len(q)}, 内部存活条目={q.internal_size()}, "
            f"tracemalloc 当前={current/1024:.1f} KiB, 峰值={peak/1024:.1f} KiB"
        )
        assert q.internal_size() == len(q) == 0, "存活条目数与待执行任务数不一致！"
    tracemalloc.stop()
    print("结论：两轮 churn 后当前内存基本持平，内部条目数 == 待执行数 == 0，无泄漏。")


if __name__ == "__main__":
    bench_complexity()
    bench_memory()
