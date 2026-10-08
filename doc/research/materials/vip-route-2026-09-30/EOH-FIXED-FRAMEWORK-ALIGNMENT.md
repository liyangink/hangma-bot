# EoH 与固定框架的分工核对

日期：2026-09-30。**状态：讨论建议，不是已批准的新实施合同。**本次只核对文献与源码；不运行实验、不调用候选模型、不修改代码或既有冻结方案。前序精读入口：[EoH 笔记 §2、§5.1](../llm-guided-heuristic-route-2026-09-15/refs/REF-EoH-FunSearch-ReEvo.md)。

## 1. 结论与适用边界

**工程判断：适合。**启发式进化（`Evolution of Heuristics`，让大语言模型在评估反馈下迭代启发式代码）可以只进化固定框架中的评分函数。作者当前实现让使用者提供固定模板 `template_program`、任务描述和外部评估器 `evaluate_program`，后者返回越小越好的 `float` 或失败时的 `None`；单函数就是正式支持的模板形态，多函数与类只是可选扩展。因此无需让模型重写规则、观察编码、特征计算、动作提交或评测流程。[作者 README：应用入口与模板形态](https://github.com/FeiLiu36/EoH#use-eoh-in-your-application)、[BaseProblem 源码](https://github.com/FeiLiu36/EoH/blob/main/eoh/src/eoh/problem.py)。

对杭麻的建议分工：人和固定代码拥有规则事实、合法动作、玩家观察（`PlayerObservation`，本座依法可见的牌局事实）、特征含义与单位、保底动作、运行预算和评测定义；模型只提交允许输入上的有界评分公式，经验阈值、权重、组合与排序可进化。**这说明方法形态匹配，尚不能证明它会提高杭麻完整桌赛积分。**论文验证的是三个组合优化基准，并非杭麻。[原论文，PMLR 235，2024，§3–4](https://proceedings.mlr.press/v235/liu24bs.html)。

## 2. 思想、代码与算子的实际含义

**主源事实：双表示是自然语言“思想”与可执行代码共同传给后续生成过程，个体另有评估所得的适应度。**思想不是在线推理步骤，也不是性能证据。建议沿用本仓结构化机制说明，把触发条件、动作改变、预期方向与反例绑定到代码摘要；效果仍由外部评测决定。[论文 §3.3](https://proceedings.mlr.press/v235/liu24bs.html)、[作者提示词与个体字段](https://github.com/FeiLiu36/EoH/blob/main/eoh/src/eoh/eoh/evolution.py)。

| 标识 | 父代 | 主源中的用途 |
| --- | --- | --- |
| `i1` | 无 | 初始化一个新启发式，不计入五个进化算子。 |
| `e1` | 多个 | 参考父代，探索形式尽量不同的新启发式。 |
| `e2` | 多个 | 先归纳共同骨架，再据此提出新启发式；不是机械拼接父代代码。 |
| `m1` | 一个 | 修改启发式结构或逻辑。 |
| `m2` | 一个 | 识别主要参数并改变参数设置。 |
| `m3` | 一个 | 分析组件的过拟合风险并简化，保留接口以改善泛化。 |

表中语义对应[论文 §3.4](https://proceedings.mlr.press/v235/liu24bs.html)及[作者当前 `_build_prompt`](https://github.com/FeiLiu36/EoH/blob/main/eoh/src/eoh/eoh/evolution.py)。这些算子可全部限定在同一个评分入口内部；`e1/e2` 的探索不要求扩张规则与信息权限。

## 3. 论文与当前实现不能混称

**当前观察：作者 `main` 已使用 `LLMConfig/EoH/BaseProblem`，README 将 `Paras/eoh.EVOL` 明确标为旧 `v0.1` 接口。**论文描述五个进化算子；当前源码实现 `m3`，默认列表却只有 `e1/e2/m1/m2`。论文的代际描述也不能直接当作当前异步采样循环的预算。本文不据此重建论文实验配置。[作者 README](https://github.com/FeiLiu36/EoH)、[默认配置](https://github.com/FeiLiu36/EoH/blob/main/eoh/src/eoh/config.py)、[当前循环](https://github.com/FeiLiu36/EoH/blob/main/eoh/src/eoh/eoh/eoh.py)。

上述在线源码核对日期为 2026-09-30，`main` 是可变引用。需要复现时应冻结具体提交；本仓前序笔记冻结的是 `472545785c936dcfc863d2bc0d6109cf23c7ce62`，不能自动等同于当前 `main`。[既有来源登记](../llm-guided-heuristic-route-2026-09-15/refs/README.md)。

## 4. 本仓优先复用的入口

**当前观察：生成、受限执行、搜索与记账基础设施已经存在，宜扩展这些入口。**

| 入口 | 可复用内容与边界 |
| --- | --- |
| [`sitin_generate.py`](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py) | 当前命令入口支持 `i1/m1`，有思想与代码解析，以及固定 `score_actions(view)` 提示词。不能据 EoH 算子表声称本仓已接通 `e1/e2/m2/m3`。 |
| [`action_value_executor.py`](../../src/hangma_bot/policy/action_value_executor.py) | 已有语法子集、只读访问、工作量计费与输出约束；宜保留这些约束。作者 `BaseProblem` 中的普通 `exec` 不能替代本仓执行器。 |
| [`sitin_search.py`](../llm-guided-heuristic-route-2026-09-15/tools/sitin_search.py) | 已有生成接线、源码身份、父代关系和搜索账本；可承接新增算子，是否适配新输入仍须另行核验。 |

**工程建议：复用 EoH 的算子形状，不整体照搬默认种群管理。**作者当前 `population_management` 按适应度值去重；相同总分可能掩盖不同专长。本项目宜按行为指纹（`BehaviorFingerprint`，固定题集上的动作选择记录）去重，并保留在不同机会类型上表现不同的候选。[作者种群管理源码](https://github.com/FeiLiu36/EoH/blob/main/eoh/src/eoh/eoh/eoh.py)、[前序精读结论](../llm-guided-heuristic-route-2026-09-15/refs/REF-EoH-FunSearch-ReEvo.md)。

若讨论方案含三组评分，它们应绑定成一个候选整体，在固定组合方式下联合评价完整桌赛；不能把分别胜出的子公式直接拼接后当成已验证候选。局部机会题用于诊断专长，完整桌赛用于评估整体价值；规则事实、输入接口与确认集边界先冻结。可沿用[现有评测合同](./EVALUATION-CONTRACT.md)的同牌山四座配对和按根统计纪律；新增评分接口或算子须另行批准与登记，本文不改变该合同。
