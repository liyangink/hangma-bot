# 测试房验收方案（四线修复后的活场验证）

> 前置：全套件 1262 绿；返工复审 accept；专家门禁在途（并行等待）。
> 基线对照：2026-09-04 测试赛 run-29a71a10ad12441eb15e0ac4cfb55c1d（M=10、160 局）。
> 指南基线：v15（KNOWN_GUIDE_VERSION=15，随官方同步更新）。

## 1. 验收目标与量化判据

| # | 验证项 | 基线（09-04 赛） | 通过判据 |
| --- | --- | --- | --- |
| A1 | S2 游标修复：全量重建频率 | protocol_recovered 场均 ~300（3063/10 场） | **场均 ≤ 10**（仅跨局边界；每场 16 局 ×1 次 + 容差） |
| A2 | S3 修复：hu 409 误报 | 97 次/120 次提交（81% 误报） | **误报 = 0**（门禁 + 双计归一化后） |
| A3 | S4+E1-E3：原始事件落盘 | 无（legacy 模式） | raw/*.jsonl 存在；validate_run 三条对账检查 0 violation；secret_scan_clean=true |
| A4 | 决策观察快照 | 无手牌记录 | decision_planned 含 observation_snapshot（my_hand/drawn_tile/phase/目标弃牌） |
| A5 | O-1 杠窗口样本 | 归档 3 场杠事件 = 0 | claim_if_legal 逢杠必杠 → 抓到杠后补牌窗口 /state 原文，核对 my_hand 长度 = 14−3×副露数（含摸牌形态） |
| A6 | O-2 边界退避时延 | 未测 | 每局首个 tile_discarded → 窗口投递时差 ≤ 1.0s 退避 + 轮询周期（从审计时间戳统计） |
| A7 | W2-1 防冻 | 未遇 | 若官方返回畸形 Retry-After（低概率）：冷却有界、不冻结（从审计可证） |
| A8 | 重复 pass 409（**预期仍在**） | 836 次 | 维持原量级——属响应窗口身份工作线（anchor_seq），**不算失败** |

## 1.1 已锁定基线（2026-09-05 复算；计数口径：按审计记录条数，hu 409 含双形态记录 ≈ 2×决策数）

| 指标 | 09-04 基线值 | 新房判据（同口径） |
| --- | --- | --- |
| A1 全量重建 | **3063 次 / 10 场 = 场均 306** | ≤ 10 |
| A2 hu 提交 | 接受 23 / 409 拒绝 194（误报率 89%） | 409 = 0 |
| A8 重复 pass 409 | 816 | 维持量级（非回归信号） |

## 2. 运行配置

- 入口：`run_test_room.py`（4 进程隔离），策略 **claim_if_legal**（逢合法即claim，最大化碰/吃/杠/胡提交量，最快撞出协议边界与杠样本；仓库惯例的测试房验收策略）
- 新房 token 路径约定：`token/test_<房间id>/{qinglong,baihu,zhuque,xuanwu}.txt`
- 配置：`configs/test-room-<房间id>.json`（mode=test_room、known_guide_version=15、audit_root=runs、strategy=claim_if_legal、insecure_hosts=[10.240.169.190]）
- 至少跑满 **2 个完整轮次**（每轮 4 桌 × Rounds 局），结束后保留四身份审计目录

## 3. 赛后分析动作（对基线出对照报告）

1. `validate_run` × 4 身份：完整性/对账/脱敏（A3）
2. decisions.jsonl 统计：hu 提交与 409 计数（A2）、重复 pass 计数（A8）、提交延迟分布
3. games/*.jsonl：protocol_recovered 场均计数（A1）、局首窗口时延（A6）
4. raw/*.jsonl：检索 gang 副露后的 draw 窗口 state 原文（A5），核对长度公式并回填金例
5. 产出：`doc/implementation/reviews/test-room-acceptance-result-<日期>.md`（对照表 + 样本引用 + 结论）

## 4. 风险与边界

- 房间空闲 30 分钟自动 close：token 就位后立即启动，避免中途长时间空窗
- 重复 pass 409（A8）不是回归信号；**重建计数未降**或 **hu 误报复现**才是
- 若触发平台侧异常（stage_crashed 等）：按既有语义处理并记录，不中断验收
