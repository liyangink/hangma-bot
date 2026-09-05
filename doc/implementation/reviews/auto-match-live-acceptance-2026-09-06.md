# 自由赛自动匹配真实房验收报告（2026-09-06）

> 对应计划：`doc/implementation/notes/auto-match-live-acceptance.md`；实现交付：`doc/implementation/handoffs/free-match.md`。
> 运行证据：`runs/runs/run-e5091d72997b41d69b8a726ebdb1444a`（恢复段）与 `runs/runs/run-06d896dd90a74d62b24b06eb1a78bd05`（发现段）。

## 1. 结论

单自动房完整闭环**通过**：匹配入席 → 运行 10 场并发 → 10/10 终局全覆盖 → 退出码 0（`tournament_finished`）。审计 validate `audit_complete=true`、0 violations、无 Token/Authorization 泄漏。

活场首验暴露并修复了一个设计假设错误（自动房无 `/rules` 端点），详见 §3。

## 2. 运行事实

| 项 | 事实 |
| --- | --- |
| 发现段 | `POST /api/match` 200，入席房间 `a_cd5c88f494b2`；随后核验 `/rules` 404 按保守语义 `matching_unavailable` 退出（设计预期内、证据充分） |
| 恢复段 | 以 `expected_tournament_id=a_cd5c88f494b2` 重启（零 match），接管 10 场进行中对局直至房间 finished |
| 时长 | 接管后 running t+0 → 10 场全部终局 t+195~396s → draining/finished t+396s 退出 |
| 退出 | 退出码 0；RESULT `terminal_reason=tournament_finished`；审计 written=14683，0 丢失/序列化失败/降级 |

## 3. 活场发现与代码修复（本次验收的核心产出）

**F-live-1（已修复）**：自动房没有 `/api/tournaments/{room}/rules` 端点——实测 `404 NOT_FOUND "bad path"`；房间详情响应内嵌完整 `config` 块（与 rules 响应同构，`Kind=auto` 在 `config.Kind`，顶层无 `kind`）。

修复：`src/hangma_bot/adapters/official/auto_match.py` 核验链改为单一详情请求——配置取自详情内嵌 `config`，不再请求 `/rules`；kind 读 `config.Kind`。新增活场回归测试（`/rules` 全程零请求 + 时限解析断言），全量 1417 passed / 0 failed。

## 4. 运行中验证项消项（L1–L8）

| # | 结论 | 证据 |
| --- | --- | --- |
| L1 | ✅ match 响应真实形态 | `{room_id, config{M:10,Rounds:8,BaseScore:1,Kind:auto,StartAt,DiscardTimeoutSec:3,PengTimeoutSec:1,ChiTimeoutSec:1,OnlineConfirm:false}, round_no:1}`；脱敏原文 fixture SHA-256 `949af43e…977946`（`raw/global.jsonl`） |
| L2 | ✅ kind 真实形态 | `kind` 位于详情 `config.Kind="auto"`（顶层无该字段）；≠auto 分支有测试锁定 |
| L3 | ✅ rules 可达性 | 自动房无 `/rules`（404 bad path）——已按真实形态修正核验链（§3） |
| L4 | ◐ 等待期 | 本次匹配即入席（房间已开赛，ready_users=4），未观察到等待期 status 序列；等待→running 转换在恢复段观察到 |
| L5 | ✅ 窗口节奏 | 982 决策窗口全部稳定提交：提交延迟 p50=62ms / p95=180ms / p99=604ms / max=955ms（<1s 吃碰窗口）；ambiguous=0、not_sent=0、超时代打=0；seq 缺口重建 38 次、409 冲突刷新 17 次（rejected_closed 17 + rejected_no_refresh 2，零盲目重发）；b8 一次 get_exhausted → 自动重开会话续打 |
| L6 | ✅ match 配额 | 全流程仅发现段 1 次 `POST /api/match`；恢复段零 match；60s/10 次滑窗与 6s 间隔未被触发上限 |
| L7 | ✅ SSE 真实行为 | 7 次 `sse_degraded`：SSE 断连重连耗尽后自动降级长轮询并继续对局（b0/b6 等场实测）；未捕获 `closed:true` 终态帧（房间 finished 走状态轮询，继续留待观察） |
| L8 | ✅ 隔离 | 全程 register/ready HTTP 调用 = 0（审计零记录） |

## 5. 收尾验证（C1–C5）

| # | 结论 | 证据 |
| --- | --- | --- |
| C1 | ✅ 终局覆盖 | 10/10 场 `GAME_FINISHED`（双层记录 20 条：适配器 `seq` + 应用层 `authoritative_seq`，审计 schema 明示的常态）；`drain_missing_finals`=0 |
| C2 | ✅ 关闭时间线 | 房间 finished 后进程按设计退出；实测房间在 finished + ~112s（101.5s~111.6s 之间）关闭为 404（官方文档“约 60s”为近似值，实测约 110s） |
| C3 | ✅ 退出语义 | 退出码 0、`tournament_finished`、RESULT 行含 run_id/脱敏身份前缀 `u_13*`；无 finished 证据的 404 路径未被触发（本房全程有证据） |
| C4 | ✅ 结果留存 | 关闭报告（本文件）+ 全量审计（14683 条）+ `audit_tool validate`：`audit_complete=true`、findings=[]、violations=0 |
| C5 | ✅ 脱敏 | 运行目录全文扫描：`Authorization`/`Bearer` 出现 0 次；raw 端点为 `GET/POST [REDACTED]` 形态 |

## 6. 牌谱下载能力确认（2026-09-06 实测）

**自动房沿用测试房间的免认证赛后下载端点**，可拉取完整对战事件流：

- `GET /api/test-rooms/{room_id}/games` → 200（10 个 batch，全部 finished）；
- `GET /api/test-rooms/{room_id}/games/{batch}/events` → 200（`blocks` 含四家 `start_hands`、逐事件流；`rounds` 局结果；`seats` 四身份）。
- 门户侧 `GET /portal/api/games/{game_id}/events` 需要门户登录态（我们的 API Token 返回 401 login required），不适用。

已把 10 场完整牌谱拉取存档：`runs/auto-match-download-a_cd5c88f494b2/`（1.8MB；`official/<dl-id>/{games.json,events.json,source.json}` 布局与审计线 `collect-test-room` 一致；各 events.json SHA-256 见目录清单）。后续审计线 `create_bundle` + `convert` 可直接产出统一牌谱数据集。

> 记录：自由赛（自动匹配房）此后可作为**高质量的牌谱来源**——完整四家事件流、真实对手、标准 M=10/Rounds=8。注意它无法替代可控同牌山评估（对手与牌墙不可控），三环境（测试房/测试赛/自动房）仍然不可互相替代。

## 7. 遗留与后续

1. `audit_tool validate` 显示 `audit_plus.profile=legacy`：**已修复（代码级）**——`auto_match_runtime.py` 的 RUN_MANIFEST 现已通过共享助手 `_audit_plus_manifest_fields` 声明 `capture_profile=audit-plus-v1`/`audit_producer=application`/`source_namespace`（审计线反馈后由主审补齐，回归测试锁定；全量 1417 passed）。本次历史运行目录保持不变（legacy 属实）；下一次自动房运行将以 audit-plus 口径正式校验。
2. 等待期 status 取值序列与长期不满房的平台行为仍未实测（L4）。
3. SSE `closed:true` 真实终态帧仍未捕获（L7 部分）。
4. 结果排名未做策略层解读（超出本验收范围；结果覆盖已留存，供评估线消费）。
5. 下载走免认证端点、房关闭后可能被删除：**赛后应尽快拉取**；`audit_tool collect-test-room` 对自动房同样可用，但需处理内网 TLS 校验（现脚本用 urllib 未带 verify 关闭）与命令命名的 test-room 语义。

## 8. 修复后复验（同日第二轮：run-6a7f079efd9b4e11b62390fc9414b417）

| 项 | 结果 |
| --- | --- |
| 完整闭环 | ✅ 匹配入席 → running → 10/10 终局 → draining → finished → 退出码 0（`tournament_finished`），审计 48305 条 0 降级 |
| 修复复验 | ✅ 终态事件单次发射（`participant_finished`×1、无重复 `matching_stopped`）；✅ manifest 携带 `capture_profile=audit-plus-v1`，`audit_tool validate` 以 audit-plus-v1 口径正式校验：`tail_complete=true`、`decisions_with_input==decisions_ended==2361`、`producer_failure_records=0` |
| 窗口节奏 | ✅ 2361 决策：accepted 4652 / rejected_closed 68 / rejected_no_refresh 2；ambiguous=0、not_sent=0、超时代打=0；延迟 p50=63ms / p95=167ms / p99=396ms / max=849ms（<1s 吃碰窗口） |
| 恢复路径 | ✅ 124 次 seq 缺口重建、34 次 409 刷新、9 次 SSE 降级自动续打，全部按契约处理 |
| 脱敏 | ✅ 目录全文扫描 Authorization/Bearer 命中 0 |
| 牌谱 | ✅ 10 场完整事件流已下载：`runs/auto-match-download-a_fb47fc10cd1a/`（全部 status=finished、含四家 start_hands） |

### 本轮新发现并已修复（2 项）

1. 终态事件双层重复：适配器与应用层各自发射 matching_stopped / PARTICIPANT_FINISHED → 按接口协议口径改为应用层唯一发射，适配器只返回终态值；双向回归测试锁定，本复验实测单次。
2. 预身份记录信封不完整：身份发现前的 4 条记录（matching_started/matched/初始化权威状态/match 原文）tournament_id 为空串，audit-plus 校验器判 malformed_record → 占位改为 unknown（与 participant_id 同一约定），代码已修复、全量 1426 passed；历史运行目录按事实保留。

### 平台行为观察（不属我方缺陷）

- 第三轮运行中（a_b74eb4bd9136）恰逢服务端发布重启：平台把 10 场对局全部置为 abandoned 并删除房间。我方表现为有界重开会话 + 无 finished 证据时诚实退出（matching_unavailable、不伪造），重赛后第四轮完整完成。
- 等待期房间（status=registering）未满员会被平台作废（/api/test-rooms/{id}/games 返回 status=void）；能否完整跑房取决于平台凑满 4 人，一次落到将作废的房时重跑即可。
