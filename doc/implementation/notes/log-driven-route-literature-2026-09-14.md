# 牌谱驱动的可持续增量麻将 AI 训练路线：一手来源调研

> 调研日期与所有链接访问日期：2026-09-14。
> 目的：为一个只有两台 Apple Mac（M4 Pro 48GB／M5 Pro 48GB，无 CUDA 集群，见 [apple-silicon-compute-research-2026-09-07.md](./apple-silicon-compute-research-2026-09-07.md)）的杭麻 Bot 项目，判断「从牌谱出发、随数据与时间稳定变强的训练路线」的真实成本与做法。
> 方法：只读一手来源（论文正文、项目官方仓库源码与文档、作者本人公开说明）。**未使用二手综述或博客转述**；确实只能通过镜像读到的官方 Wiki 内容，已在第 5 节逐条标注「镜像来源」。
> 证据标记（沿用本仓库 [AGENTS.md](../../../AGENTS.md) 约定）：
> - **来源事实**：一手来源原文或源码可直接核对。
> - **当前观察**：源码／文档里能查到，但作者没有用文字明说。
> - **工程建议**：本文作者的判断，不是任何来源的结论。
> - **待确认假设**：有间接证据但未找到作者明确陈述。
> - **来源估计**：作者本人的主观估算，不是实测。
> - **未找到**：在本次可访问的一手来源中不存在。
>
> 术语（首次出现）：**行为克隆（Behavioral Cloning，BC，用人类牌谱中的实际选择直接监督模型输出的做法）**、**离线强化学习（Offline RL，只用已有历史数据做策略改进、不与环境在线交互）**、**保守 Q 学习（Conservative Q-Learning，CQL，在离线 Q 学习损失上加一项惩罚、压低未见动作的 Q 值以减少高估）**、**蒙特卡洛回报（Monte Carlo return，把整段实际发生的回报直接相加作为回归目标，不做时序差分自举）**、**近端策略优化（Proximal Policy Optimization，PPO，一种带裁剪的策略梯度算法）**、**复式对局（duplicate mahjong，同一副牌山分别换座重打，用来压低麻将随机性）**。

## 1 结论

### 1.1 一句话定性

| 项目 | 路线定性 | 是否需要自对弈模拟 | 一手来源标注的计算量 |
| --- | --- | --- | --- |
| Mortal | 人类牌谱上的**蒙特卡洛回报回归（Q 学习）+ CQL 保守项 + 辅助排名头**，另有把新对局排空回训练缓冲的「在线阶段」 | 离线阶段不需要；在线阶段需要，但规模未公布 | **未公布训练硬件与时长**；只有推理／模拟吞吐（RTX 4090 + Ryzen 9 7950X、batch 2000 时约 4 万半庄/小时） |
| Kanachan | 先**行为克隆**，再到**离线 RL（IQL／CQL／ILQL）**的分阶段课程微调 | 不需要（这正是作者选离线 RL 的理由） | **未公布训练一次的总算力**；模型卡给出 4300 万条样本、1 epoch、batch 4096、LAMB |
| Mahjax（arXiv:2605.20577v1） | 先用启发式数据做 **BC**，再用**带 KL 约束的 PPO** 微调的两阶段 | 需要，且是 GPU 大规模并行模拟 | 1 亿环境步 ≈ 单卡 NVIDIA GH200 5.8 小时；模拟吞吐 8×A100 上 200 万步/秒 |
| Mizukami & Tsuruoka（CIG 2015） | **统计预测模型（听牌／待牌／胡牌分值）+ 蒙特卡洛模拟搜索**，无深度网络 | 需要，但每步限时 1 秒内完成 | 未给机器型号；仅声明「每步 1 秒内算完」 |

### 1.2 对「两台 Mac + 可持续增量」的直接结论

1. **来源事实：唯一同时满足「只用人类牌谱、不需要自对弈模拟、且公开到能读懂训练目标」的开源完整实证，是 Mortal 的离线阶段与 Kanachan 的 BC→离线 RL 管线。** Mortal 训练脚本只读 `.json.gz` 牌谱做梯度更新 [S4][S6][S9]；Kanachan 作者明确因为在线 RL 的模拟成本放弃在线路线，改用隐式 Q 学习（Implicit Q-Learning，IQL）[S13]。
2. **来源事实：Mortal 的训练目标不是纯监督。** 总损失 = 蒙特卡洛回报的均方误差 + λ₁·CQL 项 + λ₂·下一局名次交叉熵（示例配置 λ₁=5、λ₂=0.2）[S4][S8]。所谓「蒙特卡洛目标拟合」在源码里的确切含义是：对每个决策点 i，取 `q_target = gamma ** steps_to_done[i] * kyoku_rewards[at_kyoku[i]]`，即**直接回归「该局（kyoku）结束时按 GRP 预测的段位点期望变化」，不做时序差分自举**；示例配置 `gamma = 1`，此时目标就是该局的期望段位点变化本身 [S4][S6][S7][S8]。
3. **来源估计（不是实测）：Kanachan 作者算过，把 Suphx 规模的自对弈模拟（150 万半庄）放到一张 RTX 3090 上要跑约 5 年、电费约 40 万日元**，由此判定在线强化学习对个人算力不现实，转向离线 RL [S13]。**工程建议：这条估算与「两台 Mac」的量级差距极大，本项目不应把自对弈在线 RL 作为变强主路径。**
4. **来源事实：Mahjax 的两阶段（BC→带 KL 约束的 PPO）用的是 1024 并行环境、1 亿环境步，论文自述「追求 SOTA 超出本文范围」，只在 1000 局评估里做到平均顺位优于 2.5 的中性线** [S18]。**工程建议：这说明「能训起来」与「够强」是两件事；不要把「PPO 能跑通」当作路线可行性证据。**
5. **来源事实：CIG 2015 的统计模型 + 搜索路线在 2015 年的算力条件下每步只用 1 秒，就拿到天凤 rating 1718／保证 rating 1690，作者自述约等于「上级桌（Joukyuu）的平均玩家」水平** [S19]。**工程建议：对只有 CPU（含 Apple Silicon CPU）的项目，这条路线是「先有一个能跑的搜索基线」的最低成本选项，但它的强度天花板由人类专家牌谱的抽象特征决定，作者本人也指出该路线在「手牌难胡时的一人麻将走法」和「立直判断模型」上有明显缺陷** [S19]。
6. **来源事实：没有任何一份来源给出「达到某个强度需要多少算力／多少局数据」的定量结论。** 唯一接近的三条是：Kanachan 作者的负向估算（3090→5 年）[S13]、Mortal 文档的模拟吞吐（4 万半庄/小时，RTX 4090）[S2]、Mahjax 的模拟吞吐（2M 步/秒，8×A100）[S18]。它们都是**吞吐或单项时间**，不是「强度—算力」曲线；且都不含杭麻（杭州麻将）规则，**工程建议：不能直接外推到本项目**。
7. **工程建议：把「稳定变强」的实现顺序定为「可复现的版本对比」先于「更复杂的算法」。** Mortal 的公开强度证据全部是**复式对局统计**（1v3、同牌山换座、百万局量级）[S3]，Kanachan 也专门写了复式对局与置信区间的评测规范 [S17]。这与本仓库 AGENTS.md 第 7 节「策略比较按完整桌赛、同牌山换座」的要求方向一致。

## 2 逐项目事实

### 2.1 Mortal（github.com/Equim-chan/Mortal）

**结论：Mortal 是「人类牌谱 → 蒙特卡洛回报回归 + CQL 保守项」的离线 Q 学习工程，网络是 ResNet + 通道注意力 + 决斗式 Q 头；作者公开了源码、强度对比表和版本发布时间线，但没有公开训练数据规模、训练硬件与训练时长，也没有公开说明强度上限。**

| 维度 | 来源事实 | 出处 |
| --- | --- | --- |
| 项目定位 | 「free and open source AI for Japanese mahjong, powered by deep reinforcement learning」；项目始于 2021-04-22 | [S1][S2] |
| 训练数据格式 | 训练脚本从 `dataset.globs` 指定的路径读取 `*.json.gz` 牌谱；Rust 侧 `GameplayLoader::load_gz_log_files` 逐行解析 mjai 事件（`serde_json`）后切成样本；仓库**不含**训练数据本身 | [S8][S9] |
| 训练数据规模 | **未找到**作者公布的总局数／样本数。 | — |
| 数据的时间范围（当前观察） | `config.example.toml` 的示例路径把训练集写成 `2019/**` 到 `2021/02/**` 的按年月目录，验证集写成 `2021/10/**`、`2021/11/**`；说明数据组织方式是「按月增量累积的连续牌谱语料」 | [S8] |
| 数据来源（待确认假设） | 示例配置与文档没有写出牌谱来自哪个平台；本文**未在一手来源中找到**「训练数据取自天鳳鳳凰卓」的作者陈述。仓库 `docs/src/perf/strength.md` 与文档正文只出现 `Tenhou` 于「兼容天鳳规则／天鳳 premium 赞助」语境 | [S2][S3][S8] |
| 网络结构 | `Brain`：`ResNet`（`conv_channels=192`、`num_blocks=40`，一维卷积 + BatchNorm）叠加 `ChannelAttention`（通道路注意力，形如 CBAM），版本 1 额外输出 `mu/logsig`，版本 2/3/4 直接输出特征；`DQN`：决斗式分解 `q = v + a - mean(a)`，非法动作置 `-inf`；`AuxNet`：单层线性输出 4 维（下一局名次）；`GRP`：2 层 GRU + 24 维排列 softmax（预测终局名次排列） | [S5] |
| 训练目标 | `q_target_mc = gamma ** steps_to_done * kyoku_rewards`；`dqn_loss = 0.5 * MSE(q, q_target_mc)`；`cql_loss = logsumexp(q).mean() - q.mean()`；`next_rank_loss = CE(aux_logits, player_ranks)`；`loss = dqn_loss + min_q_weight*cql_loss + next_rank_weight*next_rank_loss` | [S4] |
| 奖励定义 | 离线阶段每个 kyoku 的 reward 由 GRP 计算：`reward = E[pts ｜ 局面]`（期望值）在各局之间的差分，即**该局带来的段位点期望增量**；`test_play` 里使用的 `[90, 45, 0, -135]` 只用于展示，「never used in training」 | [S7][S4] |
| 折扣与步数 | `dones` 由 `at_kyoku` 的边界决定（每局最后一个决策点），`steps_to_done` 因此是**到本局结束**的步数；`apply_gamma` 仅对「打牌」类动作（标签 ≤ 37）为真 | [S9][S6] |
| 超参示例 | `version = 4`；`batch_size = 512`；`gamma = 1`；`pts = [6.0, 4.0, 2.0, 0.0]`；`[cql].min_q_weight = 5`；`[aux].next_rank_weight = 0.2`；AdamW、`peak = final = 1e-4`、warmup+cosine、AMP、梯度裁剪。配置注释声明这是「dummy placeholders … must be tuned」 | [S8] |
| 在线阶段（源码可读、文档为空） | `train.py` 有 `online` 分支：把当前参数 `submit_param` 给对局服务，再 `drain()` 取回新对局日志用于训练；在线模式下跳过辅助名次损失；`server.py` 把提交的对局写入 `buffer_dir` 并在容量满时整体转移到 `drain_dir` | [S4][S6] |
| 文档完整度 | Mortal 文档站自述「most pages are empty right now」；目录列出的「Training／Offline Phase／Online Phase／Failed Attempts／Comparison with Other AIs」等章节在仓库 `docs/src/` 下**没有对应 .md 文件**，即这些章节没有内容 | [S2] |
| 版本演进 | 官方服务历史：2022-06-26 发布 1.0；2022-10-06 发布 2.0／2.1；2023-01-09 发布 3.0／3.1；2023-11-01 发布 4.0；2024-08-31 发布 4.1 系列（4.1a「defensive」、4.1b「balanced」、4.1c「aggressive」） | [S11] |
| 网络版本参数 | `model.py` 里 `version` 分 1／2／3／4 四支：1 带 `mu/logsig` 隐变量输出；3／4 把 BatchNorm 的 `eps` 改为 1e-3；4 把 Q 头合并成单层 `Linear(1024, 1 + ACTION_SPACE)` | [S5] |
| 强度证据（人类之外） | 复式 1v3（同种子换座）对比：Mortal「3.1」×3 vs akochan×1，13152／39456 局，平均顺位 2.477443 vs 2.567670，平均段位点 1.890967 vs −5.672901；「1.0」×3 vs akochan×1 同样占优（2.479145 vs 2.562564） | [S3] |
| 强度证据（版本之间，本文按表内 👑 与粗体标记判读） | 文档共 11 组版本两两 1v3 对比。**只做一次运行**的：4.1c 胜 4.0（+0.254205 对 −0.084735）、4.1b 胜 4.0（+0.377460 对 −0.125820）、4.1a 胜 4.0（+0.423765 对 −0.141255）、4.1b 胜 4.1c（+0.177930 对 −0.059310）。**含换座重跑且两次胜方一致**的：3.1 胜 3.0／2.0／2.1／1.0，4.0 胜 3.1 | [S3] |
| 版本强度不单调（当前观察） | 「2.0」与「1.0」两次换座运行中 👑 都落在 1.0 一侧，即 1.0 胜 2.0（一次 +0.134659 对 −0.403977，换座后 +0.430190 对 −0.143397）。**本文判断：版本强度并非单调递增，不能把「版本号更大」当作「更强」。** | [S3] |
| 版本对比中的噪声案例（当前观察） | 三组在换座重跑后胜方翻转：① 4.1b vs 4.1a（+0.016290 对 −0.005430 ↔ +0.030600 对 −0.010200）；② 2.1 vs 2.0（+0.125000 对 −0.041667 ↔ 换座后由另一方胜出）；③ 2.1 vs 1.0（+0.143465 对 −0.047822 ↔ 换座后由另一方胜出）。**本文判断：这些对的差异处在噪声量级，单次对局统计不足以判定强弱；这也说明「同牌山换座 + 置信区间」的评测规范是必需的。** | [S3] |
| 作者对强度的主观估计 | 2022 年的公开信里说 1.0 版「stronger than akochan and any other available baseline I have, and it's probably as strong as the early version of Suphx」——**来源估计，不是实测数据** | [S10] |
| 天鳳段位／rating | **未找到**作者公布的段位或 rating 声明。官方服务页面对 rating 的说明是：rating「has never been used in training」「is merely an average min-max scaled value without calibration or confidence intervals」，且绑定特定网络、不可跨网络比较 | [S11] |
| 训练硬件与时长 | **未找到**。文档里唯一带硬件型号的是模拟吞吐脚注：「Up to 40K hanchans per hour … Evaluated on NVIDIA GeForce RTX 4090 with AMD Ryzen 9 7950X, game batch size 2000」（这是模拟+推理吞吐，不是训练耗时） | [S2] |
| 强度上限的作者说明 | **未找到**。文档中专门用于记录失败经验的章节（SUMMARY 里的 13. Failed Attempts）在仓库中没有内容 [S2]；作者关于「政策网络版本开源」的讨论帖标题存在（Discussion #91《The policy-based version of Mortal has been open-sourced》），但本环境无法读取其正文，**不引用其任何内容** | [S2][S20] |

**关于「蒙特卡洛目标拟合」的一句话总结（来源事实）**：它不是「用蒙特卡洛树搜索生成标签」，而是**用人类牌谱里真实发生过的该局段位点期望变化作为 Q 的回归目标**；源码里既没有 TD 自举项，也没有对下一步 Q 的 max 操作 [S4][S6]。

### 2.2 Kanachan（github.com/Cryolite/kanachan）

**结论：Kanachan 的路线是「超大规模雀魂牌谱 → 无人工特征的稀疏 token 表示 → BERT 结构编码器 → 分阶段课程微调（BC → 离线 RL：IQL／CQL／ILQL）」。作者给出了明确的数据规模数字，并在公开 gist 中用「3090 跑 150 万半庄要 5 年」的估算解释了为什么放弃在线强化学习。**

| 维度 | 来源事实／原话要点 | 出处 |
| --- | --- | --- |
| 数据来源 | 雀魂（Mahjong Soul）牌谱，需自行用 mitmproxy／Wireshark 等抓取 WebSocket 报文；仓库不提供爬虫、训练数据与模型 | [S12] |
| 数据规模（作者给出的具体数字） | 「Game records consisting of **17 million rounds**, which were generated in 11 years from 2009 to 2019, can be obtained from the Phoenix Table of Tenhou（天鳳鳳凰卓）」；「I have been crawling game records from Mahjong Soul since July 2020, and the amount of game records for 4-player Mahjong played in the **Gold Room or the higher rooms** has reached about **65 million rounds as of the end of August 2021**. This number will surely surpass **100 million rounds** by the end of 2021.」 | [S12] |
| 特征设计 | 刻意「No Human-crafted Features」：牌只作为 embedding 索引的 token，1筒 的 token 不携带「数字 1」或「筒子」语义；作者认为这种端到端设计需要大数据集与高表达力模型 | [S12] |
| 模型结构 | 编码器为 BERT 同构的 Transformer 编码层：`bert_base` = 768 维／12 头／3072 前馈／12 层／GELU／dropout 0.1；`bert_large` = 1024／16／4096／24；解码器可选单／双／三层，CQL 版解码器采用分位数回归、默认 50 个分位区间 | [S14] |
| 训练目标（分阶段） | `bert.phase1`：模仿人类选择的 BC 目标；`bert.phase2`：最大化牌谱中一局（round）的增量；`cql`／`iql`／`ilql`：三个离线 RL 训练程序，带 reward plug-in、折扣因子、expectile／kappa 等超参 | [S14] |
| 一次训练的数据规模（模型卡） | `BASE／BC_H13 v20220210`：数据为「Crawled Game Records v202007_202107」；训练样本 **43,002,752** 条，「action selections only by **Saint 2, Saint 3, and Celestial** players（雀聖 2／雀聖 3／魂天）」随机抽样并打乱；优化器 LAMB、lr 0.001、ε 1e-6、**batch size 4096**、**1 epoch** | [S15] |
| 一次训练的算力（未找到 wall-clock） | 模型卡没有给 GPU 型号或耗时。训练程序的运行前置条件是 Docker + NVIDIA driver + NVIDIA Container Toolkit（CUDA 本身不需要）；`device` 可取 `cpu` 或 `cuda` 两种后端（CPU 走 float64） | [S14] |
| 作者对在线 RL 的原始表述（原话要点） | 「強化学習は（普通は）シミュレーションが必要」「モデルが巨大なのでシミュレーションが重い」「学習量で殴り倒すつもりなのでとんでもないシミュレーション回数が必要」；「試しに Suphx の学習でやってた **150 万半荘**のシミュレーションを…**RTX 3090** で実行したらどのくらいの時間がかかるか電卓に聞いたら「**5 年です**」って答えやがったんですよ。**電気代 40 万円**もかかるじゃないですか」——因此「（少なくとも個人で用意できる計算機環境では）強化学習のためのシミュレーションにあまりにも時間がかかりすぎる」，「オフライン強化学習にはシミュレーションはいらぬ」，遂采用 2022-04 时点的 SOTA「implicit Q-learning (IQL)」，并说明 CQL 同为 SOTA 但直觉上 IQL 实现更简单 | [S13] |
| 奖励设计（作者原话要点） | 采用「completely sparse reward」：**只在「1 試合の最後」给一次 reward，其余全 0**（作者强调不是「一局」而是「一試合」） | [S13] |
| 评测规范 | 项目规定用真实对局统计而非 loss／牌谱一致率；给出 1vs3／2vs2／3vs1 三种对局风格与复式对局（同一牌山换座重打，1vs3 每组 4 局、2vs2 每组 6 局），并要求给出无偏样本方差与 95%／99% 置信区间 | [S17] |
| 数据格式 | BC 与离线 RL 两套格式；BC 格式每行 7 个字段（局面 3 段 + 实际动作 2 段 + 局与终局结果），由 `cryolite/kanachan.annotate` 从雀魂牌谱生成，`annotate4rl` 再转成离线 RL 格式 | [S16] |

**换算（本文计算，来源未直接给出）**：43,002,752 条样本 ÷ batch 4096 ≈ **10,499 个优化步／epoch** [S15]。

### 2.3 Mahjax（arXiv:2605.20577v1）

**结论：这是一篇「GPU 加速麻将模拟器」的工程论文，不是强度论文。两阶段流程（启发式数据 BC → 带 BC 策略 KL 约束的 PPO）被明确写成「为了训练稳定性」的手段，论文没有做 BC 与 PPO 各自贡献的消融实验，最终结论也只到「平均顺位优于 2.5 中性线」。**

| 维度 | 来源事实 | 出处 |
| --- | --- | --- |
| 论文与评审状态 | arXiv:2605.20577**v1**，2026-05-20 提交，cs.AI／cs.LG；从 arXiv 摘要页可见的信息只有 Subjects 与 DOI，**未见期刊／会议引用字段**，即本次可确认的是一篇**预印本（未经同行评审）** | [S18] |
| 模拟吞吐 | 8×NVIDIA A100 上：无红宝牌规则 **200 万步/秒**、有红宝牌规则 **100 万步/秒**；单卡上批量约 2¹⁰ 后吞吐饱和；对比对象 Libriichi（Mortal 的 Rust 模拟器）约 4 万局/小时，论文称快 10 倍以上；基准机为 2×Intel Xeon Platinum 8360Y + 8×A100，批量 2～16384、每组跑 100 个 batch step | [S18] |
| 两阶段流程 | 第一阶段：用启发式规则智能体生成的 **500k 样本**做行为克隆，稳定初始化策略；网络为 Transformer 编码器 + 策略／价值两个 MLP 头。第二阶段：PPO 微调，并用**对 BC 策略的 KL 正则**约束偏移 | [S18] |
| 超参 | 1024 并行环境、rollout 长度 256；γ = 1.0、GAE λ = 0.95、学习率 3×10⁻⁴、clip 0.2、熵系数 0.01、价值系数 0.5、KL 惩罚系数 0.2 | [S18] |
| 计算量 | 训练共 **1 亿环境步**，在**单张 NVIDIA GH200 Grace Hopper** 上约 **5.8 小时** | [S18] |
| 实验设置 | 只用「无红宝牌规则」+「单局模式（single-round mode）」以加快迭代；论文明确指出「aiming for state-of-the-art performance is beyond the scope of this paper」 | [S18] |
| 评估 | 对阵 3 个固定 BC 对手、1000 局（1v3），指标为平均顺位，3 个随机种子求均值与标准差；结论是稳定优于 2.5 的中性线 | [S18] |
| 消融结论 | **来源没有回答**：全文（HTML 版与 PDF 版均检索）**没有出现「ablation」**，也没有「BC-only / PPO-only / from scratch」的对照。可确认的只有「BC+PPO 整体优于 2.5」、「吞吐量的 1 卡 vs 8 卡、红宝牌规则开关对比」，以及未来工作打算走向从零学习 | [S18] |

### 2.4 Mizukami & Tsuruoka（CIG 2015；会议归属见下表说明）

**结论：这是一条「用专家牌谱训练三个统计预测模型（对手是否听牌／待牌种类／胡牌分值），再把预测结果喂进蒙特卡洛模拟」的搜索路线。它每步只用 1 秒，天凤 rating 1718，作者自评为「上级桌平均玩家」水平，并明确指出对手建模的抽象与「一人麻将走法」是瓶颈。**

| 维度 | 来源事实 | 出处 |
| --- | --- | --- |
| 论文归属 | 作者主页 PDF，文件名为 `cig2015mizukami.pdf`；**PDF 提取文本的标题页未包含会议／版权行**，因此「IEEE CIG 2015」这一归属在本报告中记为**任务给定的来源标注，未在 PDF 正文核实**；论文本身是完整的会议论文格式（含 Abstract／章节／References） | [S19] |
| 训练数据 | 天鳳「鳳凰卓（Houou table）」牌谱，**2009-02-20 至 2013-12-31**；作者理由：鳳凰卓只允许前 0.1% 玩家进入，可视为专家水平牌谱 | [S19] |
| 三个预测模型 | 是否听牌（waiting）、对手待牌种类（winning tiles）、胡牌分值（winning scores）；听牌模型用逻辑回归（FOBOS／AdaGrad 在线学习，学习率 0.01），训练状态数约 **1.77×10⁷**；特征如「已亮出的副露与舍牌」等组合特征（例如「副露种类 × 舍牌」共 136×37 = 5032 维） | [S19] |
| 搜索与决策 | 蒙特卡洛模拟中用预测出的概率分布驱动对手行为（听牌／弃和两个二元参数），**每个候选牌做相同次数的模拟**，且**对对手走法与牌山生成使用同一组随机数**以降低随机性；程序侧走法用 ODEV（One-Depth Expected Value，只展开一层的期望值）来替代长模拟 | [S19] |
| 算力 | **未给机器型号与总机时**；唯一明确的约束是「The moves are computed in a second」「moves are always computed in a second」——**每次出牌 1 秒内算完**，即在 2015 年的单机 CPU 上完成 | [S19] |
| 强度（对 AI） | 对 Mattari Mahjong（作者称当时公开可得的「最强」程序）：1000 局复式对局，平均顺位 2.48 ± 0.07 vs 2.51 ± 0.07，**差异不显著（Welch t-test p = 0.29）**；对前作 [5] 差异显著（p = 0.01） | [S19] |
| 强度（对人类） | 天凤上 2634 局（Table IX；**结论段写的是 2643 局，来源内部数字不一致**），平均顺位 2.46 ± 0.04，**stable rating 1718、guaranteed rating 1690**；前景程序 1441 局为 1689／1610；作者结论：「roughly the same as that of the average players in the Joukyuu table」（上级桌平均玩家） | [S19] |
| 作者对该路线的评价 | 相比前作对 AI 更强，但**对人类玩家没有提升**（p = 0.22）；原因是「一人麻将走法」在手牌难胡时会出现坏着，而它又决定了模拟中对手「听牌／弃和」的比例；程序依赖启发式（如「听牌就必须立直」）；需要改进立直预测模型；未来工作是把分数（顺位点）纳入模型，用期望顺位作为模拟的 reward | [S19] |

## 3 各路线对「小算力 + 可持续增量」的适配性对照

**工程建议（本表全部为本文判断，来源事实见第 2 节）：**

| 路线 | 增量来源 | 两台 Mac 的可行性（判断） | 主要风险（判断） | 建议优先级 |
| --- | --- | --- | --- | --- |
| Mortal 式离线 Q 学习（MC 回报 + CQL） | 新增牌谱 + 版本重训 + 复式对局验证 | PyTorch 路线，网络是 40 层一维 ResNet（`conv_channels=192`），参数量级远小于 BERT-large；MPS 或 CPU 都能前向／反向，训练时间需实测 | 依赖大量高质量牌谱与一个可靠的「局末段位点期望」标签来源（Mortal 用 GRP 预测，本项目需自建替代标签）；CQL 权重需调 | 高 |
| Kanachan 式 BC → 离线 RL | 新增牌谱 + 分阶段课程微调（编码器复用） | 结构是 BERT-base 级（768×12 层），训练程序以 NVIDIA Docker 为前提，但 README 提供 `device=cpu`；单卡 48GB 统一内存对 base 模型够用，耗时未知 | 4300 万样本／1 epoch 的量级在 Mac 上很可能不可行；且项目收益高度依赖「数据规模 × 模型表达力」，与「小算力」直接冲突 | 中（先做 BC 阶段，离线 RL 后置） |
| Mahjax 式 BC → PPO 自对弈 | 自对弈步数 + 数据 | 论文的吞吐全部来自 GPU 并行（A100／GH200），本仓库既有调研已把 jax-metal 列为实验性后端，**不宜作为首发后端** | 自对弈模拟吞吐是小算力项目的直接瓶颈；论文本身也未证明该流程能到高水平 | 低 |
| CIG 2015 式统计模型 + 模拟搜索 | 新增牌谱 + 改进预测模型／搜索深度 | 纯 CPU 可行（每步 1 秒是 2015 年单机水平，本机 CPU 更强） | 强度受预测模型抽象与搜索深度限制；作者自述该路线对人类的提升不明显 | 中（作为可解释基线与对手模型组件） |

**综合（工程建议）**：
1. 先把「牌谱 → 监督信号 → 小网络 → 复式对局评估」这条闭环做通，用的是本项目自己的规则与数据结构；Mortal 的 MC 回归与 Kanachan 的 BC 都只是**目标函数的两种写法**，可以先从交叉熵 BC 起步，再加值回归。
2. 不要在没有可靠「局末收益标签」之前引入 CQL；Mortal 的 CQL 项是叠在 MC 回归目标之上的，缺少该目标时保守项没有意义 [S4][S7]。
3. 评估协议按 Kanachan 的复式对局 + 置信区间来做 [S17]，并注意 Mortal 文档中「2.1 vs 1.0 换座后胜方翻转」这类噪声案例 [S3]。
4. 若要参考搜索路线，CIG 2015 的对手模型（听牌／待牌／胡牌分值）是**独立的、可增量训练的组件**，可以只借用它而不引入蒙特卡洛树搜索 [S19]。

## 4 来源没有回答的问题

| 问题 | 查找范围 | 结论 |
| --- | --- | --- |
| Mortal 训练用了多少局牌谱、来自哪个平台 | 仓库 README／docs 全书／`mortal/*.py`／`config.example.toml`／作者 gist | **未找到**具体局数与平台；只有 `config.example.toml` 示例路径显示出按月累积的语料与 2019→2021 的时间跨度 [S8]。**待确认假设**：来源为天鳳牌谱（本报告不将其写成事实） |
| Mortal 训练用了什么硬件、多长时间 | 同上 | **未找到**。只有模拟吞吐脚注（RTX 4090 + 7950X、batch 2000、4 万半庄/小时）[S2] |
| 作者认为 Mortal 的强度上限由什么限制 | docs 全书、gist、官方服务页 | **未找到**。文档中记录失败经验的章节没有内容 [S2]；Discussion #91（政策网络版本开源）正文在本环境不可读 [S20] |
| Mortal 的 4.x 是否仍是 DQN，还是已换成策略网络 | 仓库 main 分支源码、官方服务页 | 仓库 main 分支的 `model.py`／`train.py` 仍是 DQN + CQL + GRP [S4][S5]；同时存在作者发布的「policy-based version open-sourced」讨论帖标题 [S20]。**来源没有回答**二者关系 |
| Kanachan 训练一次（一个模型版本）的 wall-clock 与 GPU 型号 | 训练程序 README、模型卡 Wiki、作者 gist、README | **未找到**。模型卡只给样本数、优化器、batch、epoch 数 [S15]；作者 gist 只给了**在线 RL 的反向估算**（3090、150 万半庄、5 年、40 万日元电费）[S13] |
| Kanachan 各模型版本的强度（例如对 NAGA／Suphx 的胜负） | README（只写目标）、Wiki 评测规范 | **未找到**具体战绩数字；README 只表达「能击败 NAGA／Suphx 与顶级职业选手」的目标 [S12] |
| Mahjax 中 BC 与 PPO 各自贡献多少 | 论文 HTML 与 PDF 全文检索「ablation」 | **来源没有回答**：论文没有消融实验，只有「BC+PPO 优于 2.5」与吞吐量对比 [S18] |
| 「达到某强度需要多少算力／多少局数据」的定量陈述 | 四个项目的全部一手来源 | **未找到**任何一条。可用的只有吞吐量（Mortal 4 万半庄/小时、Mahjax 200 万步/秒）与单项时长（Mahjax 1 亿步 5.8 小时）、以及作者对在线 RL 的负向估算（3090 → 5 年）[S2][S13][S18] |
| 杭麻（杭州麻将）规则下的任何训练数据或强度数据 | 上述全部来源 | **未找到**。四个项目分别是天鳳／雀魂（日式立直麻将）与 JAX 模拟器，规则不同，**不能直接迁移** |

## 5 来源与访问说明

全部链接访问日期均为 **2026-09-14**。「评审状态」栏只描述本次可核对的信息。

| 编号 | 来源 | 类型 | 版本／评审状态 | 链接 |
| --- | --- | --- | --- | --- |
| S1 | Mortal 仓库 README | 官方仓库 | main 分支；AGPL-3.0 | https://github.com/Equim-chan/Mortal |
| S2 | Mortal 官方文档（整本打印页）与 `docs/src/index.md` | 官方文档 | 作者自述「大部分页面为空」 | https://mortal.ekyu.moe/print.html ・ https://github.com/Equim-chan/Mortal/blob/main/docs/src/index.md |
| S3 | Mortal 强度基准页 `docs/src/perf/strength.md` | 官方仓库源码文档 | main 分支 | https://github.com/Equim-chan/Mortal/blob/main/docs/src/perf/strength.md |
| S4 | Mortal `mortal/train.py` | 官方源码 | main 分支 | https://github.com/Equim-chan/Mortal/blob/main/mortal/train.py |
| S5 | Mortal `mortal/model.py` | 官方源码 | main 分支 | https://github.com/Equim-chan/Mortal/blob/main/mortal/model.py |
| S6 | Mortal `mortal/dataloader.py`、`mortal/common.py`、`mortal/server.py` | 官方源码 | main 分支 | https://github.com/Equim-chan/Mortal/tree/main/mortal |
| S7 | Mortal `mortal/reward_calculator.py` | 官方源码 | main 分支 | https://github.com/Equim-chan/Mortal/blob/main/mortal/reward_calculator.py |
| S8 | Mortal `mortal/config.example.toml` | 官方源码 | main 分支；作者注明示例值多为占位符 | https://github.com/Equim-chan/Mortal/blob/main/mortal/config.example.toml |
| S9 | Mortal `libriichi/src/dataset/gameplay.rs` | 官方源码 | main 分支 | https://github.com/Equim-chan/Mortal/blob/main/libriichi/src/dataset/gameplay.rs |
| S10 | Equim 公开信《Should I release the trained model of my mahjong AI?》 | 作者本人公开说明（Gist） | 2022-04-13／2022-08-19 两次更新 | https://gist.github.com/Equim-chan/cf3f01735d5d98f1e7be02e94b288c56 |
| S11 | 官方服务 mjai.ekyu.moe（版本列表、历史、rating 说明） | 作者运营的官方服务 | 页面历史栏最后更新至 2024-08-31 | https://mjai.ekyu.moe/ |
| S12 | kanachan 仓库 README | 官方仓库 | main 分支 | https://github.com/Cryolite/kanachan |
| S13 | Cryolite《kanachan について（2022年4月15日現在）》 | 作者本人公开说明（Gist） | 2022-04-15 | https://gist.github.com/Cryolite/519c8ecc042732a3459a39a1f1256599 |
| S14 | kanachan 训练模块 README（`kanachan/training`、`bert`、`bert/phase1`、`cql`、`iql`、`ilql`） | 官方源码文档 | main 分支 | https://github.com/Cryolite/kanachan/tree/main/kanachan/training |
| S15 | Wiki 模型卡 `BASE／BC_H13 v20220210` | 官方 Wiki（**镜像来源，未在 GitHub 官方页面复核**） | github-wiki-see.page 声明其镜像自官方 Wiki，页面最后修改于 2022-03-10 | 官方地址：https://github.com/Cryolite/kanachan/wiki/BASE%EF%BC%8FBC_H13-v20220210 ・ 镜像：https://github-wiki-see.page/m/Cryolite/kanachan/wiki/BASE%EF%BC%8FBC_H13-v20220210 |
| S16 | Wiki `Notes on Training Data` | 官方 Wiki（**镜像来源**） | 镜像页显示最后修改 2023-05-06 | 官方地址：https://github.com/Cryolite/kanachan/wiki/Notes-on-Training-Data ・ 镜像：https://github-wiki-see.page/m/Cryolite/kanachan/wiki/Notes-on-Training-Data |
| S17 | Wiki `Methods and Metrics in Performance Comparison and Evaluation` | 官方 Wiki（**镜像来源**） | 镜像页显示最后修改 2022-03-11 | 官方地址：https://github.com/Cryolite/kanachan/wiki/Methods-and-Metrics-in-Performance-Comparison-and-Evaluation ・ 镜像：https://github-wiki-see.page/m/Cryolite/kanachan/wiki/Methods-and-Metrics-in-Performance-Comparison-and-Evaluation |
| S18 | Mahjax 论文 | arXiv 预印本 | **arXiv:2605.20577v1**，2026-05-20 提交，cs.AI／cs.LG；摘要页未见期刊／会议字段，**未标注同行评审** | 摘要：https://arxiv.org/abs/2605.20577 ・ HTML 全文：https://arxiv.org/html/2605.20577v1 ・ PDF：https://arxiv.org/pdf/2605.20577v1 |
| S19 | Mizukami & Tsuruoka《Building a Computer Mahjong Player Based on Monte Carlo Simulation and Opponent Models》 | 会议论文（作者主页 PDF） | 任务给定来源标注为 CIG 2015；**PDF 正文未含会议／版权行，归属未在正文核实**。参考文献中引用了 2015 年 Science 的扑克求解工作，可佐证成文时间 | https://www.logos.t.u-tokyo.ac.jp/~tsuruoka/papers/cig2015mizukami.pdf |
| S20 | Mortal Discussion #91 标题《The policy-based version of Mortal has been open-sourced》 | 官方讨论区 | **正文在本环境无法读取**（GitHub Discussions 为客户端渲染；API 亦受本机 IP 速率限制）；本报告只引用其标题存在这一事实，不引用任何内容 | https://github.com/Equim-chan/Mortal/discussions/91 |

**访问与取证说明**：
1. GitHub 源码文件通过 jsDelivr 的 GitHub 镜像（`cdn.jsdelivr.net/gh/<repo>@main/<path>`）取得；它是 GitHub 仓库文件的 CDN 镜像，内容与官方仓库文件一致，链接栏给出的是官方地址。若需要严格复核，请以官方地址重新下载比对。
2. `raw.githubusercontent.com` 与 `gist.githubusercontent.com` 中前者在本环境不可用、后者可用；GitHub Discussions／Issues 页面为客户端渲染，本环境读不到正文，因此凡涉及讨论区的结论都已标注为「未找到」。GitHub REST API 在本机 IP 上已达未认证速率上限。
3. 论文 PDF 用 pypdf 6.18.1 提取文本后检索与引用，可能存在少量排版符号丢失（例如 CIG 2015 文中数字间的乘号、上标），**引用时以原文语义为准，未对数字做任何补全或修正**。Kanachan 作者 gist 为日文原文，本报告在表格中给出的是**原文片段 + 中文要点**，未改写其数字。
4. 本报告只新建了本文件，未修改仓库中任何其他文件，未运行任何训练或修改代码。
