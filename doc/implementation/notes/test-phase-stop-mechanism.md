# 测试阶段确定性中止机制（2026-09-05 定稿）

> 状态：已在测试房 t_9779c892550e 全程实战验证；正式赛事**禁用**（正式赛事走完整生命周期，不适用人工中止）。

## 结论

测试房阶段需要"不再发起下一轮、让当前局自然打完"的中止时，使用：

```bash
pkill -9 -f run_test_room.py
```

只杀编排器（orchestrator），**不要**同时匹配 `run_participant.py`。之后不做任何操作，等待四个子进程自然退出。

## 为什么它是确定性的

SIGKILL 不可被捕获、阻塞或转发，编排器没有机会执行任何清理/重启逻辑；随后：

1. 四个 `run_participant.py` 子进程成为孤儿进程，继续打完当前轮剩余局；
2. 每个子进程在 `tournament_finished` 终态到达后正常退出（实测退出码 0），审计照常落盘收尾；
3. 没有父进程 ⇒ 没有守护重启 ⇒ 没有 register/ready ⇒ 测试房不满足开轮条件 ⇒ 房间约 30 分钟空闲后自动关闭。不存在"误杀进行中的局"或"中止后又开新轮"的可能。

## 验证记录（2026-09-05，t_9779c892550e）

- 杀编排器后 4 个孤儿子进程全部打完 r6 双桌（b0/b1 两场），各自 `participant_finished`（reason=tournament_finished）；
- 4 个 run 目录 `summary.json`：`audit_degraded=false`、`write_failures=0`、`dropped_low_priority=0`、`raw_retention.dropped=0`；
- 会话终局复盘与牌谱导出见 `test-room-20260905-retrospective.md`。

## 使用步骤

1. 确认要中止的是测试房编排器：`pgrep -fl run_test_room.py`（应恰好 1 个）；
2. `pkill -9 -f run_test_room.py`；
3. `pgrep -fl run_participant.py` 确认 4 个子进程仍在（孤儿化成功）；
4. 等待子进程退出（可轮询审计目录的 `summary.json` 或进程表）；子进程退出即中止完成，房间随后自行关闭。

## 被废弃的旧方案：状态哨兵

早期实现轮询平台状态，发现 `finished/registering` 即追杀重启链。其缺陷：

- **竞态**：2 秒轮询间隔对 2 秒重启延迟 + 3-5 秒 init/register/ready 链，胜负取决于采样相位；
- **跨态漏检**：`finished → registering` 若在一次采样间隔内完成跨越，哨兵永远看不到目标态；
- **事后追杀**：即使杀对了进程，也可能已发出 register/ready，留下不可预测的半开轮。

SIGKILL 方案不依赖任何状态检测，从机制上消除以上三类失败。
