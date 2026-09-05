# 模拟模块开工指南

> 负责人：模拟线；分支建议 `codex/simulation-v1`。依据 [parallel-v1](./parallel-contracts.md)，新增运行代码尚未实现。

## 1. 交付目标

实现能按实际 `TournamentConfig.rounds_per_game` 完成桌赛的确定性本地环境，支持同牌山、换座位、历史路径核对及完整世界导入导出。先建立正确环境，再承担模型训练数据生产；首版不做信念采样器、神经网络或完整多阶段赛事模拟。

完整世界状态（`WorldState`，包含四家手牌和牌墙的内部状态）归 simulation。完整历史轨迹（`FullHistory`，只有真实发生路径的全信息记录）不等于任意分叉起点。审计转换器只生成文件；本线决定文件能否初始化自己的世界。

先读根规范、[hangma 规范](../../src/hangma_bot/hangma/AGENTS.md)、[架构](../architecture.md)、[统一契约 §6](./parallel-contracts.md#6-模拟模块接口-simulation-v1)、[规则证据](../../src/hangma_bot/hangma/RULES_EVIDENCE.md)及[真实牌谱夹具](../../tests/fixtures/hangma/README.md)。官方依据是本地 v15/2026-09-05 快照，夹具采集时 v14；遇到差异保留两者来源，不自行认定兼容。

## 2. 对外接口与规则边界

只实现契约中的 `MatchSpec`、`SimulationDecision/Frame/Choice` 和 `SimulationEngine.start/frame/advance/export_hand/from_replay`。评估器负责策略、预算和统计；模拟器不自行创建 BotPolicy。WorldState 不透明且不可变，advance 返回新状态，允许一个起点被多个实验分叉。

当前 HangmaRules 已有 analyze/validate/emergency_action/score，但没有完整状态推进。**不能只调用 validate 后就在 simulation 内再写一遍财神、抓打圈、杠链和结算规则。** 本线同时承担实际缺少的推进能力，放在 hangma 新文件，由 HangmaRules 的公开方法委派；该内部方法由本线设计、主审审查，不影响已冻结的旧方法签名。

| 内容 | 所有者 |
| --- | --- |
| 四家手牌、牌墙/补牌位置、序号、随机状态、单局与桌赛状态的存储 | simulation/state.py |
| 发牌、随机流隔离、应用规则变更集、整理可见观察 | simulation/engine.py、projection.py、shuffle.py |
| 动作造成的牌张移动约束、响应优先级、规则状态转移、番与结算 | hangma/progression.py 及既有规则深模块 |
| 推进输入/输出的最小值对象 | hangma 内部，不依赖 simulation.WorldState；不得把世界类型搬到 kernel |
| 四座位策略调用、候选保底、实验终止、置信区间 | 评估线 |

推进输入可以包含四家规则状态等离线事实，但 `analyze(PlayerObservation)` 的线上权限不变。规则深模块不访问网络、磁盘、系统时钟或随机数；随机结果由模拟器输入。不修改官方协议投影器来服务模拟器。

## 3. 实施切片

S1 先建立一条可验收的单局路径，再扩到全部动作族；每个切片都要显式限制已支持范围。

1. 建立不可变 WorldState 与确定发牌；实现 frame 中四座位独立观察、牌张守恒和序号。保留 14/13/13/13 起点支持，不凭手牌顺序猜额外摸牌。
2. 在 hangma 补出牌、摸牌、响应与结算推进；先过普通路径，再覆盖吃碰、明/暗/补杠、补牌/抢杠、财神与全部特殊链。优先级、同时胡等细节逐项引用官方证据，未确认则 blocked，禁止默认“先到先得”。
3. 同期响应者从同一推进前状态生成观察；收集全部选择后统一裁决。输入数组顺序不改变结果；暂不模拟毫秒竞速，所有选择视为合法窗口内到达。
4. 完成连庄/换庄、倍数、牌墙结束等有证据的单局边界，并完成 Rounds 个单局。后续单局牌山随机源与前一单局动作次数分离。
5. 导出契约 hands 行及 `world_schema=simulation-world/1`，导入后行为一致。full_world 只由完整初始世界导出；from_replay 只续完导入的一个单局，不伪造原桌赛其余牌山。另存分叉用 export_hand 的可选 match_id 参数，保留 parent_hand_id 和共同 scenario，不让两条不同轨迹覆盖同一单局身份。
6. 实现 `offline/replay_check.py` 历史核对入口，供审计 CLI 和评估器调用；这不是可任意分叉的 from_replay。它只按已记录抽牌和真实动作核对，不把未来事件透露给当时策略。

历史核对公开纯函数为 `check_hand(hand: Mapping[str, object], rules: HangmaRules) -> dict[str, object]`。输出 `hand_id`、`status=passed/failed/not_checked`、`checked_events`、`issues`；issues 每项有 `seq`（无事件时 null）、`code`、`detail`、`source_refs`。格式/来源不足返回 not_checked，实际规则冲突返回 failed；不读文件，不改 hand。事件归类和规则推进复用 hangma，禁止为历史核对再建第二套规则。

## 4. 真实资料的边界

仓库 archived-rooms 样本首块有四家起手，后续 start_hands 为四个 null；同一个 round_no 分多个块，最终 game_id 不能用 batch 推导。按契约向量验证转换器输出，不能直接依赖审计线私有解析函数。

历史模式中有真实 tile_drawn 才揭示该次摸牌。timeout/pass 若是同一自动动作的附带通知，不重复推进。规则核对需要的配置缺失时可以通过显式带来源的实验配置补充，但原记录仍标缺失，不冒充官方来源。

导入官方 full_history 不足以确定尚未摸到的牌墙，必须明确拒绝反事实分叉。约束采样未来单独实施，产物必须标 simulated、父单局、采样版本与种子。

## 5. 文件认领

| 路径 | 本线权限 |
| --- | --- |
| src/hangma_bot/simulation/{interface,state,engine,projection,shuffle}.py | 新增具体实现与本模块导出；内部可以合并文件，不拆空壳 |
| src/hangma_bot/hangma/progression.py | 新增唯一规则推进；必要的内部值对象归这里或 internal_types.py |
| src/hangma_bot/hangma/engine.py | 仅本线提供推进委派；旧 analyze/validate/score 行为改动单独登记 |
| src/hangma_bot/offline/replay_check.py | 新增历史规则核对；不编辑审计的 replay.py 或评估的 evaluate.py |
| tests/simulation/；tests/unit/hangma/test_progression*.py | 本线测试 |
| bootstrap.py、kernel、旧规则接口、公共父目录 __init__.py | 提交所需差异给主审集成，不独自扩共享契约 |

不要把测试辅助代码 `tests/unit/hangma/archived_room_tools.py` 直接移作生产规则实现。先辨明哪些是官方解析，哪些是测试推演，再让生产实现通过相同真实案例。

## 6. 验收和交付

| 门禁 | 证据 |
| --- | --- |
| 信息权限 | 同一可见局面替换未公开手牌/牌墙，玩家 request 一致；已发生公开事实变化才允许观察变化 |
| 推进 | 牌张/积分守恒；非法/旧 revision/缺失选择原子拒绝；所有动作族及特殊规则有金例 |
| 确定性 | 固定规则/发牌版本/spec 结果逐字节一致；输入 choices 置换结果一致；分叉不污染父世界 |
| 完整桌赛 | Rounds 来自配置；不支持分支返回 blocked，不能计入完成局数；达到完整桌赛才给 final_scores |
| 资料核对 | 三份真实分块资料按能力核对；缺信息为 not_checked，冲突有 seq 和原文引用 |
| 导出 | full_world 导出导入一致；full_history 缺墙拒绝世界导入；稳定文件可交评估线直接运行 |

建议本地命令 `python -m pytest tests/simulation tests/unit/hangma tests/contracts`（目录创建后执行）。提交 `handoffs/simulation.md`，附支持/阻塞矩阵、规则证据、新公开导出、实际命令和产物哈希。不宣称已通过平台测试或全阶段赛事模拟。
