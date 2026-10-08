# T3 开发探针与完整桌入口独立审核

日期：2026-09-30。**状态：已完成本批六份离线文件的独立审核；Standards 修前 2 项、Spec 修前 1 项均已修复复核，当前两轴各无待修可行动项。**审核区分规范符合性（`Standards`，仓库约束）与规格符合性（`Spec`，冻结合同）；不合成总分，不证明候选强度、独立确认或发布资格。

## 范围与方法

审核者未参与六份实现。审查起点为 `main` 的 `09aea2e47`，对象是工作区新增的 `offline.vip_eoh_probe`、`offline.vip_route_development` 及各自脚本、单元测试；另只读核对所调用的生产接口和集成文档。先读仓库、tests、scripts 的 `AGENTS.md`、[固定框架合同](./FIXED-FRAMEWORK-CONTRACT.md)、[T3 首批预登记](./T3-DEVELOPMENT-BATCH-1.md)、[评测合同](./EVALUATION-CONTRACT.md)。按 `code-review` 的两轴方法审查；并发槽已占满，两轴由本审核者分别核对，没有把一个轴的通过用来抵消另一个轴。

未读取 `.private` 或 DSH 凭据，未调用模型，未接官方房，未运行真实八局桌赛；未改实现、数据库、数据集、生成器、合同或旧封存证据。下面的完整计划测试使用假驱动（`mock`，只验证编排的替身）；真实模拟只启动一个在首窗立即失败的自然单局，并另验证一个真实规则视图的评分窗口。

## Standards

**修前两项规范遗漏，已分别交作者和根修复并复核。**没有另立可行动的设计气味项。

| 发现 | 依据与修前位置 | 处理 |
| --- | --- | --- |
| S1：公开 `VipDevelopmentAuditPolicy.choose` 缺中文接口说明 | 仓库 `AGENTS.md` §4 要求公共接口有中文 docstring；原 `src/hangma_bot/offline/vip_route_development.py:301` 无说明 | 作者已补输入、输出、异常与审计副作用说明；最终 `vip_route_development.py:413` 已复核 |
| S2：新数据流尚未同步到架构与主方案 | 仓库 `AGENTS.md` §3；原两文顶端只有 T0–T2 事实与策略内容 | 根已在 `doc/architecture.md:12`、`doc/hangma-ai-bot-technical-plan.md:11` 同步 probe、行为信用、H/M 四换座、物理起庄及双账范围；已只读复查 |

其余规范事实：规则分析沿 `HangmaRules`，评分沿 `ActionValueExecutor.score_vip_route`，没有复制规则；脚本只解析公开材料并调用离线入口。抽卡只用行动前观察、合法动作键和窗口键；候选只收到新视图的权限白名单。开发结算包装器只调用模拟器公开 `frame` 与 `export_hand_settlement`，不读 `WorldState` 内部字段。测试通过公开接口和公开故障注入点检验行为，未以内部状态代替断言。

## Spec

**修前一项 P2 门禁缺口，经两轮修正已关闭。**probe 本身没有已复现的可行动错误。

### P2：完整桌入口没有强制绑定实际行为探针证据

T3 预登记要求：“无首选差异的源码仍归档，但不投入昂贵完整桌”。第一版 `VipDevelopmentBatch.read` 的原字段与校验只冻结生成包（原 `vip_route_development.py:102`、`:154`），其后 `run_vip_route_development` 可直接调桌（原 `:446`、`:472`）。独立的 33 项旧测试证明不提供 probe 材料也会派发假完整计划；公开入口缺门，不应靠操作者记忆维持这项纪律。

作者第一轮增加了行为摘要路径和 SHA256、完整包 × 窗口分母、候选完整身份及源码/生成记录摘要、至少一项完整且真实首选改变的逐父比较，并重新装载冻结父包（第一轮 `vip_route_development.py:103`、`:171`、`:200`、`:215`、`:228`）。但校验仍不要求真实 probe 必有的 `batch_sha256`、`implementation_manifest`、`panel_path/panel_sha256`；明确标为 `synthetic_structure_not_measured_behavior_for_mock_driver_only` 的人工摘要也能通过真实入口的前置校验。第一轮测试夹具位置为 `test_vip_route_development.py:86`。

已通过公开接口最小复现：在临时目录用 `write_vip_seed_parent` 建父包，构造不同源码的可装载候选包，再写上述人工摘要与开发批次，调用 `VipDevelopmentBatch.read`。输出为 `accepted synthetic summary without batch_sha256, implementation_manifest or panel: synthetic-summary.json`。模型调用 0、桌赛运行 0。这不是假驱动可产生强度的结论；它证明该人工材料尚未被真实入口隔离。

第二轮最终复核：`VipDevelopmentBatch.read` 默认不接受人工行为夹具（`vip_route_development.py:97`、`:199`）；只有替身 `match_runner` 才由运行入口开启夹具读取，产物来源强制 `mock`（`:497`）。真实路径核当前生成批次字节、实际 probe 依赖闭包、面板字节及有序输入摘要（`:205`、`:207`、`:214`、`:222`），并经新公开 `validate_vip_eoh_panel` 重核原审计与行动前选择（`vip_eoh_probe.py:187`）。原面板、manifest、decisions、来源源码及生产源码均进入冻结文件；当前候选和实际父包仍完整绑定，运行尾部逐文件重核（`vip_route_development.py:232`、`:260`、`:633`）。

审核者独立窄复验 **36 项通过**，包括默认真实读取拒夹具、真实单窗公开 probe 输出可被验证、错误批次/生产源码/面板/输入 ID 的准确拒因，以及坏字段、完整分母、首选变化和实际父包绑定。结构坏字段测试显式使用假材料开关，没有被“禁止夹具”提前失败掩盖。该 P2 缺口修复成立。

新增公开验证器与 `input_sha256s` 改变了 probe 的测量源码身份。此前行为摘要必须保留原身份；进入新门须在新目录重新测得完整 probe，不能给旧封存摘要补字段或换摘要追认。

### 已核对的规格事实

| 项目 | 最终冻结版事实与精确位置 |
| --- | --- |
| 完整窗口分母 | `vip_eoh_probe.py:272` 为每包每窗写结果；装载、建图、评分失败不删行，`:328` 保留比较分母 |
| 实际首选差异 | `vip_eoh_probe.py:289` 使用分数降序及键字典序，与严格策略一致；`:328` 要求完整比较，`:339` 才发差异信用。尺度、解释、仅次选换序不算新机制 |
| 全合法评分 | `vip_eoh_probe.py:260` 重核当前同源全部合法键，`:284` 用真实受限执行入口。候选漏项、弃权、超量均未完成；开发 `vip_route_development.py:439` 观察实际 `SCORED` 调用，不把首选恰等于紧急动作算回退 |
| 源码与原生身份 | probe `:304`、`:315` 首尾经 `load_vip_parents` 重核源码、记录、合同、实际 `RuleConfig`、投影与规则额度；唯一身份入口 `vip_heuristic_smoke.py:49` 纳入第一方闭包、原生 C 与当前数学二进制。开发 `vip_route_development.py:509`、`:519` 保存实际源码、合同及原生快照 |
| 四换座与同墙 | 每根四个不同焦点座位（`vip_route_development.py:130`），每映射 A/C 同 seed；`:582` 将逻辑庄设为 `permutation.index(0)`，经共同驱动映射后物理起庄均 0。策略分化后自然推进，没有强给未来相同摸牌 |
| 完整八局与新对手池 | 公开批次 `vip_route_development.py:114` 固定 `Rounds=8`、两池、四映射 A/C 全分母；`:161` 与 `:590` 固定共同 8192 分析档。H 为三名注册研究 R18；M 为注册研究 R18、完整 V2、等胡 V2（`:305`、`:314`），冻结权重、风险表和源码；另起新池身份，不沿用旧线上包 |
| 成本与失效 | `vip_route_development.py:578` 在桌组调用前持久化两臂预留，`:600` 异常不退费；`:458`、`:467`、`:470`、`:633`、`:638` 核缺行、重复行、内部 R18 降级、非零/未知运行计数、身份与墙钟失效。`:619` 与 `:622` 保留原始 `MatchResult` 和运行记录，失败池估计为空 |
| 信息权限与双账 | `vip_route_development.py:425` 当前机会只记录行动前合法胡及同源立即番值，未来资格明确未知；`:356` 只导出已完成自然单局，`:660` 另汇总普通/高番胡、他家先胡、流局。未知证据不补零、不倒填机会 |

## 验证记录

| 命令或最小检查 | 独立观察 | 可证明范围 |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/unit/offline/test_vip_eoh_probe.py`（最终版） | **26 passed in 15.26s**；公开验证器添加前另独立验证 25 项 | 抽卡、共享真实视图、排序、失败分母、来源与包漂移、显式 128 上界及公开面板验证器 |
| `.venv/bin/python -m pytest -q tests/unit/offline/test_vip_route_development.py`（行为门修前） | **33 passed in 24.83s** | 假完整计划、固定物理庄、预算与缺行/漂移；真实首窗失败及单窗全合法评分，不证明八局完赛 |
| 两个脚本 `--help` | 正常 | 公开 CLI 可装载，未执行模型或桌赛 |
| `.venv/bin/python -m pytest -q tests/unit/offline/test_vip_route_development.py -k 'default_production_reader or real_probe_reader or real_shaped_probe or invalid_behavior_summary or noncomplete_or_nonpreferred_behavior or behavior_summary_must_bind'` | **36 passed, 37 deselected in 20.15s** | 最终生产门与身份绑定的独立窄复验；真实 probe 只评分单窗，未跑完整桌 |
| 只读统计公开 `behavior-panel-1/panel.json` | 来源 3,407 窗、3,407 唯一输入、87 层、选 87 张、显式上界 128；行动前阶段 `draw/response_chi/response_peng` 为 28/29/30，白板量 0/1/2/3 为 34/35/15/3 | 实际开发覆盖。没有四白窗口，不是框架规则缺陷 |
| 第一轮门的公开 `VipDevelopmentBatch.read` 临时材料复现 | 人工摘要缺三组生产材料仍通过；0 模型、0 桌赛 | 证明第二轮修复必要性，不能用作行为或强度信用 |

作者报告的最终 development **73 项通过（61.47 秒）**是作者验证；审核者对最终版独立复验上述 36 项，不将两者相加冒充独立覆盖。前序 33 项与最终窄集存在重叠，亦不相加。

## 最终六文件字节指纹

此表只冻结本次已审核代码与测试，不含候选成绩或生成出处。读取到的 development 三份指纹与作者重新冻结通知一致。

| 文件 | SHA256 |
| --- | --- |
| `src/hangma_bot/offline/vip_eoh_probe.py` | `1a75c4e4f68d376f09d69ec3d93cd4ce0786a5e09929cc4e23bbd958767e933d` |
| `scripts/vip_route_eoh_probe.py` | `6bf8216a6a44ca1e3c01a1cfb075c8663419be830a8b25409e7f5ceaaf1a58f9` |
| `tests/unit/offline/test_vip_eoh_probe.py` | `3ec37ca51f10a17e09a7ec000a21e565e5cf942821dd99cf696b828a7799d3ea` |
| `src/hangma_bot/offline/vip_route_development.py` | `e8e4e5721015df1a114964715e448d4bd399e5dc87fa6f3628b07251ae3e688e` |
| `scripts/vip_route_development.py` | `90ed1c85aff5d245314d3a69b360173586268c24db6cc79c4e713f18cc5caa60` |
| `tests/unit/offline/test_vip_route_development.py` | `3eaaca9c731a64915792be5bcdb2f65e9196c08f9fc4f6fdb47d97f3894f865f` |

## 剩余边界

1. 本批是开发材料；T2 种子 202/203 和本面板已曝光，不能作为独立确认。87 层没有四白真实行为证据；不据此宣称所有多白或特殊规则组合都覆盖。
2. 当前机会账是 `current_legal_hu_only`，尚未形成结果盲的完整机会题与对应负控；盲等、普通出口损失、他家先胡等反事实机会得失没有被当前窗口账完整测量。自然已发生结算不能替代该账。
3. 同一根列表分别在 H/M 跑开发比较，不等于确认合同要求的两个独立抽样框。确认需新根、根级区间、查看与停止纪律以及功效依据；不能把少量开发根估计升级为领先。
4. 逻辑时钟与策略计算观察毫秒不证明官方 1/3 秒。墙钟检查在桌组之间阻止启动，不能抢占同步评分；超时后置空是失效纪律，不是硬抢占保证。
5. 身份与快照核验适用于本批新 CLI 解释器。长期已导入进程仍需防止实际内存代码与磁盘清单失配；首尾磁盘摘要不是任意长驻进程的完整证明。
6. 本审核未运行真实八局 A/C 完整桌、官方接线或发布门。任何假驱动及人工结构摘要都不能标为真实强度；真实材料门已复核，不代表完整桌运行已经产生。

两轴分别为：Standards 修前 2 项、修后 0 项；Spec 修前 1 项 P2、修后 0 项。最严重 Standards 项为数据流文档未同步，已修；最严重 Spec 项为行为准入证据未强制绑定，已修。此结论只适用于声明的六文件和开发范围。
