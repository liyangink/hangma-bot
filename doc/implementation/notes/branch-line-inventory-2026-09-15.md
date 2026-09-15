# 分支路线与可复用资产盘点（2026-09-15）

> 本文是只读盘点记录：核对远端分支、逐分支归纳训练探索进展与可复用资产，并回答"各分支是否都以训练 RL 模型为目标、阻碍是否为时间与算力不足"。
> 证据标记沿用 [AGENTS.md](../../../AGENTS.md)：**官方已确认**／**当前观察**／**工程建议**／**待确认假设**。
> 所有"当前观察"均可由文中给出的路径在对应分支工作区复核。

## 1. 本次本地化操作（当前观察）

```text
git fetch --all --prune --tags      # 新增 3 条远端分支
git merge --ff-only origin/main     # main: a2b03b1e -> 00297417
```

| 分支 | 处置 | 本地落点 |
| --- | --- | --- |
| `main` | 快进 `a2b03b1e → 00297417` | 主工作区 `.` |
| `codex/competition-utility-v1` | 已是最新（34968a6b） | `.team-work/competition-utility-v1`（既有） |
| `codex/model-outcomes-v1` | 已是最新（6d7d268e） | `.team-work/model-outcomes-v1`（既有） |
| `codex/hangma-shiji-v1` | 新分支，建本地跟踪 + 工作区 | `.team-work/hangma-shiji-v1` |
| `codex/mirror-ensemble-v1` | 新分支，建本地跟踪 + 工作区 | `.team-work/mirror-ensemble-v1` |
| `codex/wengu-v1` | 新分支，建本地跟踪 + 工作区 | `.team-work/wengu-v1` |

工作区可在用完后退掉：`git worktree remove .team-work/<名字>`。

## 2. 分支谱系（当前观察）

| 分支 | 分叉于 main | 自建提交数 | HEAD | 最后提交时间 |
| --- | --- | ---: | --- | --- |
| `main` | — | — | `00297417` | 2026-09-15 约 08:45 |
| `codex/model-outcomes-v1` | `f596cb02` | 144 | `6d7d268e` | 2026-09-14 09:02 |
| `codex/hangma-shiji-v1` | `f596cb02` | 174（含 model-outcomes 全部 144 + 自有 30） | `0d798975` | 2026-09-15 08:15 |
| `codex/competition-utility-v1` | `f596cb02` | 15 | `34968a6b` | 2026-09-11 19:57 |
| `codex/mirror-ensemble-v1` | `4b9947ff` | 8 | `bc2b0798` | 2026-09-15 04:56 |
| `codex/wengu-v1` | `4b9947ff` | 10 | `631aad6a` | 2026-09-15 08:09 |

`codex/hangma-shiji-v1` **完整包含** `codex/model-outcomes-v1`（`git merge-base --is-ancestor 6d7d268e codex/hangma-shiji-v1` 成立）。两者可视为"模型主线 + 拾级扩展"一条线。

## 3. 主线共享底座（main 已在库，所有分支复用）

| 模块 | 关键文件 | 作用 |
| --- | --- | --- |
| `src/hangma_bot/learning` | `encoding.py`、`key_encoding.py`、`sequence_encoding.py`、`sequence_policy.py`、`sequence_model_artifact.py`、`outcome_model.py` | 训练/推理共用编码、网络定义与制品兼容性检查 |
| `src/hangma_bot/offline` | `replay.py`、`replay_check.py`、`observation_audit.py`、`evaluate.py`、`evaluation_statistics.py`、`artifact_store.py`、`postgame.py` | 回放、观察审计、完整桌赛评估与统计（配对/聚类 bootstrap） |
| `src/hangma_bot/simulation` | `engine.py`、`state.py`、`interface.py`、`artifacts.py`、`projection.py`、`shuffle.py` | 完整世界推进与固定牌山 |
| `src/hangma_bot/policy` | `heuristic_v2.py`、`v2_hu_upgrade.py`、`hu_upgrade.py`、`sequence_model_policy.py`、`outcome_policy.py`、`safe_fallback.py` | 线上决策接缝与稳定版本 V2／Tier-A |
| `src/hangma_bot/competition` | `outcome_utility.py` | 积分结果到赛事目标的转换 |
| `prebuilt/sequence-policy-models` | `2048-projected/`、`4096-direct/`、`4096-projected/`（各 `model.pt` 713,492 B + `manifest.json`，**已入库**） | 三个可部署序列策略候选 |
| `datamart/` | `build.py`、`compare_arms.py`、`serve.py`、`schema.sql`、`strategy-map.json` | 对局数据商城与多臂配对比较器 |
| `scripts/` | `evaluate.py`、`export_sequence_model.py`、`run_test_room.py`、`run_auto_match.py`、`fetch_leaderboard.py` | 评测、导出、测试房与自由赛运行入口 |

## 4. 逐分支盘点

### 4.1 `codex/model-outcomes-v1` — 模型训练主线（体量最大）

**定位**：从真实牌谱与模拟反事实分支训练结果/策略模型的一整轮探索。规模：自建提交 144，新增文件 1,291，其中 `review/` 新增 **1,210 个文件、65 个实验目录**，`tests/` 27，`doc/` 10，`src/` 20。

**新增源码组件（`git diff --diff-filter=A f596cb02..codex/model-outcomes-v1 -- src/`）**

| 组件 | 职责 | 复用价值 |
| --- | --- | --- |
| `learning/sequence_policy.py`、`sequence_encoding.py`、`sequence_rule_value.py` | 序列 Actor-Critic 与序列编码、规则价值分支 | 高（部署主线在用） |
| `learning/outcome_network.py`、`model_artifact.py`、`ranking_probe.py` | 结果网络、制品封装、排序探针 | 高 |
| `learning/discard_actor.py` + `policy/discard_actor.py` | 弃牌动作头（独立行为克隆分支）与线上包装 | 高 |
| `offline/model_training.py`、`aux_model_training.py`、`discard_training.py` | 训练循环（含 KL 约束一步改进、辅助头） | 中高 |
| `offline/model_sampling.py`、`model_environment.py`、`real_model_data.py` | 采样、模型环境、真实牌谱数据装配 | 高 |
| `offline/key_decisions.py`、`logical_policy.py`、`ranking_probe.py`、`replay_metadata.py` | 关键窗口选取、逻辑策略装配、排序探针、重放元数据 | 中 |
| `scripts/model_python.sh` | 训练统一 Python 入口 | 中 |

**训练装置（`review/` 下，已入库 .py 共 641 个）**：核心是 `review/paired-action-learning-2026-09-13/`（`fit_pipeline.py`、`fit_core.py`、`fit_data.py`、`fit_freeze.py`、`fit_evaluate.py`、`fit_diagnostics.py`、`fit_audit.py`）的"配对动作回报拟合"流水线，以及 `review/portable-policy-fit-2026-09-13/`（可移植学生包训练与完整桌赛消费）。其余为分项实验：`sequence-bc-2026-09-12`、`sequence-ppo-2026-09-12`、`model-scale-2026-09-13`、`exploration-init-2026-09-12`、`residual-engineering-2026-09-12`、`rule-residual-2026-09-12`、`mixed-continuation-fit-2026-09-13` 等。

**实际训练过的模型与规模（当前观察；数字来自 `review/sequence-bc-2026-09-12/RESULTS.md`、`review/sequence-ppo-2026-09-12/TRAINING-RESULTS.md`、`review/expert-intake-2026-09-14/EXPERT-EXPERIMENT.md` 等，均在 shiji 工作区可查）**

| 训练对象 | 网络／方法 | 规模与关键数字 | 结果 |
| --- | --- | --- | --- |
| 首版 outcome 结果模型 | 候选均值 MLP：7,994 维观察 + 159 维候选 → hidden 64，**530,436 参数**（紧凑双头版约 15,909 参数） | 目标 = 四家整数积分守恒 MSE | 最佳 MSE **127.6589**，**劣于**零预测 126.9568 与常数 127.0963；8 根完整桌赛 **−29.56** [−34.81, −23.66] |
| 真实牌谱 outcome／行为约束 | 同网络，加入已确认动作行为辅助 | 真实数据纯回归／行为约束／补 Pass+等待三版 | 分别 **−28.3125**／−14.84375／**−11.40625** 分/桌（区间均不含 0 或接近 0） |
| 全动作行为克隆 | `visible-sequence-actor-critic-v1`（共享可见序列 Actor-Critic，175,554 参数） | 500,557 个选择窗、4 遍、62,921 次更新；开发一致率 **95.0548%**；终端制品 `sequence-bc-500k-v1/epoch-4.pt`（约 3.94 GB） | 两池均值 +1.8594／+2.6719 分/桌，**区间跨零** |
| PPO 交互训练 | 标准截断 PPO + 相对冻结 BC 克隆的 KL + 熵项 + 价值平方误差 | 目标 = 本人完整八单局实际桌内积分（γ=λ=1，积分 /100）；100,160 选择窗、295 批、3,430 更新、1,180 桌 | 四项比较区间**全部跨零**（rich +1.1172、mixed +4.1289） |
| PPO 续训 / 轨迹权重 | 同上 + 窗口权重 | 2,048 根、33,787 窗、24 遍、3,072 更新、训练 730.90 秒、175,488 个可训练策略路径参数 | 九项同时区间**全跨零** |
| 专家监督 | 同一序列网络，交叉熵 + 0.1×初始化分布差异 | 47 房 / 470 场真实牌谱 → **41,266** 条合法多候选样本（训练 33,866／开发 7,400）；AdamW lr=1e-4，每臂 2,048 步 | rich +6.03、mixed **−7.28**，方向相反，六项区间跨零 |
| 参数插值 H/L/M | **不训练新参数**，同名参数双精度加权 α=0.25/0.50/0.75 | H = 75% 专家参数 + 25% V2 控制参数 | 选中 α=0.75（H）；六项区间跨零；三池门禁未过 |
| 条件教师学生 | 4 个序列学生，相同网络与随机初值 | 各 48 根训练 / 16 根留出，各 144 次更新（共 576） | 六项筛查**未通过** |
| 可见动作非线性估值 | 冻结父网络前端 128 维表示 + 复用动作头 | 仅 **8,320** 个回归头参数，四折各 1,440 次更新（共 5,760） | 误差优于零预测/线性控制，但选中标签均值 **−0.1474 分**，四折仅两折为正 |

**注意**：PPO 是“**一个学习者对三家冻结完整 V2**”（或混合池加入冻结克隆），**不是四家自博弈**——训练与评估身份见 `review/sequence-ppo-2026-09-12/EVALUATION.md`。

**本地未入库制品**：该工作区 `artifacts/` 约 **1.5 GB**（评估/检查点），`runs/` 亦本地。**未入库，克隆分支后不能直接重建**。

**结论（当前观察）**：8/8 项主要比较的同时 95% 区间全部跨零；2048/4096 规模点相对 V2 点估计 +1.28～+3.33 分/桌但均不显著（[模型训练独立审计](../../../doc/implementation/notes/model-training-independent-audit-2026-09-13.md) §3、§6）。

### 4.2 `codex/hangma-shiji-v1` — 模型主线 + 拾级（已终止）

**定位**：在模型主线上追加"特殊状态/普通响应/持白弃牌/其他弃牌"四类窗口的有界组合策略筛选（B 为启发式基线 `V2HuUpgradePolicy`，H 为冻结研究模型），并系统排除各类条件教师路线。自有 30 个提交带来 355 个 `review/` 新文件、**21 个新实验目录**。

**相对 model-outcomes 新增的源码组件**

| 组件 | 职责 |
| --- | --- |
| `src/hangma_bot/learning/observed_sequence_encoding.py` | H 使用的`visible-observed-public-sequence-v2` 部分历史编码（与主线 `visible-key-public-sequence-v1` 不同） |
| `src/hangma_bot/simulation/sampling.py` | **可见条件世界采样**（从 `PlayerObservation` 采出与观察一致的世界，附自归一化重要性权重） |
| `scripts/run_shiji_screening.py` | 拾级初筛/复筛启动器 |

**已入库模型制品**：`artifacts/hangma-shiji-v1/models/H.pt`（713,184 B，SHA-256 `0ee1c740…82a4`，175,554 参数：width64/layers2/heads4/ffn256）+ `clone/model.pt`（137,085 B）+ `import.json`／`origin-manifest.json`／`origin-plan.json`／`selected-candidate.json`（迁移证据，见 [IDENTITY.md](../../../.team-work/hangma-shiji-v1/review/hangma-shiji-v1/IDENTITY.md)）。

**新增实验目录**：`bounded-competition-route-2026-09-14`、`visible-world-sampling-2026-09-14`、`visible-world-teacher-2026-09-14`、`visible-world-order-2026-09-14`、`conditional-teacher-learning-2026-09-14`、`control-teacher-learning-2026-09-14`、`conditional-noise-components-2026-09-14`、`conditional-reliability-2026-09-14`、`conditional-ridge-2026-09-14`、`expert-intake-2026-09-14`、`expert-blend-2026-09-14`、`trajectory-weight-2026-09-14`、`initial-hand-control-2026-09-14`、`h-disagreement-2026-09-14`、`h-future-value-2026-09-14`、`fixed-h-expansion-2026-09-14`、`public-terminal-value-2026-09-14`、`visible-action-value-2026-09-14`、`hangma-shiji-v1`（可运行筛选装置：`run.py`、`policies.py`、`tables.py`、`budget.py`、`workers.py` + 4 个测试）、`hangma-shiji-next`（判定与核账脚本 4 个 + 测试 4 个）。

**额外 30 个提交的主题链（当前观察）**：可见世界采样 → 起手顺序条件计数 → 完整桌赛条件教师 → 条件教师学生／岭回归／重复可靠性／噪声分解 → H 分歧与专家监督／参数混合／轨迹权重／非线性估值 → B/H 四类开关组合初筛与复筛 → 失败证据快照与停止判决。

**关键工程数字**：第一版可见采样 44 窗只有 39 窗拿满 4 世界（5 个长历史窗耗尽 1,000 次尝试，5,353 次拒绝全为 `known_draw_mismatch`），ESS 中位 2.28；加入起手顺序精确动态计数后 **44/44 拿满、拒绝降到 0、ESS 中位 2.45**。全量教师覆盖 64 根、1,562 分歧、6,248 世界、12,496 次首动作分叉，全量核账 5,473,067 次策略动作、7,521,308 条完整事件；但 **417/1,562 窗 ESS < 2**，且 rich/mixed 半组方向相反（185/781 与 203/781）。

**结论（当前观察，[STOP-DECISION.md](../../../.team-work/hangma-shiji-v1/review/hangma-shiji-next/STOP-DECISION.md)）**：初筛 16,384 桌、复筛 16,384 桌全量记录核账通过，**两次都没有选出超过已有 H 的组合**；最好组合 G13 相对 H 为 −0.3396 分/桌，`nominated_combination` 为 `null`。**"本次停止由效果门槛触发，开发预算没有耗尽"**：合计占用 4.4563 作业小时，12 小时桶剩余 8.4520；未租外部算力、未扩到 96 小时预算。

### 4.3 `codex/mirror-ensemble-v1` — 万镜推演（决策时搜索，已证伪）

**定位**：**不训练更强策略模型**，改为在动作窗口内用模拟器对候选做蒙特卡洛重排；学习降级为搜索的供给线。方案见 [路线 README](../../../review/decision-time-search-route-2026-09-14/README.md)。

**组件**：源码改动只有 `src/hangma_bot/simulation/` 5 个文件——新增 `sampling.py`（可见条件世界采样：反向可见约束采样 + 自归一化重要性权重 + 正向规则重演验收），并修改 `__init__.py`、`engine.py`、`interface.py`、`projection.py`；其余全部可运行装置在 `review/decision-time-search-route-2026-09-14/` 下：`stage0a_bound.py`（一步上界与噪声分解）、`stage0b_bench.py`（截断 rollout 吞吐基准）、`stage1_mirror_policy.py`（原型策略）、`stage1_run.py`（分片运行器 + 预登记判定分支）、`stage1_report.py`、`_check_report.py`，以及 `stage0a/`、`stage0b/`、`stage1/{smoke,smoke2,smoke2b,run-64}/` 的原始结果。

**复用前置坑（当前观察）**：`stage0a_bound.py` 的输入路径 `ART` 被**硬编码**为 `/Users/liyang/hangma-bot/.team-work/model-outcomes-v1/artifacts/.../portable-label-scale-4352-v1/local/nodes`，迁移复用前必须先改成可配置路径；`stage1_run.py` 默认 `workers=10`，复现本次 4 分片必须显式传 `--workers 4`。

**制品卫生问题（当前观察）**：`stage0b/stage0b-result.json` 与 `stage0b-result.python-fallback.json` 的 git blob 哈希相同（`eaa32eaf…`），内容完全一致（554.7 动作/秒、75.1 ms），而 `STAGE0B-RESULTS.md` 叙述 fallback 为 122/563——**该 fallback 档案不能作为独立的 Python 后端基准使用**。

**注意（当前观察）**：main 只有该路线的**结论文档与 `report.json`**（`review/decision-time-search-route-2026-09-14/`），**没有上述可运行脚本**；要用工具链必须切到该分支。

**分阶段门禁（当前观察）**

| 阶段 | 判定 | 关键数字 |
| --- | --- | --- |
| Stage 0a 一步上界 | 过门禁 | 4,222 窗 / 256 根；事后神谕 +15.50 分/窗（CI [14.00, 17.08]）；置换噪声地板 +12.47（CI [12.36, 12.57]）；**净信号 +3.03**（CI [1.43, 4.73]）；神谕改选率 45.7% |
| Stage 0b 吞吐 | 过门禁 | C 原生后端 **554.7 / 563.8 动作/秒**；`sample_observation(W4)` 中位 **75.1 ms**、完整率 100%、ESS 中位 3.70 |
| Stage 1 原型 + 战役 | **未通过** | 见下 |

**结论（当前观察，[STAGE1-RESULTS.md](../../../review/decision-time-search-route-2026-09-14/stage1/run-64/STAGE1-RESULTS.md)）**：最小设计被证伪，配对完整桌赛差 **−15.367 分/桌**，95% CI [−24.309, −7.176]（64 根 × 4 换座 × 双角色 = 512 桌）。原因是"赢家诅咒"：重排窗估计增益中位 8.9 分但真实效应为负，世界权重有效样本数中位仅 1.93。按预登记分支 (c) 收口，**不重跑、不自动升级更深搜索**。

### 4.4 `codex/wengu-v1` — 温故（牌谱驱动价值回归，门槛二未通过）

**定位**：只从已打完的真实对局学习，不做反事实分支、不做自对弈。方案见 [独立路线 README](../../../review/independent-route-2026-09-14/README.md)。参照 Mortal 的"蒙特卡洛回报回归"离线路线。

**组件**

| 组件 | 职责 |
| --- | --- |
| `src/hangma_bot/offline/wengu/land.py` | 官方牌谱落库（910 场 → 7,279 单局行，`coverage=full_history`，得分守恒） |
| `src/hangma_bot/offline/wengu/windows.py` | 决策窗口提取（复用重放状态机；实际动作落在合法候选内 4196/4201） |
| `src/hangma_bot/offline/wengu/dataset.py` | 数据集装配 |
| `src/hangma_bot/offline/replay_check.py` | 重放一致性核验 |
| `scripts/wengu_land.py`、`wengu_gate1.py`、`wengu_cf.py`、`wengu_gate2a.py`、`wengu_gate2_rank.py`、`wengu_forkmap.py` | 落库、门槛一、反事实生成、门槛二两种判定、fork 位置地图 |

**各门槛结果（当前观察）**

| 门槛 | 结果 | 关键数字 |
| --- | --- | --- |
| A0 牌谱落库 | 通过 | 910 场 / 91 房间 / **7,279 单局**；7,279 full_history、1 observed、跳过 1；四家分数守恒 |
| A0 窗口提取 | 通过（有缺口） | 4,201 个决策窗（出牌 882、碰 2,502、吃 817）；**4,196/4,201 = 99.88%** 实际动作落在合法候选内；5 个不一致**全是明杠**（赛后无牌墙，`remaining_tile_count=None`） |
| 门槛一（单局结果预测优于常量基线） | **通过** | R²=0.046；MSE 改善 +7.17，95% CI [+5.30, +9.25]；样本 27,345（训练 21,884／留出 5,461）；负对照 R²=0.00048、CI [−0.18, +0.32] 跨零 |
| 早杀测试（同窗反事实离散度） | 通过 | 30/30 有效试验；候选结局极差均值 **30.9 分**、中位 32、合并标准差 **13.56**；零极差 13.3%；同 seed 重跑逐字节一致 |
| fork 位置地图 | 完成 | 初版全零是"focal 恒等于 dealer"的混淆；解耦后 48 次试验、6 个位置、283 个窗口，零信号占比 43.8%—58.3%，**无随 k 递减梯度** |
| 门槛二（同窗排序优于父策略 V2） | **未通过** | 见下 |

**结论（当前观察，[门槛二判决](../../../.team-work/wengu-v1/doc/implementation/notes/wengu-gate2-verdict-2026-09-14.md)）**：模型不是纯噪声（真实标签优于打乱标签负对照），但**远不如启发式**：模型−随机 +0.30 对 V2−随机 **+1.84**；标签从 2,428 提到 6,036（2.5 倍）后增益反而从 +1.30 降到 +0.30，**"再攒更多标签就会好转"未获支持**。判定"路线在本项目算力下停止"。
**复用前必须修的数据缺口（当前观察，来自 A0 核账）**

| 缺口 | 数字 | 影响 |
| --- | --- | --- |
| 杠候选系统性缺失（**已修复**） | 赛后无牌墙导致 `remaining_tile_count=None`，规则侧保守剔除**全部三类杠**——3 场冒烟里的 5 处不一致恰好全是明杠只是抽样假象，全量 1,250 次杠事件（明杠 606／补杠 406／暗杠 238）都受影响 | 已于 2026-09-15 在 `offline/replay_check.py` 修复（见提交 `34702f8b`）；60 场 / 87,377 窗口上杠类不一致 77 → 0 |
| timeout 与 pass 未分离 | `timeout=630,815`、`pass=380,723`，**两者合计是弃牌数的 3.8 倍**；`action_sample_rows` 最终只用 tile 做 `action_feature`，未知/无 tile 返回全零，**未在此处过滤 timeout** | 动作标签与特征被污染 |
| `guide_version` 混用 | v15=3,519、v27=320、v28=3,440 | 训练前必须分层或过滤 |
| `compact` 曾在 macOS 上静默失效 | `spawn` 不继承全局变量；修正后样本 28,061 对 27,345 | 该次"排除数为 0"是直接 `continue` 未登记，不是真的没有排除 |
| 目标口径 | 用本单局净分，约一半窗口本人分数根本不变 | 下一版应考虑终局名次口径 |

另外，纯牌谱代理（观察-only vs 观察+动作 one-hot 的嵌套对照）的 full MSE 增益 +0.134 [−0.050, +0.327]、compact +0.101 [−0.078, +0.292]，**两者都跨零**——这条已判为"纯牌谱下不可判定"，不要再当作门槛二证据。

**失败的适用范围（原文明确限定）**：模型是 458 维线性岭回归；标签量级 6 千条；fork 点仅在焦点座位第一个多候选窗口；续打对手是 V2；计算预算 2 个 worker。**不能推出"麻将价值学习不可能"或"非线性模型一定不行"。**

### 4.5 `codex/competition-utility-v1` — 赛事目标与资格线效用

**定位**：把积分/排名事实转换为**赛事目标**（资格线压力、主动追分、最后机会足额收口），不训练新网络。规模：15 个提交、95 个文件、14,001 行。

**新增源码组件**

| 组件 | 职责 |
| --- | --- |
| `competition/qualifier.py` | 资格线参考目标与压力计算 |
| `competition/qualifier_sufficiency.py` | 条件足额判定 |
| `competition/terminal_qualification.py` | 终榜晋级范围（最好/最坏同分名次） |
| `offline/qualifier_{scenarios,progress,pursuit,route_diagnostic,action_evidence,evidence_robustness,heuristic_eval,last_chance,last_chance_eval,pursuit_eval,sufficiency_eval}.py`、`offline/closed_ledger_hu.py` | 情景评估、本人进度核算、追分对照、机制诊断、动作证据、稳健性、启发式与足额评测、封闭账本 |
| `policy/qualifier_route.py`、`policy/qualifier_heuristic.py` | 线上目标驱动策略与启发式包装 |

**交接与证据**：`doc/implementation/handoffs/competition-utility-v1-*.md` 共 14 篇，加 `-evidence/` 下 `reports/`（回归与验证 JSON/日志）与 `runs/`（4 个完整桌赛 run 的 manifest+report）。测试 16 个文件。

**结论（当前观察，[roadmap](../../../.team-work/competition-utility-v1/doc/implementation/handoffs/competition-utility-v1-roadmap.md)）**：C1/C2 已实现并通过本机回归；C3 完整桌赛评测**效果验收未通过**（48 分目标开发池 7/128 → 独立验证 7/128；144 分两池均无达标；实际发生 32 次追分改选但门禁未过）；C4 未交付，保持稳定线上策略。方向已修订为"连续压力数学模型"，**明确"首版赛事模块不要求训练新的神经网络"**。

## 5. 可复用资产汇总

### 5.1 直接可用（已入库、跨分支共享）

| 资产 | 位置 | 说明 |
| --- | --- | --- |
| 三个序列策略候选 | `prebuilt/sequence-policy-models/{2048-projected,4096-direct,4096-projected}/model.pt` | 各 713 KB，含 `manifest.json`；main 即可用 |
| 完整桌赛配对评估 | `src/hangma_bot/offline/evaluate.py`、`evaluation_statistics.py` | 同牌山、换座、根聚类 bootstrap |
| 可见条件世界采样 | `src/hangma_bot/simulation/sampling.py` | mirror 与 shiji 各自独立实现；建议择一并统一 |
| 反事实续打标签管线 | `review/paired-action-learning-2026-09-13/`（model-outcomes/shiji 均在库） | 同墙分叉、确定性可复现 |
| 拾级筛选装置 | `review/hangma-shiji-v1/{run.py,policies.py,tables.py,budget.py,workers.py}` | 16 组合 × 完整桌赛的有界筛选 + 预算记账 |
| 拾级判定与核账 | `review/hangma-shiji-next/{confirmation_stats,factorial_diagnostics,paired_tables,stage_ledger}.py` + 4 测试 | 可复用的统计判定与核账工具 |
| 搜索原型工具链 | `review/decision-time-search-route-2026-09-14/{stage0a_bound,stage0b_bench,stage1_mirror_policy,stage1_run,stage1_report}.py` | 仅在该分支；含预登记判定分支机制 |
| 温故牌谱落库与窗口提取 | `src/hangma_bot/offline/wengu/{land,windows,dataset}.py` + `scripts/wengu_*.py` | 官方牌谱→决策窗口的干净管线 |
| 赛事目标组件 | `src/hangma_bot/competition/qualifier*.py`、`terminal_qualification.py`、`policy/qualifier_route.py` | 需切到 `codex/competition-utility-v1` |
| 模型制品 H | `artifacts/hangma-shiji-v1/models/H.pt`（+ clone） | 175,554 参数，仅在该分支 |

**序列策略制品卡片（当前观察，读自 `prebuilt/sequence-policy-models/2048-projected/manifest.json`）**

| 字段 | 值 | 说明 |
| --- | --- | --- |
| `schema` | `sequence-policy-deployment-v1` | 部署包格式；主线 `learning/sequence_model_artifact.py` 按此加载 |
| `network_version` | `visible-sequence-actor-critic-v1` | `width=64`、`layers=2`、`heads=4`、`feedforward=256` |
| `feature_version` | `visible-key-public-sequence-v1` | **与 H 的 `visible-observed-public-sequence-v2` 不同**，两者不可互换 |
| `action_version` | `candidate-visible-relations-conditional-value-v2` | 动作编码 |
| `steps` / `training_roots` | 3072 / 2048 | 训练步数与训练牌山数 |
| `parent_identity` | `choices_collected=200259`、`updates=6890` | 父模型身份与采集量 |
| `rule_config` | `hangma-mvp-v10-public-counts`、`base_score=1`、`you_cai_bi_kao=false` | 评测所用规则配置 |
| `release_gate` | **false** | 未过发布门禁 |

制品自带声明（原文摘抄）：**"未证明优于或不劣于 V2：正式开发比较的同时区间全部跨零。本包用于真实环境实测取数，不是已验证的强度提升。"**

### 5.2 数据资产

| 资产 | 位置 | 状态 |
| --- | --- | --- |
| 夜间自由赛真实牌谱 | `datasets/derived/auto-match-v10-2026-09-10/`（`games-v10.json` 470 桌、`features-v10.jsonl` 3,760 局、`decisions-summary.json` 约 15.5 万决策窗） | 已入库 |
| 榜单标注 | `datasets/leaderboard/game-annotations.jsonl` | 已入库 |
| 官方赛后牌谱 | 440 场 / 7,810 单局 / 131,673 弃牌决策，其中榜单玩家 37,402 条（21 人） | 已入库；**至今未用于模仿学习** |
| 训练派生数据（学生包、分支标签） | 各工作区 `artifacts/`（model-outcomes 约 1.5 GB） | **未入库，本地专属** |
| 拾级筛选原始记录 | 32,768 桌 | 在 shiji 工作区 |

### 5.3 死路（不要重复，附原因）

| 尝试 | 结论与证据 |
| --- | --- |
| 在近乎确定的父策略上做一步 KL 策略改进并靠扩数据改善 | oracle 改选上界 198/20900 = 0.95%；320→640→1280→2048→4096 点估计无单调上升，4096 相对 2048 四项区间全跨零 |
| 用整桌配对差作标签 | 方差是本单局口径的 3.03 倍；51.87% 标签恰为零；原分支记录仍在盘上，零模拟成本可改 |
| 纯启发式参数继续打磨 | 已封口，多个实验臂证伪（[启发式收尾](../../../doc/implementation/notes/heuristic-research-closeout-2026-09-11.md)） |
| 均匀世界 × 少世界数 × 手工阈值的决策时搜索 | −15.37 分/桌 [−24.31, −7.18]，最小设计被证伪 |
| 458 维线性岭回归 + 单局净分目标 + 开局窗口排序 | 模型−随机 +0.30 对 V2−随机 +1.84；加 2.5 倍标签反降 |
| 四类窗口 B/H 组合切换 | 14 组合 + 复筛均未超过 H |
| 用账号身份做对手画像 | 同账号两夜间胡率变化达 ±25pp，池均值仅 +0.46pp |
| 单隐藏世界 outcome MLP + 总 MSE，并直接部署 | MSE 劣于零预测（127.6589 对 126.9568）；8 根完整桌赛 −29.56 分/桌 |
| 用行为交叉熵与结果 MSE 共头直接部署 | 未执行候选没有结果标签；加行为约束后仍为 −14.8 分/桌量级 |
| 在同一定点配对数据上继续 Adam/L-BFGS/KL 温度搜索 | 局部梯度达标但完整桌赛无提升 |
| 320→640→1280→2048→4096 只扩根数 | 所有主要比较区间仍跨零 |
| 全动作 PPO（单学习者对三家冻结 V2） | 四项完整桌赛比较区间**全部跨零**（rich +1.1172、mixed +4.1289），未构成改进 |
| 真实专家监督模仿（41,266 条样本） | rich +6.03、mixed **−7.28**，方向相反；六项同时区间跨零 |
| 父模型参数插值 H/L/M（α=0.25/0.50/0.75） | 六项区间跨零；扩到三池仅 rich 下界为正，三池门禁未过 |
| 轨迹总量权重 | 九项同时区间**全跨零** |
| 条件教师标签 + 序列学生／184 维条件岭回归 | 条件学生六项、岭回归八项筛查均未通过；教师重复波动占总平方量 0.9696／0.9182 |
| 可见动作非线性估值（仅 8,320 个回归头参数） | 误差优于零预测与线性控制，但**选中标签均值 −0.1474 分**，四折仅两折为正 |
| 把条件教师窗口的最大候选值当可达上限 | 约 12 个候选、组内标准差约 13.6 分时，取最大值本身就会产生约 **20 分** 的选择假象 |

## 6. 提问回答

### 6.1 他们是否都以训练一个 RL 模型为目标？

**不是。** 5 条分支里只有 2 条以"训练模型"为目标，且这两条做的是**离线/带约束的策略改进，不是完整在线强化学习**。

| 分支 | 是否训练神经网络 | 属于哪种训练范式 |
| --- | --- | --- |
| `model-outcomes-v1` | **是** | ①**全动作行为克隆**（500,557 选择窗 / 62,921 更新，开发一致率 95.05%）；②**PPO 策略梯度**（`review/sequence-ppo-2026-09-12/objectives.py`，目标 = 完整八单局实际桌内积分，γ=λ=1；含截断代理损失、价值平方误差、相对冻结 BC 克隆的 KL、熵项；100,160 选择窗 / 295 批 / 3,430 更新 / 1,180 桌）；③配对动作回报 + **KL 约束的一步策略改进**（价值头被冻结且未进损失）。**但 PPO 是"一个学习者对三家冻结 V2"，不是四家自博弈**；无全局奖励预测、无训练期特权信息引导、无档位型离线评估 |
| `hangma-shiji-v1` | **继承** model-outcomes 的模型，自身只做**组合策略筛选**与条件教师/岭回归诊断 | 有界策略筛选与统计判定，未训练新端到端策略 |
| `mirror-ensemble-v1` | **否** | **决策时蒙特卡洛搜索**（只重排候选，不训练）；原文定位"不再把离线训练更强策略模型作为提升主干" |
| `wengu-v1` | 否（458 维线性岭回归） | **牌谱驱动的离线价值回归**；原文明确"不把自对弈在线强化学习作为变强主路径" |
| `competition-utility-v1` | **否** | 赛事目标/资格线效用工程；原文"首版赛事模块不要求训练新的神经网络" |

另一条硬证据（当前观察）：在所有分支的 `src/` 内 grep `ppo`、`policy_gradient`、`clip_ratio`、`self_play` 均无命中——**没有任何 PPO/在线 RL 进入生产模块**。PPO 只作为研究流水线存在于 `review/sequence-ppo-2026-09-12/`（`objectives.py` 声明 `OBJECTIVE_VERSION = 'sequence-ppo-current-to-bc-kl-v1'`，含 `clip_epsilon`、`reference_kl_weight`、`entropy_weight`、`value_weight` 四个显式冻结的损失权重）。

### 6.2 走不通的主要阻碍是不是时间和计算资源不足？

**部分成立，但不是主要阻碍，也不解释全部失败。** 需要拆成两层。

**（a）算力确实是结构性硬约束（成立）**

| 事实 | 数值 | 来源 |
| --- | --- | --- |
| 本机 | 两台 Apple Mac（M4 Pro 48GB／M5 Pro 48GB），无 CUDA 集群 | [Apple Silicon 算力调研](../../../doc/implementation/notes/apple-silicon-compute-research-2026-09-07.md) |
| Suphx 单次 RL 消融 | 44 张 GPU × 2 天（约 2,112 GPU 小时）；离线评估另需 20 张 K80 × 2 天 | [Suphx 论文](https://arxiv.org/abs/2003.13590) |
| 差距量级 | 与本机相差 **2–3 个数量级** | [万镜推演路线 §2](../../../review/decision-time-search-route-2026-09-14/README.md) |
| 自对弈可行性 | Kanachan 作者估算 Suphx 规模自对弈（150 万半庄）在单张 RTX 3090 上约 **5 年**、电费约 40 万日元 | [牌谱驱动路线文献](../../../doc/implementation/notes/log-driven-route-literature-2026-09-14.md) §1.2 |
| 测量功效 | 实测 `MDE ≈ 234/√H`；40 房/臂一夜 MDE 8.07；检出每桌 +2 分需 **约 900–1,660 个独立牌山** | [训练方向回顾](../../../review/training-direction-2026-09-14/README.md) §6.4 |
| 本轮实际机时 | 反事实标签生成：1,408 根墙钟 **13,428.16 秒**、CPU **80,253.74 秒**；PPO 追加批 2,253.68 秒；并行小批约 1.73 倍加速 | `doc/implementation/model-outcomes-v1/TRAINING-OVERVIEW.md`、`review/model-scale-2026-09-13/DATA-COMPLETE.md` |

**（b）但直接卡住这一轮训练的，是方法与学习信号问题（原文自述，成立）**

| 卡点 | 数值 | 是否算力问题 |
| --- | --- | --- |
| 父策略熵坍塌 | 父模型最大动作概率中位数 0.999997；62% 窗口 ≥0.999；让正标签候选反超所需逆温度 β=412.24，实际 2.506（差 165 倍） | **否**。原文："扩数据、放宽更新约束都不会改变结论" |
| 标签口径与契约不一致 | 实际用整桌配对差，方差为本单局口径的 3.03 倍；51.87% 标签为零 | **否**。零模拟成本可修 |
| 结果模型主线从未验证 | 价值头 MSE 0.0802 差于零预测 0.0779、线性基线 0.0755 | **否**。这是实现与契约漂移 |
| 评估设计事前不可判定 | 同一 128 根开发集被 ≥4 批消费、累计 ≥24 项主要比较，campaign 级多重性未计 | **部分是**（要 900–1,660 根才能独立确认） |
| **原文直接判定**（候选取舍，而非算力） | 原话：**「瓶颈是候选取舍的学习质量，当前不是 GPU 或训练时间」**；另有「预算停止，不能称收敛」 | **否**。这是项目自己给出的卡点定性 |
| PPO 价值头 | 价值误差 0.08615 劣于零预测 0.08286，解释方差 **−0.0402** | **否**。奖励归因未建立 |
| 配对动作监督 | 1,344 桌中新模型相对 V2 **−24.92 / −26.46 分/桌**（明显退化） | **否**。标签·投影·接管错位 |
| Suphx 突破组件缺位 | 动态目标熵、全局奖励预测、训练期特权信息引导、自对弈双方共同演化、档位型离线评估——逐项对照**全部为"否"**（PPO 有固定熵项，但不是 Suphx 的"按近期经验熵与目标熵之差动态调整 α"） | **否**。是配方缺失，不是算力 |

**（c）两个反例说明"算力不足"不能作为统一解释**

1. **拾级路线是预算未耗尽就停止的**：`STOP-DECISION.md` 明确"本次停止由效果门槛触发，开发预算没有耗尽"——合计 4.4563 作业小时，12 小时桶剩余 8.4520；未租外部算力。它停是因为没有组合超过 H。
2. **温故把标签加到 2.5 倍，效果反而下降**（+1.30 → +0.30），且模型−随机 +0.30 远低于 V2−随机 +1.84。原文据此否定"再攒更多标签就会好转"。

**（d）准确表述（工程建议）**

> 算力不足封死了两条路——Suphx 规模的在线自对弈 RL，以及高功效的完整桌赛统计确认；这是本项目无法绕过的结构性上限。
> 但 2026-09-12—09-15 这一轮训练没能产出可上线的更强模型，**直接原因是学习信号与评估设计的方法问题**：父策略熵坍塌使一步改进在结构上无路可走、标签口径取了方差大三倍的分量、结果模型主线从未被验证、评估设计在事前不可判定。
> 因此"主要阻碍是时间和算力不足"**只说对了一半**：换一台更大的机器并不会让 `q ≈ p0` 的那一步训练产生可测效应。项目也已据此改口径——把目标从"证明模型路线有效"改为"有限算力下最大化赛事名次"，并选择让算力直接转化为强度的路径。

## 7. 给后续工作的建议（工程建议）

1. **先修口径，再谈扩量**：改用 `current_returns_by_seat`（本单局配对差）重抽学生包，零模拟成本；重标定 τ 并把"最小有意义积分差"（建议 2 分/桌）在看到结果前冻结。
2. **建立 campaign 级多重比较记账**：确认牌山保留地（512 根）只在未消费前提下定论，避免"同一开发集反复调参直到出现正数"。
3. **复用顺序**：① `wengu` 的牌谱落库/窗口提取管线（干净、已验证）；② `shiji` 的可见世界采样与筛选/核账装置；③ `mirror` 的搜索工具链（注意只在分支上）；④ `competition-utility` 的资格线目标组件（注意共享契约未变更为正式接口）。
4. **唯一未使用的专家数据仍是最大空白**：440 场官方牌谱中的 37,402 条榜单玩家弃牌从未进入模仿学习；使用前须先核验观察可完整重建、超时占比，并按**完整场次**隔离训练/测试。
5. **统一重复实现**：`simulation/sampling.py` 在 mirror 与 shiji 上各有一份独立实现，复用前应先择一合并。
6. **不要重走的死路**见 §5.3；若要重启模型线或搜索线，须按预登记给出新的可证伪依据与完整冻结方案。

## 8. 待确认假设

1. `codex/hangma-shiji-v1` 与 `codex/model-outcomes-v1` 的本地 `artifacts/`（1.5 GB / 856 KB）是否已被完整备份；它们未入库，克隆后不可重建。
2. 各分支的 `review/` 实验脚本是否都能在当前 main 的 `src/` 上直接运行（分支基点较早，存在 API 漂移风险），本次未逐一执行验证。
3. 各分支的大体积产物（训练检查点、逐动作流、学生包、逐世界原始文件）**不在 Git 中**：`sequence-bc-500k-v1/epoch-4.pt`（约 3.94 GB）、`expert-choice-dataset-v1/`、`artifacts/model-outcomes-v1/evaluations/visible-world-*`、`artifacts/wengu-cf*/` 等均需另行备份与校验；仅凭 clone 无法重演。
4. **制品归档缺陷**：`stage0b-result.json` 与其 python-fallback 副本 blob 哈希相同，`STAGE0B-RESULTS.md` 叙述的 122 动作/秒、563 ms 没有对应文件支撑。
5. `mutation-opening.json` 等既有 `review/` 输入跨分支复用，但分支基点较早（`f596cb02`／`4b9947ff`），存在 API 漂移风险。
6. "近半竞争者可能是纯启发式蒙特卡洛"来自用户情报，未由平台证实。
