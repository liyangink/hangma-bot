# 自由赛自动匹配接入开工指南

> 负责人：自由赛线；分支建议 `codex/auto-match-v1`。用户已确认入口为 `POST /api/match`。本文件是待实现设计，不表示已接入或已开始参赛。

## 1. 已确认协议与首版范围

依据为本机[官方 API §2.6](../official-platform-api-v2.md#26-自动匹配post-apimatchv12-起v13-全自动语义v15-默认配置上调)、[v15 指南快照](../references/official-guide-v15.txt)，抓取日期 2026-09-05。真实新响应仍需实施者留存 fixture；不依赖臆测端点。

| 事实 | 接入约束 |
| --- | --- |
| 仅全局 Token 可调用 match | 已有赛事入口保持原作用域检查；新增显式 auto_match 入口，不把所有全局 Token 放行到旧赛事流程 |
| 返回 room_id/config/round_no，等待期重复 match 幂等 | 响应 room_id 才是本次目标；该 round_no 保持原文，不当成单局号 |
| 默认 M=10、Rounds=8；请求 M/Rounds 为可承受上限 | 首版声明机器实际能力；不能把 M=2 当成要求平台建 M=2 房，也不偷偷删除上限绕过资源不足 |
| 只通过 match 入席，register/ready 返回 AUTO_MATCH_ONLY | 应用层用专用生命周期，绝不执行原 register→ready 分支 |
| match 10 次/分/用户；自动房占 M 格，全局上限 16 | 所有请求共享同 Token 调度资源；不为每个新房另起无限配额 |
| finished 后约 60 秒关闭，之后房间玩家接口 404 | 参赛过程中保存终局与积分；404 本身不能证明正常完赛 |
| 自由对战排行榜是门户 session 接口 | 首版不接门户认证；只记录玩家接口实际返回的赛事事实和可见积分 |

首版一个进程、一个全局 Token、一次自动房会话；默认完成后退出。先交付稳定单会话，再选做多会话循环，循环次数必须有限且保存配置。它是采集不同对手行为和验证可靠性的入口，不能作为可控同牌山评估器。

## 2. 最小实现与接缝

新增 `OfficialAutoMatchSession`，作为现有 `TournamentSessionPort` 的第二个真实实现；继续复用 GameSessionPort、BotPolicy、AuditSink。不为单个 match 端点增加新 Port，也不让 application 导入具体 HTTP 客户端。

`initialize` 负责版本/全局身份检查及一次匹配操作的协议交互，返回已有 SessionBootstrap；可以对同一次操作做有界的协议级恢复，但不能在适配器内循环参加下一间房。`next_update` 对 finished/closed/void 返回目标房普通权威快照，由 application 判定终态，协议/身份错误才返回分类故障；`open_game` 复用现有 OfficialGameSession 和 SSE。`register/ready` 在本实现中本地拒绝调用且 HTTP 请求为 0；正常调用方不走这两个方法。

这是对原 initialize“只发现、无入席副作用”的**显式条件化变更**，已登记在共同契约 §3.3；不能漏改接口文档、SessionBootstrap 注释与契约测试。只有显式 auto_match 且目标为空、已排除已有自动房归属时允许 POST match；恢复非空目标不调用 match。application 控制是否开始这一次操作，适配器在配置预算内处理该操作的协议重试；返回分类终态后 application 关闭，不自动重新 initialize。这样保留四个接口，同时把新增副作用限定到用户选择的运行模式。

由自由赛线提出、主审集中合入的最小受控类型扩展：

- `RuntimeMode.AUTO_MATCH="auto_match"`；旧三种模式含义不变。
- 该模式的 RuntimeTarget.expected_tournament_id 允许空字符串，表示尚未发现目标；其他模式仍必须指定目标。非空表示只恢复该已知自动房，不创建新房。未发现的空值不能进入 URL 或假造官方 ID。
- 初始化成功后的 SessionBootstrap 和后续 TournamentSnapshot 一律使用经确认的非空 room_id/participant_id/config，且核对 kind=auto 和本人入席事实。
- 为初始化停止增加明确的参赛者终态原因 `MATCHING_UNAVAILABLE`（暂不可匹配或恢复证据不足）和 `CAPACITY_LIMIT`（资源上限）；不误标淘汰、鉴权失败或正常完赛。调用方保存 detail/官方错误码，正常关闭；首版不自动无期限重试。

application 新增 `AutoMatchRuntime`，只处理初始化、等待开赛、运行 active_games、收尾退出；复用 GameTask/DecisionLoop 和既有预算。自动房的 my_games 与 `/api/me.active_games` 交集是本进程可运行集合，不能误接全局 Token 所属其他赛事的场次。返回多于 config.M 或目标不匹配时显式诊断。

组合根新增 `build_auto_match_runtime`，创建并注入同一 Token 的 transport、scheduler、StreamBudget 和 audit。相关业务选择不写到脚本或 recording。当前 OfficialTournamentSession 内创建 transport 的既有实现无需为本线大重构；新实现的资源从组合根注入，不复制 ActionGate/序号恢复/SSE 状态机。

## 3. 生命周期与错误分支

先完成一个房间的闭环；接口错误、身份错误和结果缺失分别记录。

| 状态/事件 | 行为 |
| --- | --- |
| 启动 | 校验 v15 兼容、全局 Token、声明上限，查询身份及当前归属；有已确认活动自动房则恢复，不能另占新席 |
| 无现有自动房 | 调用 match 一次，保存原文、请求上限和返回 config；客户端声明不足时停止，不能假设只开本地能处理的少数场 |
| 等待开赛 | 轮询目标房；没有 active_games 继续等，别调用 ready；不反复 POST match 当作保活 |
| 运行 | 按 active_games 建立/回收场次，SSE 只唤醒状态同步；同场最多一个在途动作 POST，沿用修复后的窗口规则 |
| 各场结束 | 当场立即保存最终 /state、GAME_FINISHED、积分和 seq；不能等整房关闭后再补抓 |
| 房间 finished | 在宽限内汇总已有结果，记录缺失；不等待门户页面或全量下载才能关闭本地记录器 |
| 只有 404 | 若已有权威 finished/终局证据则按已有证据收尾；否则标结果缺失/未知，不能全记零分或 complete |
| 停止/取消 | 在途动作沿用结果不确定契约；保存局部证据和关闭状态，不假造已完成牌谱 |

协议失败处理：

- `NO_ROOM_AVAILABLE`：显式 M/Rounds 低于已确认服务默认值是永久容量不符；其他可能的建房后入席失败，只有官方错误内容/后续权威响应支持时才有限重试，无法分类就保留原文并停止。不能将所有 404 永久化或全部循环重试。
- `MATCH_BUSY`：有界等待后重试同次匹配；请求间隔至少覆盖 10 次/分钟限制（实现采用滑动窗口配额，并留余量），遵守 Retry-After。原有每秒限速器不能替代每分钟配额。
- `MATCH_LIMIT_REACHED`：停止新增入席，报告已有占用与容量；首版退出为 CAPACITY_LIMIT，不帮用户退出其他赛事。
- 401/错误 Token 作用域/未知 breaking 版本：分类停止，不轮换凭证。
- POST match 超时：等待期幂等不代表运行期也可盲目重发。先查身份和已知目标归属；无法确定是否已入席就结束为 MATCHING_UNAVAILABLE 并保留恢复信息。下次显式以已知 room_id 恢复，禁止凭 game_id 字符串格式猜房间。

同一个全局 Token 由一个节点的一个进程拥有；多节点使用不同 Token。首版不用分布式锁，但运行说明必须明确这项部署约束，启动时发现相互冲突的归属要停止并记录。

## 4. 与审计和评估的连接

使用现有 v1 AuditSink。生命周期以 `LIFECYCLE_CHANGED(area=auto_match)` 保存事件：`matching_started/matched/waiting/running/draining/finished/matching_stopped`；必要恢复沿用 PROTOCOL_RECOVERED，附 room_id、官方错误码、重试次数和等待秒数，未知字段为空。初始化前使用已有启动占位身份，发现后由组合根更新上下文，不能重写早先记录。

raw 增加 `source=match_response`，沿用 raw payload1 的 `endpoint/http_status/raw`，可选附客户端本地请求编号及请求上限；完整响应脱敏保留，不让 Token 入包。builder/validator 的来源登记由审计线在共享小提交提供；自由赛开发可在测试中使用固定响应，不需要等待完整审计增强。首个联合运行必须已合入该登记。

结果交给审计转换和评估汇总；本线不生产另一套牌谱/统计代码。自动房下载能力未确认，只标 observed；若以后确认新接口，新增 adapters/official 的下载支持与 fixture，再由审计线提升相应覆盖，不能预设测试房间下载可用。

## 5. 文件、配置和验收

| 文件 | 本线职责 |
| --- | --- |
| src/hangma_bot/adapters/official/auto_match.py | 匹配 DTO、错误分类、OfficialAutoMatchSession；复用既有 transport/scheduler/game |
| src/hangma_bot/application/auto_match_runtime.py | 自动房专用生命周期、并发场次与收尾 |
| scripts/run_auto_match.py | 只解析配置并调用组合根；不含状态机 |
| tests/adapters/official/test_auto_match*.py；tests/unit/application/test_auto_match*.py | 匹配/恢复/收尾/隔离与无 ready 的行为测试 |
| application/contracts.py 中 RuntimeMode/RuntimeTarget/ParticipantTerminalReason；bootstrap.py；公共导出 | 主审集成受控差异；不要修改审计枚举区域或旧 participant runtime |

配置至少包括显式 mode、known_guide_version、source_namespace、全局 Token 的集中配置引用、可承受 M/Rounds、可选已知 room_id、匹配重试次数/等待上限秒、SSE 开关、审计目录；默认只完成一个自动房。Token 绝不作为命令行参数或日志内容。超时、资源和数据收尾阈值归配置并写入脱敏 manifest。

先完成 Fake/fixture 验收：Token 范围错误、等待幂等、超时归属恢复、永久容量不符、忙/限流、全局其他赛事隔离、10 场并发、乱序/缺口/SSE 降级、finished 后 404、未取终局先 404、取消及慢审计。确认所有 register/ready HTTP 调用数为 0。

集成后再用已授权配置进行一次实际自动房验收，保存匹配原文、全部场次列表、实际 M/Rounds、超时/自动动作/重复提交、结果覆盖和关闭报告。当前 M=2 的测试房间验收不能代替这里的 M=10 验收；SSE closed:true 真实样本尚缺的项目继续诚实记录。交付 `handoffs/free-match.md`，主审统一集成入口。
