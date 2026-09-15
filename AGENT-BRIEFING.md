# AGENT BRIEFING：接手本项目所需的知识背景

> **这份文档不含任务进度、待办或阶段验收结论。** 它只回答一件事：
> **一个没读过任何前序对话的 agent，需要具备哪些背景知识、读过哪些文献、知道哪些可靠实现，才能接手。**
>
> **怎么用**：先读本文；再按 §8 的“阅读路径”深入对应模块。本文只提供背景摘要和资料索引。
> **依据顺序**：规则事实核对对应版本的官方资料与留存验证证据；研究结论核对原论文；实现细节核对固定提交的源码。笔记和方案中的转述不能替代一手依据。
>
> 根 [AGENTS.md](./AGENTS.md) 规定项目约束；本文补充理解这些约束所需的背景。

## 1. 项目是什么、红线是什么

**开发能接入官方杭麻竞赛平台的全自动赛事 Bot。** 优先级固定（根 `AGENTS.md` §1）：

1. 官方协议与杭麻规则正确；
2. 1 秒/3 秒动作窗内稳定提交合法动作；
3. 可参加官方测试赛事、可审计的最小可用版本；
4. 可回放、可模拟、可评估；
5. 在可靠基线上提高晋级指标；
6. **大语言模型（`LLM`，用于离线生成和审查候选算法）只作研发教练，不进入线上动作闭环。**

**本启发式路线的三条红线**（不训练模型的用户约束见 [DESIGN.md §0 D-1](./review/llm-guided-heuristic-route-2026-09-15/DESIGN.md)）：

- **不训练任何自适应模型**（不训练网络权重、不训练代理模型、不训练价值头）；
- **线上不含任何 LLM 调用**；线上只有确定性启发式；
- **不得把工程推理当成规则事实写进文档**（根 `AGENTS.md` §3 要求区分：官方已确认 / 当前观察 / 工程建议 / 待确认假设）。

## 2. 赛事与规则背景

### 2.1 一手依据在哪

**本文规则基线为官方指南 v34，页面更新于 2026-09-14，本地同步于 2026-09-15。** 版本信息见 [API 同步记录](./doc/official-platform-api-v2.md)和[官方版本响应](./doc/references/official-guide-version-v34.json)；运行时仍须核对平台版本及实际赛事配置。

| 内容 | 文件 | 说明 |
| --- | --- | --- |
| **官方规则指南 v34 原文** | [指南快照](./doc/references/official-guide-v34-content.txt) | 规则一手依据；正文内部有历史措辞冲突时，结合版本修订和留存的官方接口对拍证据核对 |
| 官方平台 API | [API 与时间模型](./doc/official-platform-api-v2.md) | 已同步至指南 v34；文件名中的 `v2` 为兼容既有链接保留 |
| 赛事流程 | [多阶段晋级规则](./doc/official-tournament-flow-2026-09-03.md) | 海选、晋级轮、决赛的场次与排名链；版本边界见文件开头 |
| 统一术语 | [统一术语表](./UBIQUITOUS_LANGUAGE.md) | **所有文档与代码必须用它定义的名称** |

### 2.2 杭麻与日麻/国标的结构性差异

下列规则来自指南 v34 §1；赢家接庄单独标明观察证据。

- **只能自摸，没有点炮、抢杠胡**。风险包括**支付他家自摸**；防守仍可能有价值，但须按杭麻机制解释。
- **财神 = 白板**，是万能牌；**不能被吃、碰、杠、胡**；**抓打圈**：弃白者本人不受限（可吃碰明杠、可任意出牌），**其余三家只能摸切 + 暗杠 + 自摸**，任何人再弃白即原子换主。
- **爆头**：听牌态摸任意 1 张即胡；**正好 4 张白板亦按此判定**。四白本身不保证爆头；指南计番表残留“四白除外”旧措辞，修订与官方对拍依据见 [RULES_EVIDENCE.md 的四白修订记录](./src/hangma_bot/hangma/RULES_EVIDENCE.md)。
- **动作链**：飘（爆头态打出财神）与杠**每个动作 ×2**，可连续可组合；**打出非飘非杠的牌（含非爆头态打白板）→ 链断清零**。
- **吃最多 2 摊**（服务端 409 强制）；碰/杠不限；**碰（含明杠）窗口先于吃窗口**。
- **庄家倍率恒 ×8、无连庄递增；流局保留庄家**。【当前观察】非流局由赢家接庄，依据 2026-09-08、2026-09-10 抓取的官方牌谱，见 [RULES_EVIDENCE.md 的庄家轮转记录](./src/hangma_bot/hangma/RULES_EVIDENCE.md)；线上采用官方返回的庄家。
- **最后 10 墩（20 张）保留不摸，且该区间禁止任何杠**。
- **七对子：禁止吃碰明杠暗杠**（官方明文）。
- **可胡时可以弃胡**。v33 修订（2026-09-13 起）后，杠后补牌即使能胡也进入决策窗口，可选择胡牌、合法续杠或弃胡出牌；超时仍由服务端自动胡兜底。

### 2.3 番数与三家分别结算

**番数描述胡牌结果；单局局分还取决于庄家身份和三家的支付。** 以下依据指南 v34 §1.3—§1.4。

```text
总番 = 分支因子 × 2^动作链次数 × 四白因子 × 爆头因子
四白因子、爆头因子：各自满足条件时为 2，否则为 1
计算顺序：分支 → 动作链 → 四白 → 爆头
基础结算量 T = 底分 × 总番（单位：积分）
```

分支：平胡 ×1 / 七对 ×2 / 豪华七对 1、2、3 组 ×4、×8、×16。官方极值：平胡分支最大 `2⁶×2×2=×256`；全局最大 `×16×2³×2×2=×512`。

- **庄家胡牌**：三家闲家各付 `8T`，赢家单局局分为 `+24T`。
- **闲家胡牌**：庄家付 `8T`，另两家闲家各付 `T`，赢家单局局分为 `+10T`。
- 支付者的单局局分为对应负数。`×8 / ×1` 是分别支付的倍率，不能直接充当赢家的总入账倍率。

指南的“最后统一加”描述爆头因子的结算顺序，**并未提出对数评分方法**；§3.1 的取对数是本项目的数学推导。

### 2.4 阶段晋级与决赛目标

**【官方已确认】** 依据指南 v34 §2.6 与[赛事流程 §2—§5](./doc/official-tournament-flow-2026-09-03.md)：

- 海选按实际到位人数定档：`≥17` 人取前 **16**，`9—16` 人取前 **8**，`5—8` 人取前 **4**；4 人直接决赛，少于 4 人作废。v13 起的新建赛事按“已确认且开赛时在线”计人数；后续阶段可能因到位人数不足而降档。**200—300 人只能是场景假设，不是官方固定规模。**
- 16 强、8 强按**固定四人组、多桌累计**，每组前二晋级；晋级阶段按总得分、名次分、白板获取数依次排序，三键完全相同时由 `user_id` 字典序兜底。各阶段独立计分，采用官方排名。
- **决赛只看本阶段累计总得分**；任何同分都触发四人加赛，直到第 1—4 名总得分两两不同。

**【工程判断】** 最大化期望积分与最大化晋级概率是不同目标。承担更大方差是否有利，取决于当前分数、晋级线与剩余赛程，不能一概鼓励高风险。自由赛对手池分桶只能作参考；其参赛覆盖、代表性与实力变化均不足以作为赛事强度标准。

### 2.5 运行时配置与赛事生命周期

**【官方已确认】** 指南 v34 §1.6 要求读取实际赛事 `config`：`Rounds`（每桌赛单局数）、`M`（并发场数上限）、`BaseScore`（底分）、`YouCaiBiKao`（有财必拷响）以及 `PengTimeoutSec`、`ChiTimeoutSec`、`DiscardTimeoutSec`（动作窗口秒数），不能把示例值写死。

新阶段必须重新确认到位；`active_games` 为空可能是阶段间隙或决赛加赛间隙，不能据此结束进程。生命周期细节见[赛事流程](./doc/official-tournament-flow-2026-09-03.md)。

## 3. 我们的思路、方法论与算法基础

### 3.1 番数分解提供可解释的特征结构

**【数学推导】对已经成立的胡牌结果，取以 2 为底的对数后，番数公式严格可加。** 方括号表示条件成立时取 1，否则取 0。

```text
log2(总番) = 分支项(0..4) + 动作链次数 + [手留白+链内飘出 == 4] + [爆头]
```

对这些胡牌结果取期望时，`E[log2 总番]` 仍精确可加，**不需要各项独立**。规则唯一确定的是已实现番数的指数，尚未完成的局面如何映射到这些结果，需要另外设计。

**【工程用途】番数结构提供可解释的特征分解；如何用这些特征评价未完成局面，仍是待验证的启发式设计。** 胡牌概率、成形失败、支付他家自摸、剩余机会及与基础牌效分的尺度关系，都不能由计番公式自动确定。规则中的指数不能直接充当动作价值系数，也不能据此宣称评分器没有自由参数。

对数对单个正番数保序，**不保证取期望后策略排序一致**：`max E[log R]` 与 `max E[R]` 一般不同（这里 `R>0`）；期望对数对正回报波动更保守。单局净积分可能为零或负数，不能直接套用 `log R`，更不能据此推出晋级目标等价。

### 3.2 势差：检查奖励一致性的设计工具

**势函数（`Φ`，给状态赋予一个辅助数值）可用来构造塑形奖励：** `F(s,a,s') = γΦ(s') − Φ(s)`。其中 `s`、`s'` 为转移前后状态，`a` 为动作，`γ` 为与原目标一致的折扣因子。依据 [Ng、Harada 与 Russell 1999 定理 1](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf)。

**引用该定理时须保留以下边界：**

- 它保证的是在相应马尔可夫决策过程（`MDP`，状态包含预测下一步所需信息的决策模型）条件下，向原奖励加入势差后，**累计回报的最优策略保持不变**。它不直接保证把一步势差加到现有局部评分器后，贪心选动作仍保持最优。
- 若采用不折扣的有限单局目标，可设 `γ=1`。此时整条轨迹的势差和为 `Φ(终态)−Φ(初态)`；通常令所有终态势为 0，才能排除终态差异造成的额外偏好。仅知道“单局会结束”还不够；无限时域折扣情形还须满足势函数有界等原文条件。
- `Φ` **不必覆盖全部价值量**，势差的代数消去也不要求全知状态。线上可从玩家观察（`PlayerObservation`，仅含本座位依法可见的信息）构造势函数；若引用原论文的最优策略结论，仍须说明观察历史或信念状态（对隐藏局面的概率描述）如何满足建模条件，不能借此读取他家手牌。
- `γ=1` 时，真正的势差沿闭环求和为 0；**有限闭环测试只是必要性质的回归检查**，不能证明所有转移和路径都来自同一个势函数。检查应包括明确的 `Φ` 定义、终态处理与逐次转移等式；`γ≠1` 时不能照搬普通闭环和为零的判据。
- “碰加 1、吃加 2”能否写成势差，取决于状态转移结构，不能仅凭动作标签断言不可能。若没有上述构造与条件，只能称为启发式加分；其效果由完整桌赛评估确定。

### 3.3 划分层：本路线选择按价值分量组织

**【工程选择】按价值分量组织候选，有助于表达跨吃、碰、杠、弃等动作共享的评价依据。** 动作族是动作空间或模型职责的划分，价值分量是评价函数的划分；它们是不同设计维度，可以并存。

- [Suphx](https://arxiv.org/pdf/2003.13590) 按不同动作任务组织多个模型，说明动作族划分本身有成功实例。本文选择价值分量，不代表文献证明它是唯一正确方式。
- [Johanson 等 2013 §4](https://www.ifaamas.org/Proceedings/aamas2013/docs/p271.pdf) 研究的抽象合并信息集、保留动作；这是特定扑克方法的范围，不能外推为所有领先系统都不抽象动作。
- [Waugh 等 2009 §4](https://www.ifaamas.org/Proceedings/aamas09/pdf/01_Full%20Papers/13_21_120_FP_0888.pdf) 给出更细抽象未必更好的反例。对本项目的启发是：**划分质量要在相同评估条件下实测**，不能仅由粒度或名称判断。

### 3.4 迭代对象：价值分量、选择规则与评价函数结构

[栗田、保木 GPW2017](https://ipsj.ixsq.nii.ac.jp/record/183838/files/IPSJ-GPWS2017011.pdf) 明确说明，决定何时采用哪种一人麻将模型的流程包含作者经验规则，并有改进余地。[伊原、加藤 2017](https://ipsj.ixsq.nii.ac.jp/record/182413/files/IPSJ-BIO17050013.pdf) 则研究手牌评价函数的多目标优化。

**【工程迁移】这些工作支持把“局面如何选择价值分量”及评价函数结构作为搜索对象；不保证迁移到杭麻后的效果。** 本路线由冻结的 LLM 提议可审计的启发式代码，具体可改字段与参数边界见 [DESIGN.md](./review/llm-guided-heuristic-route-2026-09-15/DESIGN.md)；不训练模型的约束不等于启发式没有设计参数。

### 3.5 适应度与评估边界

**本路线用完整桌赛配对差衡量候选强度，并用实际阶段格式验证赛事目标。** 历史实验记录过窗内估计 `+8.9 分/窗`、完整桌赛却为 `−15.37 分/桌`；另一次一步上界实验的噪声地板为 `+12.47`，净信号为 `+3.03`。这些是特定实验中代理信号失效的证据，出处见[路线的历史实验分析](./review/llm-guided-heuristic-route-2026-09-15/README.md)。

- 候选与基线按实际 `config.Rounds` 完成桌赛，使用**同牌山与换座位**；以同牌山根组（`scenario_id`，共享同一随机牌山的配对与换座试验组）聚类计算置信区间，不能把相关换座结果当独立样本。见[统计实现](./src/hangma_bot/offline/evaluation_statistics.py)。
- **开发集与确认集隔离**：候选生成、反思、调参、择优只使用开发集；确认集用于冻结候选的独立验证，其结果不得反馈给生成器反复筛选。划分与记录要求见[实施设计](./review/llm-guided-heuristic-route-2026-09-15/DESIGN.md)。
- 决策级样本可检查合法性、时限、触发覆盖和行为差异；违反门禁可以淘汰。行为差异也可用于维护种群多样性，但**不能当作强度提升证据，或替代完整桌赛适应度**。
- 逻辑时钟用于可复现的模拟推进，其结果**不能证明线上真实尾延迟达标**；实际时限、并发与恢复能力须经真实计时和官方测试赛事验证。见[项目评估约束](./AGENTS.md)与[路线时限门禁](./review/llm-guided-heuristic-route-2026-09-15/README.md)。

## 4. 文献：读哪一份、为什么读

本地精读笔记与原实现索引位于 [`review/llm-guided-heuristic-route-2026-09-15/refs/`](./review/llm-guided-heuristic-route-2026-09-15/refs/)，下文 `refs/` 均指该目录。**笔记不是论文全文**；各项是否取得原文、读到什么范围、哪些仍属推导，以笔记中的证据标记为准。

| 文件 | 读它是为了什么 |
| --- | --- |
| [REF-DECOMP-mahjong-systems.md](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-DECOMP-mahjong-systems.md) | **麻将系统如何切分决策**：Mxplainer、Suphx、Kurita & Hoki 等系统的实例与迁移边界；各文献的获取范围分别标明 |
| [REF-DECOMP-game-abstraction.md](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-DECOMP-game-abstraction.md) | **抽象质量与势差的理论依据**：保持最优动作、抽象误差与可表示性；迁移时核对博弈类型和原文条件，势差边界见本文 §3.2 |
| [REF-DECOMP-riichi-axis.md](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-DECOMP-riichi-axis.md) | **日麻方法学的分解轴及其证据强度**：哪些是研究证据、哪些只是惯例；动作族与价值分量的比较 |
| [REF-EoH-FunSearch-ReEvo.md](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-EoH-FunSearch-ReEvo.md) | **候选如何生成**：思想与代码双表示、初始化与演化算子、岛屿模型、ReEvo 反思模板与循环；仓库区别见本文 §5 |
| [REF-MEoH-AlphaEvolve.md](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-MEoH-AlphaEvolve.md) | **种群管理与分级评估**：MEoH 支配与差异性（含手算验算）、AlphaEvolve 评价级联、程序数据库 |
| [REF-diversity-and-multiobjective.md](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-diversity-and-multiobjective.md) | **多样性、多目标与归因**：HSEvo 度量、MoH 泛化、多目标算法接缝、ReVEL 行为画像、LLM 增益归因方法 |
| [refs/README.md](./review/llm-guided-heuristic-route-2026-09-15/refs/README.md) | **8 个本地参考仓库的固定提交号表**与引用纪律 |

**引用纪律**：凡引用外部实现细节，**必须连实现版本/提交号一起引用**——本项目已在此栽过两次。

## 5. 参考实现与复用边界

本地副本在 `review/llm-guided-heuristic-route-2026-09-15/refs/vendor/`（**不入库**）。恢复副本时须检出[提交号表](./review/llm-guided-heuristic-route-2026-09-15/refs/README.md)中的固定提交；仅浅克隆最新默认分支不能保证版本一致。下列事实限于这些快照。

| 机制 | 从哪里 | 固定版本事实与复用要求 |
| --- | --- | --- |
| **演化算子提示词与顺序调度** | `vendor/LLM4AD@ffb6acf`：[prompt.py](https://github.com/Optima-CityU/LLM4AD/blob/ffb6acf64497be93932c98d25369352efd3865cf/llm4ad/method/eoh/prompt.py)、[eoh.py](https://github.com/Optima-CityU/LLM4AD/blob/ffb6acf64497be93932c98d25369352efd3865cf/llm4ad/method/eoh/eoh.py) | **I1 初始化 + E1/E2/M1/M2 四个演化算子**；该实现循环进入后先执行 E1，E2/M1/M2 各有开关并受预算检查约束；提示词要求大括号内一句话描述思想，再按给定空函数模板实现代码 |
| **另一套 EoH 实现** | `vendor/EoH@4725457`：[eoh.py](https://github.com/FeiLiu36/EoH/blob/472545785c936dcfc863d2bc0d6109cf23c7ce62/eoh/src/eoh/eoh/eoh.py)、[evolution.py](https://github.com/FeiLiu36/EoH/blob/472545785c936dcfc863d2bc0d6109cf23c7ce62/eoh/src/eoh/eoh/evolution.py) | 提示词位于 `evolution.py`；调度用 `random.choices` 按配置权重选算子。不能把上一行的路径和 E1 顺序执行结论归给这个仓库 |
| **反思式反馈** | [reevo@6dce182](https://github.com/ai4co/reevo/tree/6dce18257da5e11db2d138e417a2fffc5c72d05f) | 短期、长期反思模板；本项目允许反馈开发集表现，**禁止确认集信息** |
| **支配与差异性种群** | `LLM4AD@ffb6acf`：[meoh/population.py](https://github.com/Optima-CityU/LLM4AD/blob/ffb6acf64497be93932c98d25369352efd3865cf/llm4ad/method/meoh/population.py) | **`sum(0)` 是按列求和**，惩罚落在**被支配者**上；与支配者越相似，惩罚越大，差异性使惩罚减轻 |
| **评估预算计数** | `LLM4AD@ffb6acf`：[meoh.py](https://github.com/Optima-CityU/LLM4AD/blob/ffb6acf64497be93932c98d25369352efd3865cf/llm4ad/method/meoh/meoh.py) | 计数器在 `if self._profiler is not None:` 内更新，未启用日志时**评估次数上限失效**；若设有代数上限，仍可因代数停止。本项目预算计数应独立于日志 |
| **差异性度量** | `codebleu@375817f`：[syntax_match.py](https://github.com/k4black/codebleu/blob/375817f785b7b64a7e1c0e5686eed5b60329e005/codebleu/syntax_match.py) | 源码注释承认匹配方向与论文不同，分母取参考程序一侧，**不能直接当对称相似度使用** |
| **FunSearch 岛屿机制与公开参数** | `vendor/funsearch@cc53f27`：[config.py](https://github.com/google-deepmind/funsearch/blob/cc53f274237d7ab05c19df939edbc1f9616a7c19/implementation/config.py)；[原论文](https://www.nature.com/articles/s41586-023-06924-6) | **参数已公开**：10 个岛屿、每次提示词使用 2 个程序、每 4 小时触发岛屿重置。应按杭麻评估成本确定本项目配置，不能直接照搬 |
| **复用边界** | [MEoH/AlphaEvolve 笔记](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-MEoH-AlphaEvolve.md)、[多样性笔记](./review/llm-guided-heuristic-route-2026-09-15/refs/REF-diversity-and-multiobjective.md) | 所查 AlphaEvolve 官方材料未提供可直接复用的运行实现；`HSEvo@f3afffa` 的两个多样性度量位于独立 `diversity/` 命令行包，在该快照中不进入搜索循环 |

## 6. 项目内部的基础设施（各一句，细节进对应文档）

**理解基础设施前先记住三个边界**（[AGENTS.md §5—§6](./AGENTS.md)）：策略只使用 `DecisionRequest` 中依法可用的观察、赛事上下文、规则分析与决策元数据，不读取完整世界状态（`WorldState`，模拟器持有的四家手牌、完整牌墙等全信息状态）；`hangma` 是规则的唯一实现来源；增强计算开始前必须已有合法保底动作。

| 文件 | 它是什么 |
| --- | --- |
| 根 `AGENTS.md` | **最高约束**：优先级、统一语言、证据分级、模块边界、线上安全、训练与评估约束 |
| `doc/architecture.md` | 模块划分与数据流；按日期倒序堆叠修订 |
| `doc/implementation/interface-contracts.md` | **受控契约**：规则与策略协议、动作提交、审计、错误契约 |
| `doc/implementation/modules/*.md` | 六个模块各自的说明（kernel/hangma/policy/application/adapters/…） |
| `UBIQUITOUS_LANGUAGE.md` | 统一术语；"已标记的歧义" |
| `src/hangma_bot/hangma/RULES_EVIDENCE.md` | 规则实现的证据级别清单 |
| `doc/implementation/evaluation-datamart-design.md` | 评估数据底座（桌赛结果、按策略视图） |
| `doc/implementation/policy-iteration-plan.md` | 策略版本计划（V0/V1/V2 冻结纪律） |
| `doc/implementation/baselines/heuristic-v0.json` | V0 冻结指纹 |

## 7. 三条最贵的教训（不读会重走）

1. **窗内信号陷阱**：历史实验显示，窗内估计可能与完整桌赛结果反向，一步估计也可能被噪声主导。采样窗口适合门禁、覆盖与行为诊断；**用它替代完整桌赛来宣称强度提升，才是需要避免的外推**。
2. **结论可能由测量方式决定**：本项目出现过"直方图在构造上只能得 0"（诊断把两个不同的量混成一个），得出一个看起来有数据支撑、实际由过滤条件造成的结论。**报数字前先问"这个数是怎么被筛出来的"。**
3. **把推导写成既定规则**：历史文档曾把“庄位对期望积分中性”“提前收胡有大损失”“开圈有正收益”等推理写成事实。**工程推理标【推导】或【待检验假设】；官方牌谱观察与接口对拍标明证据范围、版本或采集时间，不能混同为官方明文。**

## 8. 阅读路径（按你要接什么选）

| 你接手的是 | 按这个顺序读 |
| --- | --- |
| **规则/hangma** | 根 `AGENTS.md` §5–§6 → `doc/references/official-guide-v34-content.txt`（**全文**）→ `doc/implementation/interface-contracts.md` §4 → `src/hangma_bot/hangma/RULES_EVIDENCE.md` → `src/hangma_bot/hangma/AGENTS.md` |
| **策略/policy** | 本文 §2–§3 → `UBIQUITOUS_LANGUAGE.md` → `src/hangma_bot/policy/AGENTS.md` → `doc/implementation/modules/policy.md` → `doc/implementation/interface-contracts.md` §4 |
| **评估/离线** | 本文 §3.5 → `doc/implementation/evaluation-datamart-design.md` → `src/hangma_bot/offline/evaluation_statistics.py`（根组聚类 bootstrap） |
| **研究路线（启发式迭代）** | 本文 §3 → `refs/REF-DECOMP-*.md`（三份）→ `refs/REF-EoH-FunSearch-ReEvo.md` + `refs/REF-MEoH-AlphaEvolve.md` → `refs/README.md` 的提交号表 |

## 9. 边界声明

- **本文不含任何任务进度**；进度与待办一律以仓库内的路线文档为准，不从本文推断。
- 本文区分规则事实、论文结论、源码事实与工程迁移；`refs/` 笔记是阅读索引。标注【未能获取】或【未一手核实】的项，以及超出原论文条件的推导，**不得当既定事实使用**。
- 开源实现（`refs/vendor/`）**不能**当作杭麻官方规则依据（根 `AGENTS.md` §3）。
