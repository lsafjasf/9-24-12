## python3 reproduce.py --impl buggy
```
[BUG] 1. cancelled task still executed
      observed: ['t']
      expected: []
[BUG] 2. same-deadline tasks lost
      observed: []
      expected: ['a', 'b', 'c', 'd']
[BUG] 3. ordering corrupted after reschedule
      observed: (['a', 'c'], [1, 0])
      expected: (['c', 'a'], [0, 1])
[BUG] 4. unbounded memory after churn
      observed: (0, 100000)
      expected: (0, 0)
[BUG] 5. periodic self-reschedule lost
      observed: [10]
      expected: [5, 10, 15, 20]

delayed_queue_buggy: 0/5 scenarios correct
exit=1
```

## python3 reproduce.py --impl fixed
```
[OK ] 1. cancelled task still executed
[OK ] 2. same-deadline tasks lost
[OK ] 3. ordering corrupted after reschedule
[OK ] 4. unbounded memory after churn
[OK ] 5. periodic self-reschedule lost

delayed_queue: 5/5 scenarios correct
exit=0
```

## python3 -m unittest -v test_delayed_queue
```
test_100k_churn_with_live_set_stays_bounded (test_delayed_queue.DelayedQueueTest.test_100k_churn_with_live_set_stays_bounded) ... ok
test_100k_schedule_cancel_leaves_zero_entries (test_delayed_queue.DelayedQueueTest.test_100k_schedule_cancel_leaves_zero_entries) ... ok
test_basic_fire_on_deadline (test_delayed_queue.DelayedQueueTest.test_basic_fire_on_deadline) ... ok
test_callback_cancels_a_due_peer (test_delayed_queue.DelayedQueueTest.test_callback_cancels_a_due_peer) ... ok
test_cancel_before_due_never_runs (test_delayed_queue.DelayedQueueTest.test_cancel_before_due_never_runs) ... ok
test_cancel_is_permanent_across_reschedules (test_delayed_queue.DelayedQueueTest.test_cancel_is_permanent_across_reschedules) ... ok
test_cancel_unknown_id_is_noop (test_delayed_queue.DelayedQueueTest.test_cancel_unknown_id_is_noop) ... ok
test_deadline_order_is_monotonic (test_delayed_queue.DelayedQueueTest.test_deadline_order_is_monotonic) ... ok
test_periodic_self_reschedule (test_delayed_queue.DelayedQueueTest.test_periodic_self_reschedule) ... ok
test_random_drive_matches_sorted_model (test_delayed_queue.DelayedQueueTest.test_random_drive_matches_sorted_model) ... ok
test_reschedule_after_cancel_is_a_fresh_task (test_delayed_queue.DelayedQueueTest.test_reschedule_after_cancel_is_a_fresh_task) ... ok
test_reschedule_keeps_fifo_among_equal_new_deadlines (test_delayed_queue.DelayedQueueTest.test_reschedule_keeps_fifo_among_equal_new_deadlines) ... ok
test_reschedule_moves_deadline_with_single_entry (test_delayed_queue.DelayedQueueTest.test_reschedule_moves_deadline_with_single_entry) ... ok
test_reschedule_to_earlier_is_ordered_correctly (test_delayed_queue.DelayedQueueTest.test_reschedule_to_earlier_is_ordered_correctly) ... ok
test_same_deadline_fires_all_in_submission_order (test_delayed_queue.DelayedQueueTest.test_same_deadline_fires_all_in_submission_order) ... ok
test_self_reschedule_at_zero_delay_interleaves_fifo (test_delayed_queue.DelayedQueueTest.test_self_reschedule_at_zero_delay_interleaves_fifo) ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.348s

OK
```

## python3 benchmark.py
```
== Per-operation latency vs live size n (best of 5, seconds) ==
       n    insert/op   resched/op    cancel/op    insert*log2
    2000    5.005e-07    5.147e-06    2.086e-06           1.00
    4000    5.883e-07    5.436e-06    2.318e-06           1.18
    8000    6.137e-07    5.748e-06    2.504e-06           1.04
   16000    6.487e-07    6.100e-06    2.782e-06           1.06
   32000    6.564e-07    6.930e-06    4.176e-06           1.01
   64000    8.294e-07    8.987e-06    3.965e-06           1.26

Doubling n doubles total insertion time (log factor grows slowly):
  n= 10000  total=0.0055s  per-op=5.452e-01 us
  n= 20000  total=0.0136s  per-op=6.803e-01 us
  n= 40000  total=0.0279s  per-op=6.966e-01 us
  n= 80000  total=0.0745s  per-op=9.315e-01 us

== 100,000 schedule+cancel pairs (all cancelled) ==
  pending_count  = 0
  heap slots     = 0 (internal_size)
  index entries  = 0
  live Task objs = 0 (before run: 0)
  traced current = 0.6 KiB  peak = 0.9 KiB

== 100,000 cancel/re-schedule churn over a fixed live set of 500 ==
  pending_count  = 500 (matches the 500 real tasks)
  heap slots     = 500
  live Task objs = 500 after 100k, 500 after another 100k (want 500)
  traced current = 197.5 KiB after 100k, 197.7 KiB after 200k
  traced peak (first 100k) = 222.9 KiB

== 100,000 insert then drain: per-fire cost ==
  build 0.091s (9.102e-01 us/op), drain 0.334s (3.340e+00 us/fire)
```

Python: Python 3.12.3
