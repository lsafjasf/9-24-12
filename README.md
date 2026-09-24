# 延迟队列缺陷修复（Python 3，仅标准库）

## 文件

| 文件 | 说明 |
|---|---|
| `buggy_delay_queue.py` | 原始带缺陷实现（仅用于复现对比，缺陷点以 `# BUG n` 标注） |
| `delay_queue.py` | 修复后的实现 |
| `reproduce_issues.py` | 四类现网问题的确定性复现用例（FakeClock 控制时间，无真实等待） |
| `test_delay_queue.py` | 修复版回归测试（unittest，10 个用例） |
| `benchmark.py` | 复杂度与内存实测 |

## 四类缺陷与修复对照

1. **取消后仍执行**：原实现 `cancel` 只删除第一个匹配副本，重复调复用 `task_id` 时残留副本仍会触发。
   修复：`_pos` 索引（`task_id -> 堆下标`）唯一定位，重新调度先物理移除旧条目；取消即物理删除，立即且不可逆。
2. **同一到期时刻任务丢失**：原实现用严格 `<` 判断到期，又把 `deadline <= now` 的记录当“过期”丢弃。
   修复：到期判断为 `deadline <= now`，堆序键 `(deadline, seq)` 中 `seq` 为单调提交序号，同时刻任务严格按提交顺序 FIFO 弹出，一个不漏。
3. **时钟推进后顺序错乱**：原实现堆键是“相对延迟”，不同时刻入队的任务键不可比。
   修复：`schedule` 入队时即换算为绝对到期时刻 `clock() + delay`，时钟任意推进不影响堆序；弹出顺序按 `(deadline, seq)` 字典序，到期时间严格单调非降。
4. **内存持续增长**：原实现保留取消墓碑与历史列表，只增不减。
   修复：取消为 O(log n) 物理删除，无墓碑、无懒删除残留，堆内条目数恒等于待执行任务数。

## 复杂度说明

索引二叉最小堆 + 哈希索引：

| 操作 | 复杂度 | 说明 |
|---|---|---|
| `schedule` / `schedule_at` | O(log n) | 堆尾插入 + 上浮 |
| `cancel` | O(log n) | `_pos` O(1) 定位，堆中物理删除 + 上/下沉 |
| `pop_due` / `run_due` | O(k log n) | k 为到期任务数，每次取堆顶 O(log n) |
| `next_deadline` / `len` | O(1) | 堆顶 / 长度 |

实测（`python3 benchmark.py`，n 翻倍时每次操作耗时仅缓慢增长，符合 O(log n)；
若为全表扫描的 O(n)，n 从 1 万到 16 万每次操作耗时应增约 16 倍，实测仅约 1.4–3 倍，差额为缓存效应）：

```
       n |           schedule |             cancel |                pop
-----------------------------------------------------------------------
   10000 |    1.15us   0.087us/logn |    0.78us   0.059us/logn |    2.62us   0.197us/logn
   20000 |    1.00us   0.070us/logn |    1.17us   0.082us/logn |    3.35us   0.235us/logn
   40000 |    1.25us   0.082us/logn |    2.64us   0.173us/logn |    6.23us   0.407us/logn
   80000 |    1.37us   0.084us/logn |    2.75us   0.169us/logn |    6.78us   0.416us/logn
  160000 |    1.61us   0.093us/logn |    3.44us   0.199us/logn |    8.32us   0.481us/logn
```

## 内存不增长证据

连续 10 万次“插入 + 取消”churn（重复两轮）后：

```
第 1 个 10 万次 churn 后: 待执行=0, 内部存活条目=0, tracemalloc 当前=0.1 KiB, 峰值=0.3 KiB
第 2 个 10 万次 churn 后: 待执行=0, 内部存活条目=0, tracemalloc 当前=0.3 KiB, 峰值=0.6 KiB
```

存活条目数与实际待执行任务数始终一致（回归测试 `TestMemory` 在 churn 过程中每 5000 次断言一次）。

## 周期性任务

`run_due(fn)` 逐个弹出并立即执行，回调内可 `q.schedule(自身id, period)` 重新调度：
旧实例已物理弹出，新实例是唯一条目，只要 `period > 0` 就不会在本轮重复执行，
后续实例按新到期时刻正常触发（见 `TestPeriodicReschedule`）。

## 运行命令

```bash
python3 reproduce_issues.py            # 复现四类缺陷（ buggy 实现上 4/4 ）
python3 -m unittest test_delay_queue -v  # 修复版回归测试（10 个用例全过）
python3 benchmark.py                   # 复杂度与内存实测
```
