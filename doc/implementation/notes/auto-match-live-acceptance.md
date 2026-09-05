# 自由赛自动匹配真实房验收计划（auto-match live acceptance）

> 日期：2026-09-06。状态：已执行完毕，验收报告见 `doc/implementation/reviews/auto-match-live-acceptance-2026-09-06.md`。
> 前提：授权全局 Token（用户提供）、官方内网可达、当前工作树为集成完成态（全量 1416 passed / 0 failed）。
> 对应交付：`doc/implementation/handoffs/free-match.md`（§6 未验证项是本计划的消项目标）。

## 1. 两个工作线的耦合点与验收分工

代码层面已闭环，**不需要额外集成**。耦合点如下，审计 agent 在测试期间只读观察、不写 `runs/{run_id}`：

| 耦合点 | 实现 | 活场验收观察 |
| --- | --- | --- |
| match 原文留存 | 自由赛适配器在每次 `POST /api/match` 时调用审计线的 `build_match_response_payload`（source=`match_response`，v1）落 raw | `runs/{run_id}/raw/global.jsonl` 有完整脱敏原文；无 Token/Authorization |
| 生命周期词表 | 自由赛发出 `LIFECYCLE_CHANGED(area=auto_match)`（matching_started/matched/waiting/running/draining/finished/matching_stopped）与 `PROTOCOL_RECOVERED`；审计线 validator 词表已登记 | `audit_tool validate` 通过；事件序列顺序正确 |
| 终局与结果 | 每场 `GAME_FINISHED`（final_scores + authoritative_seq）落审计；赛后审计线 `offline` codec 转统一牌谱 | 10 场终局齐全；`audit_tool convert` 烟测 hand_id 数量 |
| 运行目录 | 双方共用 `runs/{run_id}` 标准布局（manifest/事件/raw） | 审计 agent 用 `audit_tool watch`/`validate` 只读 |

分工：本线（自由赛）负责运行进程与运行期观察；审计 agent 并行只读观察审计产物、赛后做 validate/convert 与脱敏复核。

## 2. 前置检查（在发起任何 POST /api/match 之前）

| # | 检查项 | 方法与判据 |
| --- | --- | --- |
| P1 | 配置核对 | mode=auto_match、token_kind=official、base_url=官方内网、known_guide_version=15、声明上限 M=10/Rounds=8（≥服务默认，避免永久 `NO_ROOM_AVAILABLE`）、sse_enabled、audit_root |
| P2 | Token 是全局 Token | 经 `/api/me` 确认 tournament 绑定为空；报名 Token 会在 `/api/match` 得到 `400 TOKEN_NOT_SCOPED`（分类停止，不重试） |
| P3 | 无已有归属 | 该账号无其他在途自动房/赛事占用（16 格上限、50 建房在途上限）；有已知自动房则用 `expected_tournament_id` 走恢复路径，绝不新占一席 |
| P4 | 网络可达 | 不携带 Token 的 `GET /portal/api/guide/version` 可达且版本 ≥15 无未知 breaking 变更 |
| P5 | 中止预案 | 401、未知 breaking 指南版本、TARGET_MISMATCH、连续限流、结果缺失 → 停止并保留全部证据；退出码 10 = 永久停止语义，守护不得重启重试 |

Token 安全：只经环境变量 `HM_AUTO_MATCH_TOKEN` 或 `--token-file`（文件放 git 忽略路径，如 `runs/` 下或 `*.local` 文件）；绝不写入已入库的 `configs/*.json`、命令行参数或任何日志/审计文本。验收结束后删除/移出私有文件。

## 3. 运行中验证项（逐一对应 handoff §6 未验证项 1–5）

| # | 验证项 | 观察点与通过判据 |
| --- | --- | --- |
| L1 | match 响应真实形态 | 留存 `{room_id, config, round_no}` 原文 fixture（脱敏 + SHA-256）；解析成功，`round_no` 只留原文不当单局号 |
| L2 | 房间详情 kind 字段 | kind 存在且 =auto 或缺失；缺失按“未确认证据继续 + 审计”口径；≠auto 必须 TARGET_MISMATCH |
| L3 | rules 端点可达性 | `/api/tournaments/{room_id}/rules` 对全局 Token 实际返回 200/403/404；非 200 时核验链的实际表现（记录，不臆测） |
| L4 | 等待期时间线 | 等待期 status 实际取值序列与等待时长；长期不满是否 void/解散（本次实测） |
| L5 | 运行期节奏 | M=10 场并发节奏；1s/3s 窗口动作耗时分布；超时/自动代打计数；409 重复提交误报 = 0；seq 缺口/权威重建计数 |
| L6 | match 配额 | 实际 POST /api/match 次数、相邻间隔 ≥6s、60 秒窗口 ≤10 次（审计 raw 核对） |
| L7 | SSE 真实样本 | 是否捕获 `closed:true` 真实终态帧；SSE 不可用降级时 `trigger=sse_degraded` 记录 |
| L8 | register/ready 隔离 | 全程 register/ready HTTP 调用数 = 0（raw 端到端核对，非仅单元测试） |

## 4. 收尾与结果留存

| # | 验证项 | 通过判据 |
| --- | --- | --- |
| C1 | 终局覆盖 | 10 场各 1 条 `GAME_FINISHED`（final_scores + seq）；draining 补抓行为记录；`drain_missing_finals` 出现与否如实记录 |
| C2 | 关闭时间线 | finished → closed → 404 的实际时间窗口（官方约 60s）实测值 |
| C3 | 退出语义 | RESULT 行（run_id、终态 reason、脱敏身份前缀）；退出码 0=正常完赛、10=永久停止；无 finished 证据的 404 → 结果缺失/未知口径（若出现） |
| C4 | 结果留存 | 匹配原文 fixture、全部场次列表、实际 M/Rounds、结果覆盖、关闭报告 + SHA-256；`audit_tool validate` 报告；事件序列核对（matching_started→matched→waiting→running→draining→finished） |
| C5 | 脱敏复核 | 审计 agent 复核 raw/事件/异常中无 Token、Authorization 或身份敏感原文 |

## 5. 通过 / 中止判据

- **通过**：单房间完整闭环（全部生命周期事件齐全、10 场终局全齐、结果覆盖完整、退出码 0、validate 通过、脱敏复核通过），且 §3 的 L1–L8 每项有实测证据消项。
- **中止并如实报告**：分类终态退出码 10、异常退出或任何结果缺失——保留全部证据，按 handoff §6 口径记录，不得记为通过；真实样本（SSE closed:true 等）缺失的继续诚实记录。

## 6. 执行命令（示意，Token 经环境变量）

```bash
export HM_AUTO_MATCH_TOKEN="<用户提供，不落盘>"
.venv/bin/python scripts/run_auto_match.py \
  --config configs/auto-match.example.json
```

运行期间审计 agent 并行：`.venv/bin/python scripts/audit_tool.py watch runs`；收尾后：`.venv/bin/python scripts/audit_tool.py validate runs/<run_id>`。
