# `adapters/official` 模块实施规范

## 目标与边界

本模块实现 `TournamentSessionPort` 与 `GameSessionPort`，隐藏官方 HTTP、DTO、长轮询、序号恢复和非幂等动作状态。先阅读根规范、官方 API v8 记录、接口协议和 `doc/implementation/modules/official-adapter.md`。

- 每Token共享一个OfficialTransport及连接池；同一user_id的所有场次共享state滚动发送账，不再静态分配每场速率。`/state` 收到429时只让被拒查询按有效 `Retry-After` 与本地退避重排，其他桌继续按共享发送账领取额度，不冻结整个身份。每场保留独立HTTP槽（最多2个在途且state最多1个）、动作门和OTHER端点冷却；赛事控制通道的槽与OTHER冷却独立。不同用户的额度隔离。
- 四个测试 Token 之间不得共享认证头、限速状态、动作门或审计身份。
- 适配器只输出 `ObservedActionWindow`，只接收 `ActionAttempt`；禁止导入 `DecisionRequest`、`DecisionPlan` 或启发式评分类型。
- `StageIdentity.observed_revision` 只用于防止陈旧 `ready` 调用；应用层审计使用的 `stage_attempt_id` 不由适配器生成。
- `ActionGate` 和 `ProtocolSyncState` 是每场内部状态机，不暴露给应用层。
- 只支持配置中固定的官方内网主机关闭 TLS 校验，禁止全局关闭。
- Token 可由私有运行配置集中加载，但不得进入源码、fixture、异常文本或日志；所有 `Authorization` 必须脱敏。

## 同步和提交语义

- 2026-09-24 起，显式 `sse_enabled=true` 的验证模式以 `/notify` 通知水位触发短 `/state` 查询，不挂增量长轮询；流失效返回可恢复故障，不在同场切回长轮询。`last_seq` 只由权威 `/state` 推进，推断跳过帧后须从已消费游标补领并核对。未显式开启的旧配置仍使用既有长轮询。

- 重复 `seq` 幂等忽略；缺口、`gap=true`、未知关键事件和 409 使用 `seq=0` 权威快照整体重建。
- 未知但确认可忽略的兼容事件只记录，不触发重建风暴；未知关键事件才阻断并重建。
- GET 超时、可恢复 5xx 和 429 允许有界重试；动作 POST 不自动重放。
- 409 先确认官方已拒绝，再全量刷新：同一 `WindowKey` 仍需行动才返回 `SubmitRejectedRetryable`；窗口关闭则返回 `SubmitRejectedClosed`。
- POST 超时、断连或无法确定是否执行的响应返回 `SubmitAmbiguous`。相同 `WindowKey` 不得再次变为可提交状态，直到权威事件证明窗口已经迁移。
- POST 发出前检查 `latest_send_at_monotonic`；超过即返回 `SubmitNotSent`。
- state查询的最迟发起时刻与响应完成预算分开；已知窗口按最迟安全发起时刻排序，未知事件发现按场公平。有未来边界时只登记可取消的保护提示，到 `not_before_monotonic` 后才发送；提示不是第二个GET。
- 生产state先取得预占，真正进入传输前用 `mark_sent()` 记录本机单调发送时刻。未发取消退预占，已发后成功、失败、超时或取消均不退次数。
- 生产新建用户账时，首个state至少跨过一秒计数窗口；控制请求和POST无需等待。同进程重开场次不得清账或重复启动等待。
- peng→chi边界到点时取消并等待旧挂起GET回收，再领取本场state槽；同时完成时先消费已返回权威结果。过期旧窗口目的写审计并撤销，只保留必要的现状或下阶段同步，不积压历史请求。
- 认证、授权或不可恢复协议错误返回 `ParticipantTerminal`/`SubmitFatal`，不得伪装成可重试网络故障。

## 验收标准

- 官方 v8 保存响应 fixture 全部解析；允许兼容新增字段但拒绝未知破坏性指南版本。
- 同用户M场覆盖共享滚动16/s、`/state` 429仅被拒查询重排且其他桌继续服务、明确截止排序、未知发现公平及未来边界保护；各场HTTP槽和OTHER冷却、四个不同用户的额度保持隔离。
- 覆盖 `seq` 重复/缺口、`gap=true`、兼容未知事件、关键未知事件、409、429、401、超时和断连。
- 任意时刻每场最多一个在途 POST；模糊结果后同窗零次追加提交。
- `aclose()` 能取消最长 30 秒长轮询或 SSE 监听，且不误关同 Token 的其他场次。
- 状态投影测试证明官方 DTO 不泄漏他家手牌或未来信息。
- 最新已审查指南为 **v35**（2026-09-23 抓取；v35 的 breaking 处置见下文）：v24/v25/v29/v35 的 breaking 按调用路径及完整条目摘要放行，未知或被改写条目仍拦截。**v31—v34 共 4 条、0 条 breaking，但 v32/v33 属规则口径与决策窗口变更，已逐条评审并登记在 `dto.py`**：v31 局间固定停 5 秒，窗口内 `phase="settled"`、`round_no` 仍是刚结束那一局，单局迁移必须以 `round_no` 变化为准、不得依赖「一次 `seq=0` 必得新局」，完整桌赛墙钟约增加 `5 × Rounds` 秒；v32 杠爆判定改在杠动作时重算，不自行构造结算者零改动，本地引擎的爆头重算落在杠后补牌落地，已由 `test_action_chain_lifecycle` 固化；v33 杠后补牌停出决策窗口，与普通摸牌同构，主动判胡提交 `hu` 者零改动，但历史牌谱存在「补牌即可胡却无决策直接收束」的形态，离线重放必须容忍；v34 门户今日榜 `last` 垫底行，纯加法，仅 `period=today` 且上榜 >32 时非 null。v29 是全服功能开关：关闭自由匹配或自建测试房后，`POST /api/match` 新匹配与已完结 test 房「重开下一轮」（ready）返回**永久** 403 `FEATURE_DISABLED`（ready 路径此前是 409 房态类）。该错误码必须同时登记在 `errors.KNOWN_OFFICIAL_CODES` 白名单，否则会被 `sanitize_official_code` 置为 `None`，使针对它的分支**静默失效**。v30 把他人 `name` 收口为 AI 昵称、空则空串，本模块按 `user_id` 作稳定身份，零协议影响。解析 `god.god_discarder_seat` 并投影可空圈主事实，保留快照水位；旧报文缺失可兼容，有字段但畸形不能静默当缺失。规则解释统一交给 `hangma.catch_play`。

## 2026-09-08 调度修订边界

2026-09-23 指南 v35 将同为 HTTP 404 的赛事错误正式区分：`TOURNAMENT_GONE` 是房 actor 暂时不可达，详情 `GET /api/tournaments/{id}` 和规则 `GET /api/tournaments/me/rules` 按房轮询周期有界重读，耗尽仍保留暂态原码与结果未知；`TOURNAMENT_NOT_FOUND` 或缺失/未知 code 立即保守停止。不得按 HTTP 状态码或固定连续次数把前者判为目标错配。正式赛 `register`/`ready` 保留幂等重试；`/api/me` 和 `/api/match` 不进入此冷却。版本完整条目保存在 `doc/references/official-guide-version-v35.json`，只有内容摘要匹配才放行该 breaking 变更。

依据本日抓取的官方指南v25，每用户state上限为16/s；滚动实际发送账是本地保守实现，不能声称复刻未公开的服务器计次算法。四个外部端口和 `ActionAttempt` 字段不变，预算仍由应用层提供，策略不读取限频状态。2026-09-09普通弃牌缓发已默认接线：滚动state用量达到10次，正常摸牌增量有本机水位下界且余量足够时，补到保守起点后1秒。快照恢复、重试、白板和本人特殊动作链跳过。等待不占HTTP槽/查询额度；醒后复核窗口，并保留收紧的原始最迟发送时刻。等待取消用SubmissionCancelledBeforeSend穿透应用层并记未发送，不得记在途模糊结果。当时 SSE 保持关闭；当前验证模式见上文。方案与验收边界见[算法草案](../../../../review/adapter-rate-identity-2026-09-08/algorithm-design.md)及[实施验证](../../../../review/adapter-rate-identity-2026-09-08/implementation-validation.md)。

2026-09-23 实验版覆盖上述 2026-09-09 缓发触发条件：首次普通弃牌按本机见窗时刻至少等待 500 毫秒，队列拥堵时最多 1 秒；重试、特殊动作链及无安全截止余量时立即走原提交路径。不得借等待延长原始动作截止；醒后复核窗口。随机错峰尚未实现，M=10 实网完整桌赛门禁未通过，SSE 保持关闭。[换机接续](../../../../review/r18-four-arm-evaluation-2026-09-23/HANDOFF-2026-09-23.md)。

2026-09-24 测试房可显式关闭上述弃牌缓发，并试验同场普通增量长轮询的最短重挂间隔。查询立即入队，调度器按 `not_before_monotonic` 限定最早发起；`seq=0`、高优先级监听、已知期限、恢复查询，以及 `timeout/pass` 响应或动作提交后的首次查询均不加底档。50/120 毫秒两房已完成，尚未通过零合法漏窗门禁，见[试验记录](../../../../review/r18-four-arm-evaluation-2026-09-23/LIVE-R8-LONGPOLL-120MS-2026-09-24.md)。下一房实验档为普通查询 60 毫秒，普通弃牌从首次见到动作窗起至少 200 毫秒；同用户近 1.05 秒实际发起的状态请求已记满 8/16 时至少 500 毫秒。预算不足、重试和特殊动作仍立即提交。正式赛事和自由赛保持既有配置，实验效果须以完整四席房验收。

2026-09-09发送边界补充：生产`mark_sent(at)`由HTTP审计入口以同一次单调采样同步调用。state记录保留1.05秒，额外50ms为到达波动余量；官方上限仍是16/s，此余量不宣称覆盖网络长尾。详见[诊断](../../../../review/clock-rate-diagnosis-2026-09-09/README.md)。

2026-09-09期限映射：同用户共享 `snapshot-interval-v1`，由通过投影验证的当前phase、官方期限和对应GET单调起止时间约束；提交用早界、边界等待用晚界，不增加查询。样本不足/过期/冲突必须降级并留审计，不把区间估计视为精确同步或任意网络长尾保证。
