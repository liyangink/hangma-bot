# `hangma` 模块实施规范

## 目标与边界

本模块是合法动作、胡牌、向听、有效牌、财神状态和结算的唯一规则来源。先阅读根规范、统一术语表、官方 API 记录、`doc/implementation/interface-contracts.md` 和 `doc/implementation/modules/hangma.md`。

- 只依赖 `kernel`；禁止访问网络、文件、系统时间、模型或应用状态。
- `RuleConfig` 在创建 `HangmaRules` 时绑定并保持不可变。
- 第一阶段必须覆盖出牌、吃、碰、各类杠、胡、过、财神、有财必拷响、抓打圈、爆头/飘链和结算；允许局部分支存在 Bug，但不得因为一个分支异常丢失紧急动作。
- 紧急路径必须与复杂胡牌/向听搜索隔离：响应窗口过，抓打圈打刚摸牌，普通出牌打官方顺序最右一张。
- 无动作权或观察不完整时返回 `None`，不能伪造动作。

## 接口变更规则

`interface.py` 的结果类型和 `engine.py` 的公开类签名是受控契约，由总体架构维护。实施只填充 `engine.py` 方法体和内部文件；不得在策略或适配器再实现第二套合法性判断。改变公开契约前必须先提出变更原因和影响范围，再同步更新接口文档、架构图、契约测试和所有调用方。

## 主 Agent 与子 Agent 分工

规则模块工作量最大。负责本模块的主 Agent 应主动使用 2—3 个子 Agent 并行处理内部子问题，不需要用户再次转述。所有 Agent 共享同一工作区时，必须先划定独占文件，禁止多人同时编辑 `engine.py`、`interface.py` 或同一个测试文件。

主 Agent 开始时先完成以下工作：

1. 阅读官方 API/规则记录、v8 fixture、统一术语表和本模块全部说明；
2. 核对 `PlayerObservation` 与 `RuleConfig` 是否足够表达已确认规则；发现契约缺口时先向总体架构提出变更，不自行修改；
3. 确定内部不可变结果类型和文件骨架，再把互不重叠的工作派给子 Agent；
4. 优先实现 `emergency.py`，保证其他分支未完成或异常时仍有独立紧急动作；
5. 独占 `engine.py` 的最终组装、异常隔离、公开行为和集成验收。

推荐的子任务与独占文件：

| 子 Agent | 独占实现文件 | 独占测试文件 | 边界 |
| --- | --- | --- | --- |
| 手牌数学 | `hand_analysis.py` | `tests/unit/hangma/test_hand_analysis.py` | 普通型、七对、向听、有效牌和确定性分解；不判断当前动作窗口是否合法 |
| 动作族 | `action_families.py` | `tests/unit/hangma/test_action_families.py` | 出牌、吃、碰、各类杠、胡、过的候选生成；复用手牌数学，不复制向听算法 |
| 财神与结算 | `special_rules.py`、`settlement.py` | `tests/unit/hangma/test_special_rules.py`、`test_settlement.py` | 财神、有财必拷响、抓打圈、爆头/飘链和四家结算；不实现第二套通用牌型分解 |

主 Agent 独占：

- `engine.py`、`emergency.py`、必要的 `internal_types.py` 和 `__init__.py`；
- `tests/unit/hangma/test_engine.py`、故障隔离测试、官方金例与 `fan-calc` 对拍入口；
- 子 Agent 结果的代码审查、冲突解决、组合测试和性能基准。

子 Agent 完成时必须向主 Agent 报告：实现范围、未覆盖规则、采用的假设、测试结果和任何契约缺口。子 Agent 不得自行修改 `kernel`、公共接口、官方适配器或策略模块，也不得自行提交互相冲突的整仓格式化修改。

推荐集成顺序：紧急路径 → 无财神基础牌型 → 各动作族 → 财神特殊约束 → 结算 → 故障隔离 → 官方对拍。某个后续分支尚未完成时，主 Agent 应让 `RuleAnalysis` 明确标记 `DEGRADED`，而不是伪装成完整实现。

## 测试与验收

- 官方规则金例和 `fan-calc` 对拍；开源日麻规则不能作为杭麻权威依据。
- 性质测试覆盖牌守恒、动作参数、四家结算和确定性。
- 各动作族进行故障注入：胡牌分析抛错时，合法弃牌/过和紧急动作仍可产生，结果标记 `DEGRADED`。
- `emergency_action()` 的 P99 耗时必须远低于 1 秒窗口预算且不分配大对象。
- 每个 `RuleIssue` 有稳定 `area` 和可审计原因，不吞异常。
- 主 Agent 必须审查子 Agent 是否复制了规则算法、越过信息权限或修改受控契约；只有整合后的 `HangmaRules` 通过模块级验收才算完成。
