# SSE 通知流客户端（notify.py）交付笔记

> 日期：2026-09-05  
> 任务线：SSE notify 客户端（任务 1/4）  
> 权威依据：指南 v14 全文 `doc/references/official-guide-v14-content.txt`（2026-09-05 抓取）与
> v12 变更记录 `doc/references/official-guide-version-v14.json`（2026-09-04）  
> 代码：`src/hangma_bot/adapters/official/notify.py`、`transport.py`（新增 `open_sse_stream`）  
> 测试：`tests/adapters/official/test_notify.py`（56 例，wv3 增补分类矩阵/毒化帧回归后；fake 流，无网络依赖）

## 0. 结论

- 交付一个**可用但不接入运行链路**的 SSE 通知流客户端 `SSENotifyClient`：Bearer 认证连接
  `GET /api/games/{id}/notify`，只解析/投递 `seq` 水位帧，closed 后按有界退避重连对齐，
  维护每用户本地并发预算，错误全部映射回 `errors.py` 现有分类体系。
- **运行行为零变化**：本模块不被任何运行链路（bootstrap/application/game/participant）引用，
  不改变既有 `/state` 长轮询路径；`transport.py` 只新增方法与带默认值字段，`request()`
  分类行为不变（官方适配器测试现 268 例全绿，wv6 口径）。
- **冻结契约零改动**：`WindowKey`、`ObservedActionWindow`、`TournamentSessionPort`、
  `GameSessionPort`、`BotPolicy`、`AuditSink` 公共签名均未触碰（§6）。

## 1. 官方协议要点与实现摘录（逐条出处）

出处缩写：**[v12]** = `official-guide-version-v14.json` 的 v12 added 条目（2026-09-04）；
**[v14]** = `official-guide-v14-content.txt`（2026-09-05 抓取）；**[实测]** = 2026-09 官方
测试环境实测事实（任务书给定）。

| # | 协议要点（官方原文摘录） | 出处 | 本模块实现点 |
| --- | --- | --- | --- |
| 1 | `GET /api/games/{id}/notify`，Bearer token 认证，非参赛者 403 | [v12] | `open_sse_stream` 复用 `OfficialTransport` 的认证注入与 TLS 白名单语义；403 → `ForbiddenError` → 终态 |
| 2 | 连接即收初始帧 `{"seq":N}`——N = 当前事件水位，**重连对齐点** | [v12][v14] | 每个连接的首帧即对齐水位，投递给回调并记入 `initial_watermark`；重连后新连接首帧重新对齐 |
| 3 | 每次状态变更（出牌/摸牌/吃/碰/杠/胡/流局/超时等）推 `{"seq":新水位}`，与 `/state` 同一全局递增水位 | [v14] | 逐帧投递；客户端不维护游标、不解析牌面（§3） |
| 4 | 每 30s 一行 `: keepalive` 注释维持连接 | [v12][v14] | 注释行一律忽略；传输读超时 `sse_read_timeout_sec=75s`（2 周期 + 余量），静默超时 → `UncertainTransportError` → 有界重连 |
| 5 | 流终止（场终/死场/慢消费者断流）推 `{"seq":N,"closed":true}` 后关流；closed 后客户端应重连（初始帧对齐）或按需拉终态 | [v12] | closed 帧投递后收尾，按有界退避重连；EOF 无 closed 帧 → `UncertainTransportError("sse:eof_without_closed_frame")` → 重连 |
| 6 | 帧只含 seq——不含牌面/动作/变化内容；牌面仍须按需 `GET /state` 领取 | [v12][v14] | 解析只取 `seq`/布尔 `closed`，未知键一律忽略；回调与审计只携带 `seq`，绝不解析任何牌面信息 |
| 7 | **游标纪律**：`/state` 的 `seq` 参数语义 =「N 之后的事件」；游标永远是**本地已消费 seq**；初始帧的 seq 是**包含式水位**（服务器已发到 N），不可直接当轮询游标（直接传会跳过 N 之前全部事件）；游标未知/落后超水位（>256）/跨局 → `seq=0` 全量快照 | [v12][v14] | 客户端只投递水位、**不维护游标**；集成契约见 §4（游标纪律归同步工作线） |
| 8 | 每用户 32 并发连接上限（超限 429）；不占 `/state` 的 16/s 频率额度 | [v12][v14] | `StreamBudget` 本地并发预算：默认 24 = 官方 M 上限 16 场 × 1 流 + 8 余量，可配置 1..32；超预算不连接；429 → `RateLimitedError`（退避 ≥ `Retry-After`） |
| 9 | 空转期（registering/stage_open/stage_done）没有 SSE 流可挂——SSE 只存在于局内 | [v13 附注] | 集成注意：notify 只覆盖 running 局内变化信号，空转期仍靠 `/api/tournaments/{id}` 轮询满足 90s 在线要求 |
| 10 | 已完赛场对该路由返回 404 `GAME_NOT_FOUND`（非 401/403）——参赛者 Bearer Token 能通过认证层 | [实测] | 404 → `NotFoundError` → 终态：closed 后重连遇到 404 即自然收尾（终态语义的设计依据，§2） |

## 2. 交付范围与运行影响

- **新增** `notify.py`：`SSENotifyClient`、`NotifyFrame`、`parse_notify_frame`、
  `StreamBudget`、`NotifyStreamConfig`、`NotifyRunResult`、`NotifyEndKind`、
  `NotifyStreamEvent`、常量 `OFFICIAL_SSE_CONCURRENT_LIMIT=32`/`DEFAULT_LOCAL_STREAM_BUDGET=24`。
- **修改** `transport.py`：新增 `TransportConfig.sse_read_timeout_sec=75.0`（带默认值，非破坏）；
  新增 `OfficialTransport.open_sse_stream()`（异步上下文管理器，逐行产出流）；错误分类抽取为
  私有 `_classify_error()`（`request()` 与流路径共用同一分类表，行为不变）。
- **不接入**：`__init__.py`、`game.py`、`sync_state.py`、`application/**`、`bootstrap.py`
  均未引用本模块；数据流不变，因此不更新 `doc/architecture.md`（接入运行时再同步）。
- 官方指南 §2.1 明示 v12 为可选能力（"旧 bot 无需改动；继续用长轮询 /state 不受影响"），
  故"不接入"不违反任何协议要求。

## 3. 设计

### 3.1 公开面

```python
class SSENotifyClient:
    """单个 game_id 的 SSE 通知流客户端。"""
    def __init__(self, game_id, transport, *, budget=None, on_frame=None,
                 on_event=None, config=None,
                 monotonic_clock=time.monotonic, sleep=asyncio.sleep): ...
    async def run(self) -> NotifyRunResult: ...   # 完整生命周期，封闭结果
    async def aclose(self) -> None: ...           # 优雅关停（幂等，之后不可复用）
    @property
    def budget(self) -> StreamBudget: ...         # 每 Token 共享的本地并发预算
```

- 帧回调 `on_frame(NotifyFrame)`：集成契约（§4）；观察者回调 `on_event(NotifyStreamEvent)`：
  诊断/审计钩子，只携带脱敏字段（`seq`、`attempt`、错误类名、退避秒数、终局分类），**绝不含
  行原文与 Token**；观察者异常只计数（`event_hook_errors`），不影响信号流。
- `run()` 官方分类错误绝不裸抛：`NotifyRunResult.kind ∈ {TERMINAL, RECONNECTS_EXHAUSTED,
  BUDGET_UNAVAILABLE, CANCELLED}`，`error` 携带分类后的 `OfficialError`（已脱敏）。
- 时间全部注入（`monotonic_clock`/`sleep`），测试不依赖真实等待（tests/AGENTS.md）。

### 3.2 生命周期状态机

箭头语义：`run()` 的控制流方向（实线=正常流转，虚线=错误/取消路径）。

```mermaid
flowchart TD
    A[run: 获取预算槽] -->|预算耗尽, budget_wait_sec 内无槽| BU[BUDGET_UNAVAILABLE: 未发起连接]
    A -->|持槽| C[连接 open_sse_stream]
    C -->|401/403/404/400/409/其他官方错误| T[TERMINAL: 不重连]
    C -->|429/可恢复5xx/断连/超时/EOF/帧解析失败| R{重连次数 < max_reconnects?}
    C -->|初始帧/变更帧| D[投递 on_frame: 水位 seq]
    D -->|closed:true| R
    R -->|是, 退避 max(指数退避, Retry-After)| C2[重连: 新连接初始帧重新对齐水位]
    R -->|否| E[RECONNECTS_EXHAUSTED: 可恢复失败, 调用方可稍后重开]
    C2 --> C
    A -.->|aclose 标志/强制取消| X[CANCELLED: 预算槽已归还]
```

要点：**失败流在断连前已投递的帧会并入终局统计**（`_StreamFailed` 携带 `_StreamStats`）——
慢消费者场景"收了若干帧才被踢掉"时，对齐水位与投递计数不因重连丢失。

### 3.3 错误分类映射（复用 errors.py，不改契约）

| 官方/传输事实 | 分类（现有体系） | 客户端处置 |
| --- | --- | --- |
| 401 | `AuthError` | 终态，不重连 |
| 403 / 404 / 400 / 409 / 其他官方错误 | `ForbiddenError` / `NotFoundError` / `BadRequestError` / `ConflictError` / `OfficialError` | 终态，不重连（404 `GAME_NOT_FOUND` 是完赛场自然终态，[实测]） |
| 429 | `RateLimitedError`（含 `retry_after`） | 可恢复；重连退避 ≥ `max(指数退避, retry_after)` |
| 断连 / 读超时 / EOF 无 closed 帧 | `UncertainTransportError` | 可恢复，有界重连 |
| 5xx | `RecoverableServerError` | 可恢复，有界重连 |
| 帧 JSON 非法/字段类型错 | `DtoError(recoverable=True)` | 可恢复，有界重连（持续解析失败提示版本漂移，集成层应回退长轮询并检查 guide/version） |

**不做无限自动重连**：`max_reconnects`（默认 5）次后返回 `RECONNECTS_EXHAUSTED`（可恢复失败），
调用方决定稍后重开或回退 `/state` 长轮询。耗尽后同一实例可再次 `run()`。

### 3.4 帧解析与脱敏边界

- 帧 = 单行 `data: {...}` JSON；SSE 注释行（含 `: keepalive`）忽略；空行分发事件；
  `data` 多行按 SSE 规范拼接（官方帧单行）；EOF 前未以空行结束的最后一条事件宽容解析。
- 只提取 `seq`（非负纯 int，拒绝 bool）与 `closed`（必须布尔）；**未知新增键一律忽略**
  （v12 后官方可能修订帧格式，前向兼容原则与 dto.py 一致）。
- 脱敏双保险：传输层对错误体做 Token 精确替换（与 `request()` 同边界），客户端所有
  detail 再过 `sanitize()`；回调/事件/结果只携带 `seq`，原始行文本从不离开 `notify.py`。
  测试含"帧与错误体回显 Token"用例（TestDesensitization）。

## 4. 集成契约（本模块只定义接口，不接入运行链路）

1. **帧到达 → 拉增量**：`on_frame(NotifyFrame)` 被调用后，集成层应以
   `GET /api/games/{id}/state?seq=<本地已消费游标>` 拉增量（快照/gap 语义不变，[v14]）。
   若 `seq` 不高于本地游标则丢帧即可（重复水位幂等）。
2. **初始帧警告（官方原文，必须遵守）**：初始帧的 `seq` 是**包含式水位**（服务器已发到 N），
   **不可直接当轮询游标**——直接传会跳过 N 之前全部事件；游标永远是**本地已消费 seq**；
   游标未知/落后超水位（>256）/跨局 → `seq=0` 拿全量快照起步。**游标纪律由同步工作线
   （sync_state）维护**，本客户端只投递水位、不维护游标。
3. **回调必须轻量**：`on_frame` 内只做唤醒/记录水位，不得同步拉取 `/state`（回调被
   await，慢回调会让读取滞后，触发服务端慢消费者断流 [v12]）；拉取由集成层另行调度。
4. **并发预算**：同 Token 各场共享一个 `StreamBudget`（默认 24 ≤ 官方 32 上限）；
   `run()` 返回 `BUDGET_UNAVAILABLE` 时不发起连接，由调用方选择等待
   （`budget_wait_sec` 配置）或回退长轮询。
5. **终态处置**：`TERMINAL`（401/403/404/…）→ 停止该场通知流；`RECONNECTS_EXHAUSTED` →
   可恢复失败，稍后重开或回退长轮询；`CANCELLED` → 正常关停。
6. **审计映射建议**（接入运行时执行）：`NotifyStreamEvent` → 现有 `AuditKind` 体系
   （如 `AUTHORITATIVE_STATE` 附 `notify` 事实或新增可选 kind），进入记录接口前已脱敏；
   本模块不直接依赖 `AuditSink`，避免给适配器增加新接缝。
7. **注意**：notify 只存在于局内（[v13]）；空转期在线要求（90s 内有已认证请求）仍由既有
   锦标赛轮询满足，不能用 notify 替代。

## 5. 测试清单（tests/adapters/official/test_notify.py，48 例，fake 流无网络）

| 场景 | 用例 |
| --- | --- |
| happy path | 初始帧+变更帧+keepalive 注释忽略+closed 帧；404 后终态；认证头/路径断言 |
| closed→重连对齐 | closed 帧收尾→重连→新流初始帧（seq=9）作为新对齐水位；EOF 断连分类 |
| 慢消费者断连 | 流中断连（ReadError）→ 可恢复 → 重连；退避时钟推进断言 |
| 429 退避 | `Retry-After=2.5` 时退避 2.5s（≥ 指数退避 0.5）；事件携带 RateLimitedError 分类 |
| 预算 | 预算耗尽零连接（open_count==0）+ 等待模式（释放后获得槽）；校验 1..32 边界 |
| 认证失败终态 | 401 → TERMINAL、零重连、零退避等待 |
| 有界重连耗尽 | 连续 EOF×3 → RECONNECTS_EXHAUSTED（可恢复失败），时钟 = 0.5+1.0；耗尽后可重开 |
| 帧解析 | seq/closed 校验、未知键前向兼容、坏 JSON/负 seq/bool seq 拒绝 |
| 脱敏 | 帧与错误体回显 Token → 回调/事件/结果/异常串均无 Token |
| 回调与守卫 | 回调异常传播且预算槽归还；并发 run 拒绝；aclose 后不可复用 |
| 关停/取消 | 优雅 aclose → CANCELLED（保留水位统计）；阻塞读强制取消 → CANCELLED；外部 cancel → CancelledError 传播且槽归还 |
| 传输层 | open_sse_stream 逐行产出、401/429/404 分类、Retry-After 解析、断连→Uncertain、错误体脱敏、sse_read_timeout 默认值 |

测试只通过公开接口验证行为（tests/AGENTS.md）；假流用真实 `OfficialTransport` +
`httpx.MockTransport` 构造，时间注入假时钟。

## 6. 冻结契约遵守与变更建议

- 未改动任何冻结契约；`TransportConfig` 新增字段带默认值、`OfficialTransport` 只增方法，
  均属非破坏性新增（`TransportConfig` 不在冻结清单内）。
- **无契约变更建议**。若未来接入运行链路，建议评审点：是否把 notify 生命周期事件纳入
  `AuditKind` 正式词表（可选新增，非破坏）；是否让 `OfficialGameSession` 暴露"notify
  可选通道"接缝（现有接缝纪律：至少两个真实实现才加接缝，当前不满足）。

## 7. 遗留风险与待确认假设

- **待确认假设（协议）**：官方 SSE 帧以空行分隔事件（标准 SSE）；若官方实现为无空行的
  连续 `data:` 行，本客户端的宽容路径（EOF flush）可解析最后一条，但中途连续帧会拼接失败
  触发重连——需官方测试房间实测帧的字节形态。
- **待确认假设（行为）**：closed 后重连的实际响应（预期 404 终态或直接断连）尚未在官方环境
  实测；404→终态的设计依据是任务书给定的实测事实。
- **工程建议**：`sse_read_timeout_sec=75` 基于"keepalive 30s"假设；若官方调整 keepalive
  周期需同步重校。慢消费者断连的服务端阈值官方未文档化，客户端不做速率自适应。
- **当前观察**：本地预算默认 24 是工程取值（M 上限 16 + 余量 8），非官方要求；接入时可
  按实际 M 与余量调整（上限 32 为硬约束）。
- **无关并行失败记录**：全套件 1181 passed / 6 failed，6 例失败均在
  `tests/integration/test_assembled_gates.py`（`validate_run` 的 `audit_complete=False`），
  属 recording 验证器并行改动，与本任务文件无引用关系（本任务测试与官方适配器测试全绿）。
