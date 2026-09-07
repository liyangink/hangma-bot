# 杭麻 AI Bot 架构与运行流程

2026-09-07 制品更新：运行审计推荐定位到 `artifacts/sessions/<session>/audit/`，四身份仍各自拥有记录器。完赛后 `audit_tool.py postgame` 调用 `offline.postgame` 封存证据、转换数据集，并复用唯一规则模块核验终局及观察转移，不进入线上主循环。下载归 `adapters.official.archive_download`，公开客户端由 `bootstrap` 装配；本机归并和旧布局恢复归 `offline.artifact_store`。冻结接口不变，缺失信息不补写到历史 `PlayerObservation`。路径和完整性边界见 [操作指引](operations.md)。

> 状态：当前目标架构 v0.5；第一阶段接口基线 v1.1（2026-09-04 集成阶段契约收口：`SubmitRejectedNoRefresh`、候选牌效事实 `CandidateFacts`、kernel 裁决与审计词表，见接口协议 §4.1/§5/§7.1/§10.1）  
> 更新日期：2026-09-04  
> 适用范围：官方测试房间、测试赛事、正式赛事，以及后续模拟、训练与评估  
> 关联资料：[接口协议](./implementation/interface-contracts.md)、[第一阶段验收](./implementation/mvp-acceptance.md)、[统一术语表](../UBIQUITOUS_LANGUAGE.md)、[官方赛事流程](./official-tournament-flow-2026-09-03.md)

## 1. 结论与图例

第一阶段把复杂度集中在六个确有必要的模块：稳定值类型、唯一杭麻规则、启发式策略、赛事运行编排、官方适配器和审计记录。模拟、训练、小型模型和复杂赛事效用保留为后续目标，但当前不创建空接口或让其进入线上依赖。

- 实线箭头表示运行时调用或数据传递，方向从调用方/来源指向被调用方/去向。
- 虚线箭头表示后续阶段的离线产物发布，不属于第一阶段或每次决策的必经路径。
- `adapters` 隔离网络和磁盘副作用；`hangma` 与 `policy` 不直接访问官方 HTTP。
- 真实运行只给策略[玩家观察（PlayerObservation）](../UBIQUITOUS_LANGUAGE.md#状态与信息权限)，不得给他家手牌、未来牌墙或赛后结果。

## 2. 场景边界与共享核心

箭头表示各场景使用同一生产核心；“后续”节点没有进入第一阶段代码路径。

```mermaid
flowchart LR
    subgraph REAL["场景 A｜官方真实运行"]
        PLATFORM["官方竞赛平台\n测试房间 / 测试赛事 / 正式赛事"]
        OFFICIAL["adapters/official\n协议、同步、提交"]
        APP["application\n生命周期、并发、截止时间"]
        RECORDING["adapters/recording\n非阻塞审计"]

        PLATFORM --> OFFICIAL
        OFFICIAL --> APP
        APP --> OFFICIAL
        APP --> RECORDING
        OFFICIAL --> RECORDING
    end

    subgraph MVP["第一阶段共享生产核心"]
        KERNEL["kernel\n稳定值对象"]
        HANGMA["hangma\n唯一规则来源"]
        POLICY["policy\n有序候选计划"]

        POLICY --> HANGMA
        HANGMA --> KERNEL
        POLICY --> KERNEL
    end

    APP --> HANGMA
    APP --> POLICY

    subgraph LATER["后续场景 B/C/D｜模拟、训练、评估"]
        SIM["simulation\n完整世界推进"]
        COMP["competition\n赛事效用"]
        LEARN["learning\n编码、小网络与模型产物"]
        OFFLINE["offline\n生成、训练、评估"]

        SIM --> HANGMA
        OFFLINE --> SIM
        OFFLINE --> COMP
        OFFLINE --> LEARN
        LEARN -.->|"通过门禁后加载"| POLICY
        COMP -.->|"后续策略使用"| POLICY
    end
```

### 2.1 三类官方环境

| 运行方式 | 身份与并发 | 第一阶段用途 | 不能替代 |
| --- | --- | --- | --- |
| 官方测试房间 | 一次 4 个 Token；每个身份按 `active_games` 运行最多 `config.M` 场 | API、杭麻规则差异、1/3 秒窗口、并发、恢复和赛后数据 | 完整多阶段生命周期或固定牌山策略 A/B |
| 官方测试赛事 | 赛事方提供测试身份；外显协议待实测固化 | 报名、到位、海选、阶段切换、淘汰/候补、重赛和终态 | 大样本策略显著性评估 |
| 正式赛事 | 一个正式 Token；同样按 `active_games` 运行最多 `M` 场 | 只运行通过门禁的稳定版本 | 训练或高风险实验 |

官方测试赛事已经提供，因此是第一阶段发布门禁。官方只确认赛后复盘能力时，本地运行审计是实时决策证据的主要来源；不能预设正式赛事存在未确认的牌谱下载端点。

## 3. 模块边界与依赖方向

箭头表示“调用方依赖被调用方”。适配器实现应用层定义的端口，因此源代码依赖方向从适配器指向应用契约；运行时数据仍从平台流向应用。

```mermaid
flowchart TB
    BOOT["bootstrap.py\n唯一组合根"]
    ENTRY["scripts\n单身份 / 四身份入口"]
    OFFICIAL2["adapters/official"]
    RECORDING2["adapters/recording"]
    APPLICATION["application\n端口与运行编排"]
    POLICY2["policy\nBotPolicy"]
    HANGMA2["hangma\nHangmaRules"]
    KERNEL2["kernel\n稳定值类型"]

    ENTRY --> BOOT
    BOOT --> OFFICIAL2
    BOOT --> RECORDING2
    BOOT --> APPLICATION
    BOOT --> POLICY2
    BOOT --> HANGMA2
    OFFICIAL2 --> APPLICATION
    OFFICIAL2 --> RECORDING2
    RECORDING2 --> APPLICATION
    APPLICATION --> POLICY2
    APPLICATION --> HANGMA2
    APPLICATION --> KERNEL2
    POLICY2 --> HANGMA2
    POLICY2 --> KERNEL2
    HANGMA2 --> KERNEL2
```

### 3.1 第一阶段模块表

| 模块 | 公开面 | 隐藏的复杂度 | 禁止承担 |
| --- | --- | --- | --- |
| `kernel` | 动作、窗口、观察、已观察赛事上下文、不可变配置 | 类型约束和稳定动作键 | 网络、规则算法、策略、完整世界 |
| `hangma` | `HangmaRules` | 合法动作、胡牌、向听、有效牌、财神和结算；独立紧急路径 | HTTP、磁盘、时钟、模型 |
| `policy` | `BotPolicy.choose()` | 启发式评分、有序候选和超时降级 | 声明动作合法、提交 HTTP、读取 `WorldState` |
| `application` | `ParticipantRuntime`；赛事/场次/审计端口 | 报名到位、参赛者终态、最多 `M` 场监督、预算和明确拒绝降级循环 | HTTP DTO、动作门、牌型算法 |
| `adapters/official` | 实现赛事和场次端口 | 已审查指南 v15（快照 2026-09-05；v13 在线分桌审查结论见 `doc/official-tournament-flow-2026-09-03.md` §6.6，v15 自动匹配零影响见 §6.7）、每 Token 传输/限速（state 轮询 16/s 每用户聚合）、状态投影、序号恢复（含 v10 跨局 gap 快照吸收）、动作门 | 组装决策请求、策略评分、赛事何时退出 |
| `adapters/recording` | 实现 `AuditSink` | 队列、JSONL、脱敏、汇总和验证 | 业务判断、重试和阻塞动作 |
| （上游依赖边） | `adapters/official → adapters/recording` | RAW_PROTOCOL_STATE 原始事件经 build_state_response_payload / build_action_response_payload 落审计（2026-09-05 起，errors.raw_text 载体语义见接口协议 §7.1） | — |
| `bootstrap.py` | 组装函数 | 具体实现选择和配置注入 | 规则、生命周期或协议逻辑 |

### 3.2 四个冻结接缝

只冻结：

1. `TournamentSessionPort`：官方会话与生命周期 Fake；
2. `GameSessionPort`：官方场次与保存响应驱动 Fake；
3. `BotPolicy`：加权启发式与紧急保底；
4. `AuditSink`：JSONL 与内存测试记录器。

`HangmaRules` 当前只有一个真实实现，不人为增加 Protocol。`OfficialTransport`、请求调度器、限速器、`ProtocolSyncState`、`ActionGate` 和 `StateProjector` 都是适配器内部细节。接口类型和兼容规则见[第一阶段接口协议](./implementation/interface-contracts.md)。

### 3.3 后续模块边界

MVP 后按实际任务创建目标模块。2026-09-05 的[并行契约](./implementation/parallel-contracts.md)已启动 simulation/offline 设计，详见[施工导航](./implementation/parallel-workstreams.md)；competition/learning 待具体能力进入时实现：

- `simulation` 拥有 `WorldState`，每一步调用 `hangma`，禁止第二套规则；
- `competition` 只把结构化阶段事实和可能结果转换为赛事效用，不读取 HTTP；
- `learning` 统一训练/推理编码、网络、校准和模型兼容性；
- `offline` 可以调用生产核心，线上代码不能反向依赖训练任务；
- 若线上确需模拟结果，只向策略提供深的 `OutcomeEstimator`，不得暴露 `WorldState` 或让策略直接操纵模拟器。

本批具体调用与文件契约见[parallel-v1](./implementation/parallel-contracts.md)。审计拥有原文整理与统一牌谱 codec；模拟拥有不透明 WorldState 和具体 SimulationEngine；评估只读文件并调用公开 frame/advance，策略仍仅消费 DecisionRequest。历史 check_hand 与完整世界 from_replay 分开；缺牌墙的官方记录不自动成为可分叉世界。

启发式后续施工按[三个候选版本计划](./implementation/policy-iteration-plan.md)：先可靠排序，再由 hangma 补齐 Pass 等待牌效，最后有限调参。V0/V1 源码保持冻结，线上默认 V0；hangma 已按本地语义 `hangma-mvp-v2-pass-progress` 提供响应 Pass 等待事实。组合根与离线装配使用显式旧视图保持 V0/claim_if_legal 的正常评分，审计仍记录原事实，V1 已兼容可信新事实。V2 以 `weighted_heuristic_v2` 接入原策略配置，复用 V1 非 Pass 评分并统一响应等待基准；策略接口和数据格式不扩展，策略不依赖离线评估器或模拟器。边界见接口协议 §4.3–4.4。

### 3.4 自动匹配入口（待实施）

用户已确认 `/api/match`。新增 OfficialAutoMatchSession 作为 TournamentSessionPort 的第二个真实实现，application 用专用自动房生命周期复用现有 GameTask/SSE/动作门。显式 AUTO_MATCH 初始化可有一次入席副作用；旧模式保持发现与 Token 作用域检查。匹配操作内协议重试归适配器，是否开始会话、运行场次、终局收尾归应用层，默认只完成一个自动房。详见[自由赛指南](./implementation/free-match-start.md)，不能把这段流程只归到可观测模块。

## 4. 赛事生命周期与终态

箭头表示官方赛事状态变化；组委会推进下一阶段属于平台外部行为，不是我方程序的人工参与。

```mermaid
stateDiagram-v2
    [*] --> registering
    registering --> running: Bot 幂等报名并到位，平台到点开赛
    running --> stage_done: 当前晋级阶段完成
    stage_done --> stage_open: 组委会推进下一阶段
    stage_open --> running: Bot 对合格身份幂等到位，平台冻结名单
    stage_open --> eliminated: qualified=false 或 NOT_QUALIFIED
    running --> running: 决赛同分，新增 game_id
    running --> stage_done: stage_crashed=true，旧尝试作废
    running --> finished: 官方赛事完成
    registering --> void
    stage_open --> void
    registering --> closed
    running --> closed
    stage_done --> closed
    stage_open --> closed
    eliminated --> [*]
    finished --> [*]
    void --> [*]
    closed --> [*]
```

必须区分两个概念：

- 赛事终态只有官方 `finished/closed/void`；
- 参赛者终态还包括当前身份被淘汰、认证失败、未知破坏性指南版本或目标赛事错配。

因此 `stage_open + qualified=false` 正常结束当前身份，但不宣称整场赛事已经结束。`active_games=[]`、`stage_done` 和 `stage_open` 都不是自动退出条件。每次进入 `running` 都重新发现 `active_games`；动态降档、重赛和决赛加赛可能出现新 `game_id`。

`stage_crashed=true` 时关闭旧场次任务，以 `stage_attempt_id` 标记作废记录，等待新尝试。旧尝试默认不进入训练标签或赛事效果统计。

## 5. 测试房间四身份与 `M` 场并发

箭头表示启动器创建子进程；每个子进程内部再按当前身份的 `active_games` 创建场次任务。

```mermaid
flowchart TB
    RUNNER["run_test_room.py\n只负责编排与汇总"]
    A["进程 A\nToken A / ParticipantRuntime"]
    B["进程 B\nToken B / ParticipantRuntime"]
    C["进程 C\nToken C / ParticipantRuntime"]
    D["进程 D\nToken D / ParticipantRuntime"]
    AM["0..M 个 GameSession"]
    BM["0..M 个 GameSession"]
    CM["0..M 个 GameSession"]
    DM["0..M 个 GameSession"]

    RUNNER --> A --> AM
    RUNNER --> B --> BM
    RUNNER --> C --> CM
    RUNNER --> D --> DM
```

`M` 不增加 Token 数。第一阶段固定采用四个进程，复用正式单身份入口；不做同进程多租户、共享模型或复杂资源编排。每个 Token 独立拥有 HTTP 连接池、请求调度器、限速器、动作门状态和身份审计目录。同一 Token 的赛事请求和最多 `M` 个场次共享其传输资源。

## 6. 一次真实动作窗口

箭头表示调用；409 分支可以在原截止时间内回到规则/策略，但任意时刻只有一个在途 POST。

```mermaid
sequenceDiagram
    participant P as 官方平台
    participant O as Official Adapter
    participant A as Application
    participant R as HangmaRules
    participant B as BotPolicy
    participant L as AuditSink

    P->>O: 权威快照或连续事件
    O->>O: 检查 seq/gap，必要时 seq=0 重建
    O-->>A: ObservedActionWindow
    A->>A: 创建一次 DecisionBudget 与 decision_id
    A->>R: emergency_action(observation)
    R-->>A: 紧急候选或 None
    A->>R: analyze(observation)
    R-->>A: RuleAnalysis
    A->>B: choose(DecisionRequest, DecisionBudget)
    B-->>A: DecisionPlan（完整有序候选）
    A->>R: validate(当前观察, 首个未拒绝动作)
    R-->>A: 合法 / 改用下一候选
    A->>L: SUBMISSION_INTENT（非阻塞）
    A->>O: ActionAttempt
    O->>P: 一个在途 POST action
    alt 明确成功
        P-->>O: 2xx ACK
        O-->>A: SubmitAccepted
    else 明确 409 拒绝
        P-->>O: 409
        O->>P: GET state?seq=0
        alt 同一窗口仍需我方行动
            O-->>A: SubmitRejectedRetryable + refreshed_window
            A->>A: 原预算、排除拒绝动作、plan revision + 1
        else 窗口已关闭
            O-->>A: SubmitRejectedClosed
        end
    else 结果无法确认
        O-->>A: SubmitAmbiguous
        O->>O: 封锁同一 WindowKey，等待权威迁移
    end
    A->>L: SUBMISSION_OUTCOME（非阻塞）
```

安全语义不是“每个窗口只发一次”，而是：

1. 同一场任意时刻最多一个在途动作 POST；
2. 只有官方明确确认未执行，并刷新确认同窗仍开放，才能换下一候选；
3. 409 后复用原预算，不能重新获得完整窗口；
4. 网络结果不确定时不追加动作；
5. 到保底截止时间使用已经准备的紧急候选，到最晚发送时间后不再 POST。

紧急路径为：响应窗口过；抓打圈打刚摸牌；普通出牌按官方保留顺序打最右一张。它是最终兜底，不代替第一阶段完整规则引擎。

## 7. 状态同步与请求资源

2026-09-06 修订：两个生产组合根固定使用 `state` 长轮询与阶段边界查询，SSE 暂不接入。应用层单场主循环驱动同步、规则分析、策略选择和串行提交，不新增后台同步任务。低层 SSE 客户端保留供以后评估，运行 manifest 记录 `official_sync_mode=state`、`sse_requested` 和 `sse_effective=false`。

每场适配器独立维护权威快照、`last_seq`、当前单局可见历史、当前窗口和动作门。快照更新牌面但保留已收历史；只有快照之后的事件更新牌面。`current_observation()` 是快照/增量投递及提交复核共用的观察入口。增量摸牌通过 `hangma` 按既有爆头和本次补牌来源推进生命周期；缺完整前态或来源会影响结果而未知时恢复快照。所有人的副露以及响应资格暂由必要快照确认，不能为减少 GET 交付残缺桌面。

同 Token 的全部场次共用 `/state` 滚动 16 次/秒额度，包括长轮询、恢复和补史；动作 POST、赛事查询不扣该专属额度。全部 HTTP 共用最多 32 个并发槽；state 429 只冷却 state，其他来源429保守全局冷却。生产入口按14次/秒、burst=1平滑发送state并保留余量，动作可越过state额度和state冷却等待，仍服从原截止时间；`/api/match` 另按 10 次/分钟管理。依据为[指南 v18，2026-09-06](../review/official-adapter/chain-rate-alignment/guide.txt)。修复只调整现有调度器，不增加异步任务。

`hangma` 拥有同一套动作生命周期：吃碰继承爆头但不新增链，杠加一次链并继承爆头，杠补牌可继承或新进入；弃牌先用旧状态判飘，再更新听牌态，其他弃牌清链。手留四白排除优先。模拟、牌谱和官方增量调用这套规则；官方快照中的 god 原样交付策略，规则核验只报告分歧。详细证据边界见[规则清单](../src/hangma_bot/hangma/RULES_EVIDENCE.md)。

- `seq <= last_seq`：载荷相同的已保存事件幂等忽略；同序号载荷冲突恢复，迟到旧快照不得让水位回退；
- 序号缺口或 `gap=true`：不应用部分增量，`seq=0` 整体重建；
- 兼容未知事件：记录后继续；
- 未知关键事件：阻断决策并整体重建；
- POST 409：明确拒绝后整体重建，再分类是否可重新规划；
- POST 超时/断连/结果不明：进入 `AMBIGUOUS`，不得传输层重放。

未知类型不会因一次恢复自动变成可忽略。跨单局/阶段可没有新序号，进展判断同时检查 `round_no/phase`。轮询与边界同时完成时先消费已返回事件，不能由计时器丢弃它。响应表态绑定触发弃牌；新弃牌即使通过快照直接进入响应阶段，也不能继承旧 pass。

`PlayerObservation` 保存快照基线 `snapshot_seq`、已消费水位 `consumed_seq`、历史完整性及可空的 `chain_piao/gang_draw`。链未知不填零，杠补来源未知不当普通摸牌。规则模块核验有完整前态的简单 god 转移，输出 `god_mismatch` 或 `not_checked`；当前事实仍服从官方快照。抓打圈四座位语义、碰阶段显式 pass 对后续吃资格仍待官方验证。

窗口将官方 Unix 毫秒截止转换为单调时钟截止；同一窗口只能收紧。应用预算扣留发送余量，409 新快照也只能收紧原预算。仅有增量事件时不得借用旧响应阶段截止，估计时间明确标记。部署时钟偏差和真实网络尾延迟仍需线上测量。

修订策略及评审：[观察完整性修复策略](../review/official-adapter/repair-plan-2026-09-06.md)。离线 `observation_check.compare_observations` 比较已独立对齐的观察和参考，分别报告状态/历史差异及未检查项；线上不依赖该工具。

每 Token 请求优先级：动作 POST > 同步/提交确认恢复 > 场次长轮询 > 排名刷新。这个调度器只在官方适配器存在；应用层只负责决策预算和任务监督。长轮询最长 30 秒，阶段切换、场次消失或退出时必须可取消。

## 8. 审计边界

MVP 后续增强设计见[审计增强实施方案](./implementation/audit-enhancement.md)（2026-09-05 修订，新增部分待实施）。保持 v1 信封、现行 raw 留存与 AuditSink 签名，以 profile 补齐完整决策输入、候选复核、结束证据和构造失败持久化。实际生成的候选/评分必须留存，不用修复后的规则重算值覆盖历史事实。

审计不是普通调试日志，而是第一阶段正式产物。应用层记录生命周期、规则分析、策略计划、提交 intent/outcome 和最终结果；官方适配器记录协议同步与恢复事实。双方只发送已脱敏的 `AuditRecord`。

原始事件全量保留（2026-09-05 起）：adapter 层全部协议原文（/state 响应、动作提交响应与 409/429 拒绝体）经低优先级 `RAW_PROTOCOL_STATE` 路由到按场分文件的 `raw/*.jsonl`（可选 gzip 分段，只分段不抽样）；决策计划（`DECISION_PLANNED`）携带观察快照（我方手牌/摸牌/相位/目标弃牌），任何被拒动作可本地复盘。词表与对账检查见接口协议 §7.1。摸牌窗口自当日起由增量事件直达（不再逐批全量刷新），口径见 doc/implementation/notes/cursor-discipline.md。

```text
runs/{run_id}/
  manifest.json
  lifecycle.jsonl
  participants/{participant_id}/
    decisions.jsonl
    games/{game_id}.jsonl
    summary.json
  summary.json
```

高优先级动作信封不设计为正常丢弃；磁盘问题导致缺失时运行必须标记 `audit_degraded`，不能继续声称完整可审计。低优先级协议原文可以在队列压力下计数丢弃。Token 和 `Authorization` 在进入记录器前移除，记录器再次防御性脱敏。

本批复用现有独有原文 RAW_PROTOCOL_STATE，低优先级背压丢失仍需计数，不能宣称原文完整。应用层提供决策编解码；官方适配器留存协议并映射赛后格式；记录模块负责文件、共用读取器、校验与封存；离线模块负责具体统一牌谱转换，线上不依赖离线模块。只读监控使用记录中的牌桌快照和决策，不维护第二套协议状态机或规则。

证据包包含互不改写的各进程运行目录、可取得的官方赛后原文和文件哈希。统一牌谱写入独立派生目录；测试房间完整事件流与测试赛事/自由赛玩家观察按数据能力区分。缺少未来牌墙时只声明完整历史轨迹，不声明完整世界或反事实分叉能力。实时排名按实际环境采集，缺失保留未知。

## 9. 模拟、训练与评估的后续边界

以下为长期数据边界。第一阶段已经完成，本批 simulation/offline 的具体接口和验收以 parallel-v1 为准；训练模块仍待相应阶段。箭头表示数据消费方向，教师和学生的信息权限不同：

```mermaid
flowchart LR
    subgraph SOURCE["数据来源"]
        AUDIT["本地权威运行审计"]
        OFFICIAL_RESULT["官方已确认的赛后复盘/结果"]
        SIM["后续本地模拟器\n固定 seed 与完整 WorldState"]
    end
    subgraph TRAIN["后续训练"]
        REBUILD["重建当时 PlayerObservation"]
        DATA["版本化样本"]
        MODEL["小型候选结果模型"]
    end
    subgraph EVAL["评估与发布"]
        LOCAL["同牌山、换座位、大样本"]
        ROOM["官方测试房间"]
        TOUR["官方测试赛事"]
        GATE["统计/可靠性门禁 + 人工审核"]
    end

    AUDIT --> REBUILD
    OFFICIAL_RESULT --> REBUILD
    SIM --> DATA
    REBUILD --> DATA --> MODEL --> LOCAL --> GATE
    ROOM --> GATE
    TOUR --> GATE
```

本地模拟回答策略比较和训练数据问题；测试房间回答真实协议、规则、时限和并发问题；测试赛事回答完整生命周期问题。随机官方牌山不能替代同牌山严格 A/B，模拟器也不能证明官方协议兼容。

## 10. 第一阶段目录

```text
src/hangma_bot/
  kernel/                 # 冻结值类型
  hangma/                 # 唯一规则深模块
  policy/                 # BotPolicy 与两个启发式实现
  application/            # 端口、ParticipantRuntime 和场次任务
  adapters/
    official/             # 官方会话实现（已审查指南 v15）
    recording/            # AuditSink、汇总和验证器
  bootstrap.py            # 唯一组合根

scripts/
  run_participant.py      # 单 Token 正式路径
  run_test_room.py        # 四 Token、四进程测试路径

tests/
  contracts/
  fixtures/official/     # v8 快照 + v9（fan-calc 金例）+ v11/v14/v15（指南版本）
```

实施分工、各模块约束和验收入口见[第一阶段实施导航](./implementation/README.md)。

## 2026-09-06 实测后的同步修正

场次主循环继续由应用层驱动，官方适配器在同一个调用链内取得 state、吸收事件、核验观察并交付窗口；没有新增后台同步任务。权威快照负责当前牌面，已接收事件负责可见历史，两者不能以同一水位等价替代。快照超前时先做一次最多 100 毫秒的串行补领，并保留至少 350 毫秒的已知动作预算；失败明确缺史。收到更晚事件时先处理，快照前事件只补历史。

碰阶段的策略 pass 在适配器内转为等待，不发送官方 POST；真实吃窗口到达后由应用层重新决策。公开摸牌来源、抓打标记、超时阶段和终局结算字段完整进入玩家观察（`PlayerObservation`），规则模块只做有依据的推导与核验。完整世界状态（`WorldState`）仍归模拟模块所有，观察完整不意味着获知他家手牌或未来牌墙。字段、恢复边界与牌谱一致性检查见[接口契约](./implementation/interface-contracts.md#实测事件与恢复契约增补2026-09-06)。

## 延后补史与单局封存（2026-09-06）

官方适配器将牌面水位与历史缺口分开维护。应用层继续驱动原场次主循环：先处理已知未来事件和动作，空闲机会再有界补领旧历史。缺口首次未补到会保留，最多三次退避尝试；不存在第二个状态写入任务。补史只修复历史与有证据的动作权事实，当前牌面仍由权威快照及正常连续增量维护。

单局切换与结束产生独立高优先级历史封存记录，包含未知前缀、缺口和已收到终局事实。新单局响应附带旧手尾事件时，先构造旧手记录，待新快照验证成功后提交；不能把跨手不明事件塞入当前观察。详细字段和预算见[延后补史契约](./implementation/interface-contracts.md#延后补史与单局收尾契约2026-09-06)。


### 单局封存完整性补充（2026-09-06）

`history_closure.closure_issues` 记录附带旧尾中的未知事件、关键字段缺失、违规他家摸牌，以及未收到 `round_ended` / 场次终态未收到 `game_ended` 的原因。封存 `history_complete=true` 除要求起点、序号及原有观察完整外，还要求这些原因为空。`missing_ranges` 仅覆盖已知 `history_through_seq`，缺少更晚的尾事件不能只靠此区间表判断；不从积分或新快照捏造终局事件。该检查只影响赛后封存，不重新推进牌面、创建动作窗口或改变策略输入。

## M=4 赛后修复（2026-09-07）

继续使用单一场次主循环，不增加后台同步任务。延后补史的三次上限只统计进入传输层的尝试；未获调度许可仍退避，但不耗尽网络尝试。权威终态快照在同单局、无 gap、旧游标有效且跨度不超过256时，也可进行一次最多100毫秒的尾事件补领。此时只补历史，不能由补领结果重新打开终态或无限追赶；失败仍封存明确缺史。

原始state与动作响应增加进程内单调时钟的排队、许可、传输开始和完成时间，state 429另外记录已解析的Retry-After秒数。可区分排队与传输耗时，不能直接当作服务端收包时间。证据与验证见[M=4修复说明](../review/official-adapter/m4-live-2026-09-07/repair.md)。
