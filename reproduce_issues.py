"""复现脚本：在 buggy_delay_queue 上确定性复现现网四类问题。

全部使用 FakeClock 控制时间推进，无任何真实等待，结果完全确定。
运行：python3 reproduce_issues.py
"""

from buggy_delay_queue import BuggyDelayQueue


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


def issue1_cancelled_task_still_runs():
    clock = FakeClock()
    q = BuggyDelayQueue(clock)
    q.schedule("job", 10, "v1")
    q.schedule("job", 20, "v2")   # 重复调度产生两个副本
    q.cancel("job")               # 只删掉第一个副本
    clock.advance(30)
    ran = q.pop_due()
    ok = ran == []
    print(f"[问题1] 取消后仍执行: ran={ran}  ->  {'复现成功(缺陷存在)' if not ok else '未复现'}")
    return not ok


def issue2_same_deadline_tasks_lost():
    clock = FakeClock()
    q = BuggyDelayQueue(clock)
    for i in range(3):
        q.schedule(f"t{i}", 50, i)
    clock.advance(50)             # 时钟正好走到到期时刻
    ran = q.pop_due()
    clock.advance(1000)           # 之后再取也永远拿不到
    ran += q.pop_due()
    ok = len(ran) == 3
    print(f"[问题2] 同一时刻任务丢失: 应执行3个, 实际{len(ran)}个  ->  {'复现成功(缺陷存在)' if not ok else '未复现'}")
    return not ok


def issue3_order_broken_after_clock_advance():
    clock = FakeClock()
    q = BuggyDelayQueue(clock)
    q.schedule("A", 1000, "A")    # 绝对到期时刻 1000
    clock.advance(900)
    q.schedule("B", 200, "B")     # 绝对到期时刻 1100，应晚于 A
    clock.advance(150)            # now=1050：A 已到期，B 尚未到期
    ran = q.pop_due()
    # 正确行为：只有 A 到期；缺陷行为：B 被提前执行且顺序错乱
    ok = ran == [("A", "A")]
    print(f"[问题3] 时钟推进后顺序错乱: now=1050 时取出 {ran}（B 的到期时刻是 1100） ->  {'复现成功(缺陷存在)' if not ok else '未复现'}")
    return not ok


def issue4_memory_grows_forever():
    clock = FakeClock()
    q = BuggyDelayQueue(clock)
    n = 100_000
    for i in range(n):
        q.schedule(f"t{i}", 10)
        q.cancel(f"t{i}")
        clock.advance(1)
    internal = q.internal_size()
    pending = q.pending()
    ok = internal == pending
    print(f"[问题4] 内存持续增长: 10万次插入+取消后 待执行={pending}, 内部占用={internal}  ->  {'复现成功(缺陷存在)' if not ok else '未复现'}")
    return not ok


if __name__ == "__main__":
    results = [
        issue1_cancelled_task_still_runs(),
        issue2_same_deadline_tasks_lost(),
        issue3_order_broken_after_clock_advance(),
        issue4_memory_grows_forever(),
    ]
    print(f"\n共复现 {sum(results)}/4 类缺陷（在 buggy 实现上全部应为 4/4）")
