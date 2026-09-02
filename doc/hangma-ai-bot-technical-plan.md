# 杭麻 AI Bot 技术方案与一个月实施计划

> 状态：架构评审后草案 v0.1
> 日期：2026-09-02
> 目标日期：2026-09-30 前完成本地稳定运行并接入官方平台
> 关联资料：[官方平台 API v2 记录](./official-platform-api-v2.md)、[官方最小 Bot Demo](./references/official_minimal_bot_v2.py)、[指南版本快照](./references/official-guide-version-v2.json)

## 1. 文档目标与范围

本文记录已经讨论和交叉评审过的：

1. 线上 Bot 与离线训练系统的架构、模块划分和依赖方向；
2. 各模块在未来一个月内可信的实现范围、核心算法和验证方式；
3. 已知赛事规则、官方接口、时间模型以及仍待确认的事项；
4. 2026-09-30 前的初步 roadmap。

本文按以下优先级控制范围：

- **P0 必须交付**：没有它就无法稳定参赛；
- **P1 应当交付**：对胜率或可迭代性有明确帮助；
- **P2 可选增强**：仅在 P0/P1 稳定后进入；
- **不进入本月范围**：短期收益不确定或工程成本明显超出一个月。

### 1.1 本月明确不做

- 在线调用 LLM 决定打牌；
- 在线多 Agent 投票；
- 从零训练大型 Transformer 或完整纯自博弈 RL 系统；
- 在 1 秒吃碰窗口运行复杂搜索；
- 完整实现通用 ISMCTS/CFR 博弈求解器；
- 大规模适配日麻引擎或直接迁移日麻预训练权重；
- 自建观战 Web、牌桌 UI 等非参赛关键功能；
- 让 LLM 自动决定模型是否上线。

LLM 的定位是离线研发教练：协助编码、生成测试、分析牌谱和训练曲线、组织实验，但不进入线上行动闭环。

## 2. 核心结论

一个月内最可信的交付不是“先训练一个麻将大模型”，而是：

1. 先完成可靠的官方接入、状态同步和动作窗口状态机；
2. 建立与官方一致的杭麻规则核心；
3. 完成可独立参赛的确定性启发式 Bot；
4. 建立同规则模拟器、牌谱和评测体系；
5. 将小型候选结果模型作为可插拔 challenger，只有完整 8 局评测显著胜出后才启用。

线上决策链：

```text
官方事件
  → 可信玩家观察
  → 杭麻合法候选与确定性分析
  → 启发式保底动作
  → 可选：候选结果预测
  → 赛事晋级目标评估
  → deadline 守卫与最终复核
  → 提交官方动作
```

离线迭代链：

```text
官方牌谱 / 本地模拟
  → 按当时信息重建 PlayerObservation
  → 隐藏世界采样和候选反事实模拟
  → 训练候选结果模型 / 轮次价值模型
  → 完整 8 局、同牌山、换座位评测
  → 统计门禁
  → 人工审核后发布模型产物
```

## 3. 架构评审结论

早期方案把系统拆成 10 个线上模块和 4 个离线模块，职责方向基本正确，但交叉评审发现以下问题必须在编码前修正。

### 3.1 必须修正的问题

| 严重度 | 问题 | 修正决策 |
| --- | --- | --- |
| P0 | 一个 `GameState` 同时表达平台同步状态、玩家观察和模拟完整状态 | 拆为 `PlayerObservation`、`WorldState`、`DecisionRequest` |
| P0 | `rules.apply_action(GameState)` 在隐信息环境中语义不成立 | 线上规则只分析观察；只有模拟器推进完整世界 |
| P0 | 在线 Rollout 依赖模拟器，但模拟器被放进纯离线目录 | 模拟引擎移入生产核心；离线代码只负责批量生成和训练 |
| P0 | 普通 Q 值、结果预测和赛事效用混用 | 明确 `CandidateOutcomeModel` 输出赛制无关的四家联合结果分布 |
| P0 | 隐藏牌和牌墙采样埋在 Rollout 内 | 增加显式 `BeliefSampler` seam |
| P0 | 训练和线上可能各自实现编码 | 增加共享且版本化的 `learning` 模块 |
| P0 | 缺少动作命令状态机和非幂等 POST 处理 | 增加 `GameSession`、`ActionGate`、`DecisionBudget` |
| P1 | `heuristic/prediction/tournament/decision` 都暴露给启动入口 | 收口到一个深的 `policy` 模块，内部继续独立实现和测试 |
| P1 | `TournamentUtility` 混合官方规则和未来预测 | 拆为确定性赛事目标、剩余局估计、第一轮晋级线估计 |
| P1 | 评测只覆盖 Predictor | 正式评测完整 Policy、完整 8 局和官方时间/恢复壳 |

### 3.2 设计原则

- **深模块**：复杂实现隐藏在小接口后，调用方不需要理解内部步骤；
- **接口即测试面**：调用方和测试通过同一个 seam；
- **只在真实变化处定义 seam**：例如官方/回放 Gateway、启发式/混合 Policy、神经/Rollout Estimator；
- **类型隔离信息权限**：线上 Policy 在类型层面不能读取完整 `WorldState`；
- **单一规则来源**：线上判定、模拟、数据生成和测试共享同一个杭麻规则核心；
- **训练/推理一致**：特征编码、动作编码、归一化和输出解释只能有一份实现；
- **副作用外置**：网络、时钟、并发和日志不进入规则与策略纯计算；
- **保底优先**：任何模型、搜索或日志异常都不得阻止合法动作按时提交。

## 4. 最终模块划分

建议采用 8 个生产顶层模块和 4 个离线应用。它们是同一 Python 工程中的 package，不是微服务，也不需要独立部署。

```text
src/hangma_bot/
  kernel/                 # 极小稳定值对象
  hangma/                 # 确定性杭麻规则
  simulation/             # 完整世界状态、模拟和 belief
  competition/            # 晋级目标和轮次价值
  learning/               # 共用特征、网络和模型产物
  policy/                 # 唯一线上决策 seam
  application/            # 多场运行、deadline 和资源调度
  adapters/
    official/             # 官方平台 Adapter
    replay/               # 牌谱回放 Adapter
    recording/            # 非阻塞记录 Adapter

offline/
  ingest.py               # 牌谱导入与观察重建
  generate.py             # 模拟与反事实数据生成
  train.py                # 小模型训练与校准
  evaluate.py             # 完整 Bot 评测和报告

bootstrap.py              # 唯一组合根
```

### 4.1 依赖方向

箭头表示“上层依赖下层”：

```text
kernel
  ↑
hangma       competition       learning
  ↑              ↑                ↑
simulation       └──── policy ─────┘
  ↑                    ↑
offline apps        application
                        ↑
             official/replay/recording adapters
                        ↑
                    bootstrap
```

严格禁止：

```text
hangma       → official / application / policy / learning
competition  → official / application
learning     → official / application
simulation   → 官方 HTTP 接口
policy输入    → WorldState
training     → application/runtime
CompetitionObjective → 实时 HTTP 查询
NeuralEstimator → 完整规则引擎
```

真正需要在运行入口稳定组装的角色只有：

```text
GameGateway + BotPolicy + DecisionSink
```

其余模块在内部独立开发和测试，不等于都要成为启动入口可见的 seam。

## 5. 核心数据类型与信息权限

### 5.1 `kernel`

只放长期稳定且跨模块共享的值对象：

```text
Tile
Seat
ScoreVector
RuleVersion
Action
```

`Action` 应使用带类型的联合，而不是一个带大量可空字段的字典：

```python
Action = Discard | Chi | Peng | Gang | Hu | Pass
```

内部动作身份至少考虑：

```text
canonical_action_id
gang_kind
source_discard_seq
response_window_id
```

这些字段不一定发送到官方接口，但用于去重、日志、训练标签和回放。

### 5.2 `PlayerObservation`

线上策略唯一允许读取的麻将状态：

- 本人手牌和本人刚摸到的牌；
- 四家牌河、副露和剩余手牌张数；
- 当前阶段、行动座位、可响应座位；
- 庄家、局号、剩余牌数、四家桌内积分；
- 财神、爆头、动作链、抓打圈等本人或公开状态；
- 已公开的公共行动历史。

不得包含：

- 他家真实手牌；
- 未公开牌墙；
- 未来事件；
- 赛后才知道的番型和结果。

### 5.3 `WorldState`

只存在于 `simulation`：

- 四家完整手牌；
- 完整牌墙和随机数状态；
- 完整规则状态；
- 当前应行动玩家；
- 可用于结算的完整信息。

唯一允许的投影：

```python
observe(world: WorldState, seat: Seat) -> PlayerObservation
```

模拟器中的每个 Policy 也只能收到自己的 `PlayerObservation`。

### 5.4 `DecisionRequest`

线上动作窗口上下文：

```python
@dataclass(frozen=True)
class DecisionRequest:
    observation: PlayerObservation
    competition: CompetitionContext
    decision_id: str
    trigger_seq: int
    window_key: WindowKey
    estimated_deadline: float
```

`estimated_deadline` 必须使用单调时钟。由于当前接口没有服务端绝对截止时间，它只能是保守估计，不能命名为绝对真实 deadline。

## 6. 各生产模块的关注点与实现思路

### 6.1 `hangma`：确定性杭麻规则（P0）

#### 接口

```python
class HangmaRules:
    def choices(self, observation: PlayerObservation) -> ChoiceSet: ...
    def score(self, win: WinDescription) -> Settlement: ...
```

`ChoiceSet` 一次返回：

- 所有合法动作；
- 每个动作的确定性牌型分析；
- 向听数、有效牌、结构类型；
- 财神、七对、爆头、动作链等规则标记；
- 可确定的胡牌分数和特殊分支。

#### 实现思路

1. 使用花色分解动态规划或记忆化搜索计算面子、搭子、对子；
2. 普通型和七对分别计算向听，再结合财神数量取合法最优结果；
3. 有效牌按当前可见牌扣除后的剩余张数加权，不只计算牌种；
4. 吃碰杠后的牌型分析只返回确定性 afterstate 分析，不伪造完整下一状态；
5. 胡牌和计分与官方 `fan-calc` 做金标准对拍；
6. 使用性质测试验证牌守恒、动作合法性和结算总分守恒。

#### 验证标准

- 官方规则金例全部通过；
- `fan-calc` 随机对拍无差异；
- 任意 `ChoiceSet` 中不存在服务端必然拒绝的动作；
- 规则计算在单次决策预算内稳定完成，不能访问网络。

### 6.2 `simulation`：完整环境与隐藏信息采样（P1）

#### 接口

```python
class SimulationGame:
    def reset(self, seed: int, config: RuleConfig) -> WorldState: ...
    def observe(self, world: WorldState, seat: Seat) -> PlayerObservation: ...
    def step(self, world: WorldState, action: Action, rng: RNG) -> StepResult: ...
```

#### 实现要求

- 固定 seed 可完全重放；
- 状态转换不读取网络、文件和当前时间；
- 模拟不实现第二套杭麻规则；
- 状态可复制或持久化，支持候选反事实分叉；
- 首版优先多进程批量模拟，不要求本月完成 JAX/GPU 向量化。

#### `BeliefSampler`

```python
class BeliefSampler(Protocol):
    def sample_worlds(
        self,
        observation: PlayerObservation,
        history: PublicHistory,
        count: int,
        rng: RNG,
    ) -> tuple[WorldState, ...]: ...
```

本月只要求 `UniformLegalSampler`：根据牌守恒、公开弃牌、副露和手牌张数生成合法隐藏世界。学习型 belief 属于 P2。

候选 Rollout 应让所有动作共享同一批隐藏世界样本，降低比较方差。简单 determinization 可能存在 strategy fusion 偏差，因此其定位是启发式增强和离线教师，不宣称得到博弈均衡。

参考：[Information Set Monte Carlo Tree Search](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf)。

### 6.3 `competition`：赛事目标与晋级概率（P1）

拆成三个内部职责。

#### `CompetitionObjective`

纯函数，由官方赛制确定：

```text
第一轮：最终全场排名 ≤ 16 → 1，否则 0
第二轮：桌内排名 ≤ 2 → 1，否则 0
第三轮：桌内排名 ≤ 2 → 1，否则 0
决赛：按官方最终奖励向量
```

#### `StageContinuationEstimator`

输入当前四家积分、剩余局数、座位/庄家安排，输出桌内最终排名联合分布。首版可以先用规则化 Monte Carlo；数据足够后训练小型 MLP。只有证明历史轨迹本身提供额外信息时才考虑 GRU。

#### `GlobalCutoffEstimator`

第一轮专用：根据实时全局榜单、已完成进度和历史模拟，估计第 16 名最终积分线分布。全局排名过旧或接口字段缺失时，必须降级为最大化期望积分，不能使用伪精确晋级概率。

本模块与 Suphx 的 global reward prediction、run-time policy adaptation，以及 Mortal 的 GRP 思路一致：单局战术预测与整轮排名价值分离。[Suphx](https://arxiv.org/abs/2003.13590)、[Mortal model](https://github.com/Equim-chan/Mortal/blob/main/mortal/model.py)。

### 6.4 `learning`：训练/推理共享实现（P2）

统一拥有：

```text
FeatureSchema
ObservationEncoder
ActionEncoder
NetworkDefinition
Calibration
ModelArtifact
InferenceAdapter
```

模型产物必须包含：

```text
guide_api_version
ruleset_hash
feature_schema_version
action_schema_version
engine_commit
continuation_policy_id
opponent_pool_id
belief_sampler_version
calibration_version
training_data_id
checkpoint_hash
```

关键版本不匹配时拒绝加载并自动使用启发式 Policy。

#### `CandidateOutcomeModel`

本项目不优先学习一个与赛制绑定的标量 Q 值，而是学习：

```text
PlayerObservation + CandidateAction
  → 本局结束时四家积分变化的联合分布
```

形式上可记为：

```text
Z^π(o, a)
```

其中 `π` 是动作后的 continuation policy 和 opponent pool，必须版本化记录。模型输出至少包括：

```python
class HandOutcomeDistribution:
    joint_score_delta_samples: Array[N, 4]
    winner_probs: Array[5]  # 四家 + 流局
    uncertainty: float
```

不能分别预测四个人的独立积分分布后再拼接，否则会丢失相关性。可参考 distributional RL 的收益分布思想，但本项目必须保持四家结果联合一致性。[QR-DQN](https://arxiv.org/abs/1710.10044)。

首版模型目标：1-3M 参数、CPU 毫秒级推理、一次批量评估全部合法动作。网络可采用小型 1D-CNN/ResNet 加全局标量特征和动作 embedding。

### 6.5 `policy`：唯一线上决策 seam（P0/P1/P2）

#### 外部接口

```python
class BotPolicy(Protocol):
    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionProposal: ...
```

Adapter：

```text
HeuristicPolicy   # P0，完全不依赖模型
HybridPolicy      # P2，启发式 + CandidateOutcomeModel + competition
```

`HybridPolicy` 内部才包含：

```text
HangmaRules
FallbackPolicy
OutcomeEstimator
CompetitionEvaluator
候选保留策略
不确定性处理
deadline 降级
```

#### 启发式核心算法

启发式优先使用分层排序，避免早期依赖大量拍脑袋权重：

```text
1. 胡牌和硬规则优先
2. 最低向听数
3. 最大加权有效牌数
4. 最大预期成牌收益
5. 最大手牌灵活度
6. 最小对手加速风险
```

杭麻没有点炮胡，因此对手风险重点不是放铳，而是：

- 弃牌被下家吃或其他玩家碰的概率；
- 吃碰后对手缩短了多少结构；
- 是否加速庄家或直接排名竞争者；
- 是否让对手进入爆头、飘、杠等高倍链。

模型很小时应评估全部合法动作；只有昂贵 Rollout 才筛选候选。胡、杠、爆头/飘特殊分支，以及最高收益、最低风险、最高方差候选不得被普通 Top-K 直接裁掉。

#### Online Rollout 限制

- 吃/碰 1 秒窗口不运行 Rollout；
- 出牌 3 秒窗口只允许有界、可取消的少量搜索；
- 任何时候先算出 fallback，再启动模型或搜索；
- 模型/搜索未在 soft deadline 前返回，立即使用 fallback。

### 6.6 `application`：多场运行与资源调度（P0）

负责：

- 持续发现新增 `active_games`；
- 每场独立 Session，单场失败隔离；
- 最多 16 场和最多 32 个挂起长轮询；
- 动作、状态恢复、长轮询、排名刷新的优先级；
- 模型推理和 CPU Rollout 的有界并发；
- 模型预热、超载拒绝和 deadline watchdog；
- 优雅退出与永久错误隔离。

建议共享调度设施：

```text
ApiScheduler
  action POST > gap/409/模糊提交恢复 > 长轮询 > ranking refresh

InferenceScheduler
  最早 deadline 优先、有界并发、超载降级

BotSupervisor
  动态发现比赛、启动/回收 Session、故障隔离
```

### 6.7 `adapters/official`：官方平台 Adapter（P0）

内部包含：

```text
OfficialV2Transport
StateProjector
GameSession
ActionGate
ApiScheduler
CompetitionContextCache
```

`StateProjector` 是纯实现模块，可独立回放测试，但不需要作为 `bootstrap` 的顶层 seam。

#### 状态同步

- `seq <= last_seq`：幂等忽略重复事件；
- `seq != last_seq + 1`：不应用部分增量，立即全量重建；
- `gap=true`：全量重建；
- 全量快照整体替换，不做字段级 merge；
- `pending=true`：不修改状态和 seq；
- 未知事件记录后将状态标记为需要重建；
- 当前桌积分以权威 game snapshot 为准；
- 全局榜单单独缓存并携带 `as_of` 和 staleness。

#### `ActionGate`

动作窗口状态机：

```text
OPEN
  → RESERVED
  → SUBMITTING
  → ACKED
  → CONFIRMED_BY_EVENT

异常：REJECTED_409 / AMBIGUOUS_TRANSPORT_FAILURE / EXPIRED
```

窗口键至少包含：

```text
game_id + round_no + triggering_seq + phase + seat
```

同一弃牌的 `response_peng` 和 `response_chi` 是两个窗口，不能只按 `last_discard` 去重。

动作 POST 是非幂等操作。发生网络超时后不能盲目重试，因为服务端可能已经执行但响应丢失；必须转为 `AMBIGUOUS`，等待权威事件或拉全量快照确认。

#### 对外 seam

```python
class GameGateway(Protocol):
    async def discover_sessions(self) -> AsyncIterator[GameSessionPort]: ...

class GameSessionPort(Protocol):
    async def next_request(self) -> DecisionRequest | GameFinished: ...
    async def submit(self, proposal: DecisionProposal) -> SubmitResult: ...
```

正式实现、牌谱回放和测试 Fake 均满足这一 seam。

### 6.8 `adapters/recording`：非阻塞记录（P0）

记录：

- 原始事件和规范观察；
- API/规则/模型/特征版本；
- 合法候选和启发式分析；
- 模型预测、晋级效用和不确定性；
- fallback 原因、耗时、最终动作；
- 最终积分和排名。

写日志必须经过有界后台队列；磁盘慢、磁盘满或序列化失败不能阻塞动作。Token 必须在进入记录模块前被彻底移除。

## 7. 离线模块与训练闭环

### 7.1 `offline/ingest.py`（P1）

职责：

- 保存不可变原始牌谱；
- 按每个决策时刻重建当时的 `PlayerObservation`；
- 生成合法候选和行为动作；
- 保存最终结算，但不把未来信息放入输入特征；
- 按赛事/房间/时间划分训练集和验证集，避免相邻决策泄漏。

自动泄漏测试：改变未公开手牌和未来牌墙、保持 `PlayerObservation` 不变，线上特征编码和模型输出必须完全一致。

官方赛后完整四家手牌可用于类似 Suphx oracle guiding 的教师标签，但学生模型输入始终只能是 `PlayerObservation`。[Suphx](https://arxiv.org/abs/2003.13590)。

### 7.2 `offline/generate.py`（P1/P2）

```text
PlayerObservation
  → BeliefSampler
  → 同一批 WorldState
  → 多候选动作分叉
  → 后续 PolicyPool 续打
  → 四家联合积分结果
```

每条数据记录：

```text
continuation_policy_id
opponent_pool_id
belief_sampler_version
ruleset_hash
random_seed
```

首轮不对所有状态做昂贵反事实模拟，只选择：

- 启发式前两名分数接近的状态；
- 吃/碰/杠/过等结构性决策；
- 最后一两局的高方差晋级决策；
- 模型高不确定或历史上高 regret 的状态。

### 7.3 `offline/train.py`（P2）

本月仅考虑两个小模型：

1. `CandidateOutcomeModel`：候选动作到本局四家联合结果；
2. `StageContinuationModel`：当前积分和剩余局数到最终桌内排名联合分布。

第一轮全场第 16 名分数线优先使用实时榜单和规则化估计，数据足够后再训练 `GlobalCutoffEstimator`。

训练一旦不能在单张常规 GPU 上数小时级迭代，应缩小模型和数据，不扩大基础设施。

参考项目：

- [Mortal](https://github.com/Equim-chan/Mortal)：规则引擎、局部 DQN、全局 GRP 分离，legal mask 与小型 GRP；
- [RLCard](https://github.com/datamllab/rlcard)：环境、合法动作、Agent 和训练循环 seam，但其麻将规则过于简化，不能复用规则或权重；
- [MahJax](https://github.com/nissymori/mahjax)：`init/step/observe`、批量模拟和 BC/PPO 示例，本月只借鉴环境接口和可重放思想；
- [Suphx](https://arxiv.org/abs/2003.13590)：global reward prediction、oracle guiding、run-time policy adaptation；
- [QR-DQN](https://arxiv.org/abs/1710.10044)：收益分布学习思想。

### 7.4 `offline/evaluate.py`（P0/P1/P2）

评测分四层：

1. **规则一致性**：官方金例、`fan-calc` 对拍、牌守恒和结算守恒；
2. **局部策略**：固定困难状态、候选 regret、结果分布校准；
3. **完整赛事**：完整 8 局、同牌山、交换座位、第一轮前 16 率、第二/三轮前 2 率、决赛第一率；
4. **运行可靠性**：1 秒/3 秒 deadline、并发、409、gap、限速、模糊提交和模型降级。

统计置信区间按“完整 8 局比赛/牌山 seed”聚类 bootstrap，不能把同一场的上百个决策当作独立样本。

评测程序只输出报告和置信区间；模型晋级由独立门禁规则和人工审核决定。

## 8. 已知赛事信息

### 8.1 参赛形式

- 第一至第三轮为远程联赛，通过官方 API 自动完成对局；
- 决赛在官方指定场所，继续接入命题方提供的杭麻竞赛平台；
- 全程由 AI 自动决策，人不得手动参与；
- 2026-09-30 前须保证程序本地稳定运行并可接入平台。

### 8.2 晋级流程

- 第一轮：全部完赛后按积分取前 16 名，随机组成 4 桌；
- 第二轮：每桌取前 2 名，共 8 人，随机组成 2 桌；
- 第三轮：每桌取前 2 名，共 4 人进入决赛；
- 决赛：4 人同桌，按决赛积分排名；
- 每轮均为 8 局。

由此确定赛事目标：

```text
第一轮：最大化 P(全场排名 ≤ 16)
第二轮：最大化 P(桌内排名 ≤ 2)
第三轮：最大化 P(桌内排名 ≤ 2)
决赛：最大化官方定义的最终名次效用
```

### 8.3 当前调研得到的杭麻规则

以下规则需要继续用官方规则页、测试房间和 `fan-calc` 固化为金例：

- 136 张牌，不含花牌；
- 白板为财神，可作为万能牌使用；
- 财神牌本身不用于吃、碰、杠等公开组合，可主动打出；
- 以自摸胡为主，当前规则记录未包含点炮胡；
- 支持普通牌型和七对；
- 吃牌次数最多 2 次，碰/杠次数不限；
- 不允许抢杠；
- 牌墙最后 20 张保留；
- 存在爆头、飘、杠等动作链和倍数；
- `YouCaiBiKao` 为锦标赛可变参数；
- 打出财神后可能进入抓打圈：其他玩家不能吃、碰、明杠，本人只能打刚摸牌，仍可暗杠和自摸胡；
- 庄闲结算不对称，精确分值必须以本地规则和官方 `fan-calc` 对拍为准。

## 9. 已知官方接口与时间模型

当前记录基于 2026-09-02 的官方指南 v2；平台仍在迭代，启动时必须检查版本。

### 9.1 关键接口

| 用途 | 接口 | 备注 |
| --- | --- | --- |
| 身份与活跃比赛 | `GET /api/me` | 返回 `tournament_id`、`active_games` |
| 当前锦标赛规则 | `GET /api/tournaments/me/rules` | 读取 `Rounds`、底分和时间窗口等 |
| 报名/到位 | `POST /api/tournaments/{id}/register`、`ready` | 幂等 |
| 锦标赛状态和实时排名 | `GET /api/tournaments/{id}` | 包含 `my_games`、实时 `ranking` |
| 对局长轮询 | `GET /api/games/{id}/state?seq=N` | `seq=0` 为权威快照 |
| 提交动作 | `POST /api/games/{id}/action` | 非幂等；非法/过期返回 409 |
| 指南版本 | `GET /portal/api/guide/version` | 新 breaking 版本阻止进入新赛事 |
| 官方计分校验 | `POST /portal/api/tools/fan-calc` | 仅用于测试和离线校验 |
| 测试房间赛后数据 | `/api/test-rooms/{id}/games/{batch}/events` | 完赛后含四家起手牌和各局结果 |

Portal Cookie 接口不属于稳定 Bot 契约，线上 Bot 不依赖。

### 9.2 v2 关键变化

- 快照不再提供 `allowed_actions`，客户端必须自研完整合法动作判定；
- 快照新增本人 `seat`；
- 吃牌可通过 `tiles` 指定组合；
- 玩家实时事件只包含本人摸牌，不包含他家手牌；
- 事件解析必须允许未知类型记录和恢复，不能直接崩溃。

### 9.3 时间与并发

| 项目 | 当前值/限制 |
| --- | --- |
| 碰/明杠窗口 | 默认 1 秒，固定走满 |
| 吃窗口 | 默认 1 秒，固定走满 |
| 出牌窗口 | 默认 3 秒；可胡时超时自动胡，否则打最右一张 |
| 长轮询无事件挂起 | 最多 30 秒 |
| 状态轮询频率 | 最多 8 次/秒/用户 |
| 并发挂起轮询 | 最多 32 个/用户 |
| 同时比赛 | 最多 16 场，且受锦标赛 `M` 限制 |

建议默认内部预算：

- 1 秒吃碰窗口：只使用预计算、启发式或快速神经网络，目标 200-300ms 内提交；
- 3 秒出牌窗口：先算 fallback，再运行快速模型；至少预留约 700ms 用于网络、校验和恢复；
- 排名刷新不进入动作关键路径，只读取缓存；
- HTTP 长轮询超时与动作思考时间完全分离。

## 10. 待确认信息

### 10.1 影响赛事效用的 P0 问题

1. “每轮 8 局”在平台上是 `config.Rounds=8` 的一个 `game_id`，还是 8 个独立 `game_id`？
2. 每轮开始积分是否完全清零，还是跨轮继承？
3. 第一轮第 16/17 名、桌内第 2/3 名同分时如何判定？
4. 决赛只重冠军还是完整名次均有不同奖励？需要最终奖励向量。
5. 第一轮 `ranking` 是否包含全体参赛者、准确积分、完成局数和更新时间？
6. 第一轮参赛总人数及全局排名刷新时机是什么？
7. 八局中的座位、庄家和发牌安排如何变化？

### 10.2 影响平台可靠性的 P0/P1 问题

1. 是否会提供服务端绝对 `deadline_at` 或服务器时钟同步方式？
2. 动作 POST 是否计划支持幂等键或请求 ID？
3. 正式环境 TLS CA/证书信任方案是什么？
4. 锦标赛正式牌谱是否也能通过与测试房间相似的接口下载？
5. `ranking` 条目正式字段结构、排序和刷新频率是什么？
6. 8 局若拆分为多个 game，官方是否提供轮内累计积分和 `StageProgress`？
7. 决赛现场的硬件、网络、进程和模型大小限制是什么？

### 10.3 需要继续固化的规则问题

- 财神在所有普通型、七对和特殊分支中的替代边界；
- 爆头、飘、杠动作链的完整断链条件和倍数；
- 庄闲精确结算；
- 抓打圈所有允许/禁止动作；
- 最后 20 张保留与流局处理；
- 同时满足多个番型时的叠加规则；
- 超时自动胡和弃胡后的后续行为。

## 11. 初步 Roadmap（2026-09-02 至 2026-09-30）

roadmap 以“先形成可参赛基线，再增加胜率”为原则。若资源不足，P2 模型可以延期，但 P0 不可延期。

### 阶段 0：9 月 2-4 日，冻结契约和测试骨架

#### 交付

- 冻结 `Tile/Seat/Action/PlayerObservation/WorldState/DecisionRequest`；
- 创建 package 骨架和依赖检查；
- 保存官方 v2 DTO 样本、版本响应和 Demo；
- 建立 pytest、性质测试和牌谱 fixture；
- 列出规则金例与待确认问题清单。

#### 退出标准

- `PlayerObservation` 无法导入或访问 `WorldState`；
- 官方原始 JSON 不进入 policy；
- package 依赖无反向环。

### 阶段 1：9 月 5-10 日，官方运行壳与规则核心（P0）

#### 交付

- `OfficialV2Transport`、`StateProjector`、`GameSession`；
- seq/gap/409/未知事件恢复；
- `ActionGate` 和模糊提交处理；
- 多场 Supervisor 和基本限速调度；
- 杭麻合法动作、胡牌、向听、有效牌和计分；
- 与 `fan-calc` 的自动对拍。

#### 退出标准

- 测试房间可连续稳定完成对局；
- 无重复动作提交；
- 所有关键状态恢复测试通过；
- 规则金例和随机 `fan-calc` 对拍通过；
- 模型完全关闭时也能运行。

### 阶段 2：9 月 11-15 日，启发式可参赛基线（P0）

#### 交付

- `HeuristicPolicy`；
- 出牌、吃、碰、杠、胡、过的分层排序；
- 抓打圈和特殊链硬约束；
- deadline fallback；
- 非阻塞决策日志和牌谱回放；
- 1 秒/3 秒压力测试。

#### 退出标准

- 完整对局无人工介入；
- 非法动作率为 0 或仅剩可解释的竞态 409；
- 1 秒窗口不因模型、日志或其他场阻塞；
- API 断连、429、409、未知事件后可恢复；
- 形成可在 9 月中旬冻结的保底参赛版本。

### 阶段 3：9 月 16-21 日，模拟、赛事效用与评测（P1）

#### 交付

- 可重放 `SimulationGame`；
- `UniformLegalSampler`；
- 候选根节点 Rollout；
- `CompetitionObjective`；
- 第二/三轮前 2 和决赛排名模拟；
- 第一轮全局榜单缓存与保守降级；
- 完整 8 局同牌山、换座位评测框架。

#### 退出标准

- 模拟结算与线上规则同源；
- 改变隐藏牌但保持观察不变时，Policy 输入不变；
- 启发式不同版本可以用完整晋级率比较；
- 第一轮榜单过旧时明确降级，不产生伪精确结果。

### 阶段 4：9 月 22-25 日，小模型 challenger（P2）

#### 交付

- 困难状态反事实数据集；
- 共用 FeatureSchema 和 ModelArtifact；
- 第一版 `CandidateOutcomeModel`；
- 结果分布校准和 CPU 推理基准；
- `HybridPolicy`，模型异常自动回退启发式。

#### 退出标准

- checkpoint 版本不匹配会拒绝加载；
- 模型推理不会阻塞 deadline；
- 完整 8 局晋级指标优于启发式，且置信区间达到门禁；
- 若未显著提升，则不上线，不影响基线版本。

### 阶段 5：9 月 26-30 日，冻结与稳定性冲刺（P0）

#### 交付

- 9 月 26 日起冻结规则、接口和模型结构；
- 长时间 soak test、多场并发和故障注入；
- 版本自检、配置校验、密钥和日志脱敏；
- 部署脚本、启动检查、健康检查和回滚说明；
- 最终官方环境联调。

#### 退出标准

- 连续长时间运行无内存、任务或文件句柄泄漏；
- 多场同时到达动作窗口时，动作提交优先级正确；
- 模型/CPU/GPU/磁盘异常全部能降级启发式；
- 可从干净环境一键启动；
- 发布候选只有“启发式稳定版”和“通过门禁的混合版”两套，能够快速回滚。

## 12. 交付优先级总结

### P0 必须在 9 月中旬前稳定

- 官方 v2 Gateway、Session、ActionGate；
- 单一杭麻规则核心；
- 启发式 Policy；
- 多场并发、deadline 和恢复；
- 非阻塞日志和牌谱回放；
- 规则、运行和端到端测试。

### P1 应在冻结前完成

- 同规则 SimulationGame；
- UniformLegalSampler；
- 赛事目标和完整 8 局评测；
- 第一轮榜单缓存和保守降级；
- 候选根节点离线/有限在线 Rollout。

### P2 只有通过评测才上线

- CandidateOutcomeModel；
- StageContinuationModel；
- HybridPolicy；
- 学习型 belief 或更复杂搜索不作为本月承诺。

## 13. 参考资料

### 官方资料

- [官方平台 API 与时间模型 v2](./official-platform-api-v2.md)
- [官方最小 Bot Demo](./references/official_minimal_bot_v2.py)
- [官方指南版本 v2 快照](./references/official-guide-version-v2.json)

### 研究和开源实现

- Junjie Li et al., [Suphx: Mastering Mahjong with Deep Reinforcement Learning](https://arxiv.org/abs/2003.13590)：global reward prediction、oracle guiding、run-time policy adaptation；
- [Mortal](https://github.com/Equim-chan/Mortal) 与 [模型实现](https://github.com/Equim-chan/Mortal/blob/main/mortal/model.py)：规则引擎与模型分离、Dueling DQN、legal mask、GRP；
- [RLCard](https://github.com/datamllab/rlcard)：环境、合法动作、Agent 和训练循环的接口设计；
- [MahJax](https://github.com/nissymori/mahjax)：`init/step/observe`、可重放状态和批量模拟；
- Peter Cowling et al., [Information Set Monte Carlo Tree Search](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf)：信息集搜索、determinization 与 strategy fusion；
- Will Dabney et al., [Distributional Reinforcement Learning with Quantile Regression](https://arxiv.org/abs/1710.10044)：收益分布建模与分位数回归。

上述项目用于借鉴模块 seam、算法思想和训练目标，不直接复用其日麻规则或预训练权重。Mortal 代码采用 AGPL-3.0，若未来直接复用代码必须单独审查许可证；本方案优先自行实现小型模型和杭麻规则。
