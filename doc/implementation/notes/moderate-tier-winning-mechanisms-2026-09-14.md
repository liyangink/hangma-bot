# 中等强度赛场取胜机制：一手来源证据核查

> 调研日期与全部来源访问日期：**2026-09-14**。用途：为「在官方杭麻赛事中超过约 20 个竞争对手（近半为纯启发式蒙特卡洛 + 人工经验的机器人），不要求达到世界顶级人类水平，算力为两台 Apple Mac」这一现实目标选择技术路线提供依据。本文不是杭麻规则依据，也不宣称任何方法已在本项目有效。
>
> **证据标记（全文沿用）：**
> - **官方已确认**：平台或赛事官方文档明文写出。
> - **来源事实**：外部一手来源（论文原文、项目官方仓库源码与文档、作者本人公开材料）原文所述。
> - **工程建议**：本项目取舍，不是来源结论。
> - **待确认假设**：尚无本项目证据。
> - **我的判断**：本文作者的推论，不是来源的结论。
>
> 术语首次出现写成「中文名（`EnglishName`，一句通俗解释）」。相关既有笔记：[启发式探索与模型路线：原始文献核查](heuristic-methods-literature-2026-09-10.md)、[候选积分标签：原始资料与训练边界](candidate-outcome-labels-evidence-2026-09-11.md)、[Apple Silicon 计算优化调研：M4 Pro / M5 Pro，各 48GB](apple-silicon-compute-research-2026-09-07.md)。

---

## 1 结论

### 1.1 一页结论

**工程建议：应把「结果/价值模型 + 有界搜索」而不是「端到端纯策略网络」作为主线。**这不是因为纯策略网络不强，而是因为**在中等强度对手场取胜所需的算力量级，与本项目两台 Mac 的差距，在「价值模型 + 搜索」路线上小得多**，而且这条路线上存在与本项目赛场结构高度相似的一手案例（Kurita 与 Hoki 2019）。

**但必须同时接受一条负面发现：在麻将域，「对纯启发式对手的改进」有明确的零结果。**Mizukami 与 Tsuruoka 2015 用当时最强的公开程序 Mattari Mahjong（评估函数是人工启发式的组合）做 1000 局复式对局，平均顺位 2.48 ± 0.07 对 2.51 ± 0.07，**差异不显著（p = 0.29）**；作者并自陈改进「未体现在对人类玩家一侧」。**「对手是启发式程序」不等于「我们更容易赢」。**

| 问题 | 结论 | 最贴近的一手证据 |
| --- | --- | --- |
| 1 结果模型 + 搜索 vs 纯策略网络 | 前者在**中等强度对手场、台式机算力**下有直接案例，但**其中一条是零结果**；后者登顶证据的算力门槛极高 | Kurita 与 Hoki：3557 局、平均顺位 2.23 ± 0.04 胜当时最强 AI（边界显著）；**Mizukami 与 Tsuruoka：对纯启发式程序 Mattari Mahjong 1000 局复式，差异不显著（p = 0.29）**；Suphx：44 GPU × 2 天/次训练、20 张 K80 × 2 天/次离线评估 |
| 2 名次/晋级目标建模 | 名次导向建模在麻将域有一手证据；单局得分被明确论证为不好的学习信号 | Suphx §3.2；Kurita 与 Hoki 式 (1) 与式 (3) |
| 3 针对固定可预测对手优化 | 支持的是**条件命题**：对手固定且明显次优时有效；对手会适应或强度更高时无一手证据支持 | 支持：PSRO、Billings 1998、Kurita 与 Hoki 的固定 chance player；限定：Pluribus、Libratus、Davidson 2000、Johanson 与 Bowling 2009 |
| 4 强度评估设计 | 公开项目的主流是**固定对手池 + 复式同牌山 + 大样本**；报告区间的是少数（Kanachan 与 Mizukami 2015） | Mortal（1v3 复式、无区间）、Kanachan（t 分布/二项区间）、Mizukami 与 Tsuruoka 2015（复式配对 + bootstrap 区间 + Welch t 检验）、Suphx（真实天梯 + 重采样） |
| 5 可靠下限 | 平台自身有超时代打；顶级系统为时限**放弃**随时搜索；降级靠阈值切换而非在线修正 | 天鳳官方手册、Suphx §5 脚注 8、Mizukami 与 Tsuruoka 的阈值切换 |
| 6 对手身份是否可信 | 身份键画像在平台层面被官方承认「无法证实」；公开研究一致偏向**把画像作用域限制在单场/单阶段** | Kakao Games 官方公告、Pluribus、Johanson 与 Bowling 2009、Ganzfried 与 Sandholm 2011 |

### 1.2 对本项目技术路线的判断（工程建议）

1. **主线取「小结果模型 + 有界搜索/排序」，并保留规则层枚举合法动作作为保底。**一手依据：Kurita 与 Hoki 用「手牌价值 = 最终名次分布 × 名次收益」加上多个马尔可夫决策过程（Markov Decision Process，把一局牌抽象成只含一个决策者的简化过程）抽象，在普通台式机上每次决策几秒内完成，并在 3557 局中取得优于当时最强 AI 的平均顺位。
2. **搜索预算必须按动作窗口本身设计，不能照搬论文的「几秒」。**ISMCTS 原论文自己报告：决策时间 1 秒时，多观察者 ISMCTS 略逊于确定化搜索；到 3 秒以上才显著更强（斗地主场景下 < 1 秒时 SO-ISMCTS 也略弱）。本项目线上是 1 秒/3 秒窗口，**待确认假设**：本项目的时间预算落在该论文的「搜索尚未回本」区间。
3. **不要把「对手建模」当作初期的主要收益来源。**收益量级在有数字的两处都很小：Leduc 扑克上平均每手 +0.106 大盲（best response 相对均衡策略的增益），两人有限注扑克上需要约 1000 手预热且此后仍有数百手负收益；而「对手身份是否可信」本身在平台层面被官方否认。**工程建议：先做「本局公开行为」级别的轻量防守校准，把跨场次账号画像列为后期可选项。**
4. **目标函数按赛事名次/晋级写，不要写成本局积分最大化。**Suphx 与 Kurita 与 Hoki 都支持这一点；但注意 Kurita 与 Hoki 的名次收益 `U_game(x)` 是「由赛事规则定义」的，本项目对应物是阶段晋级规则，属**待确认假设**，需按实际赛制确认后再实现。
5. **评估设计取 Kanachan、Mortal 与 Mizukami 2015 的组合：复式同牌山 + 固定对手池 + 置信区间。**只做复式不给区间（Mortal、Botzone 官方赛事）或只给区间不控牌山，都会让「是否真的变强」无法判定；Mizukami 与 Tsuruoka 早在 2015 年就同时用了复式配对、bootstrap 区间与 Welch t 检验，可作为最小可用模板。
6. **先设计「提升不显著时怎么办」。**本项目面对的是与 Mizukami 与 Tsuruoka 相同的处境：对手偏弱、样本有限、提升幅度小。**工程建议**：把「与基线无显著差异」写成预期结果之一，先把规则正确性、时限内稳定提交、复式评估工具链做扎实，再谈强度提升；不要用单次实验的均值差当作上线依据。

### 1.3 待确认假设（尚无本项目证据）

以下都是**待确认假设**，不是来源结论，也不是本项目的既有观察：

1. 官方杭麻平台的**超时判罚口径**未知。日本天鳳是「时间耗尽由平台代打 pass 或摸切」，而 Botzone 竞技麻将只把超时记为 TLE 错误、未承诺代打（**官方已确认**的是这两条平台事实；「杭麻也代打」是**待确认假设**）。在确认前，保底动作必须由我方自己完成。
2. 赛事对手是否**真的固定、是否会被其他队伍针对训练**未知。这是第 2.3 节条件命题成立与否的关键事实锚点，文献无法回答。
3. 赛事是否允许、以及如何统计**自由对战记录**未知；因此「对手画像能否跨场次累积」是待确认假设，不是已知条件。
4. 本项目的动作窗口内可完成的模型推理次数与搜索迭代次数**尚未实测**（两台 Mac 的具体吞吐需测量，不能由芯片名称推定）。

---

## 2 逐问题事实与来源

### 2.1 问题一：「结果/价值模型 + 搜索」与「纯策略网络」的证据对比

#### 2.1.1 Kurita 与 Hoki 2019：与本题赛场结构最相似的一手案例

**来源**：Moyuru Kurita、Kunihito Hoki，*Method for Constructing Artificial Intelligence Player with Abstraction to Markov Decision Processes in Multiplayer Game of Mahjong*，[arXiv:1904.07491v1](https://arxiv.org/abs/1904.07491)（2019-04-16，**预印本**；arXiv 页 Comments 为 IEEE 版权声明）。同一工作另有**同行评审期刊版**：[IEEE Transactions on Games, 13(1):99–110, 2021-03, DOI 10.1109/TG.2020.3036471](https://doi.org/10.1109/TG.2020.3036471)（书目数据经 Crossref 核对；**本次未取得期刊版全文**，下文数字均出自 arXiv v1）。

**来源事实（实验设置）**：

- 对手池是**固定三方**：「The three AI players are one Bakuuchi and two copies of manue.」其中 Bakuuchi 是 Mizukami 与 Tsuruoka 的蒙特卡洛 + 对手建模程序，manue 是公开源码的入门级蒙特卡洛程序。
- Bakuuchi 用的是最强版本：「The version of Bakuuchi is the one that achieved its highest grade and ratings (R2206) in tenhou, and is stronger than that published in a previous paper [20].」——其参考文献 [20] 即 Mizukami 与 Tsuruoka 的 CIG 2015 论文。
- 规模：「Table. I lists the result from 3557 gameplays of mahjong with the tonpu rule.」（东风战规则，3557 局）
- 决策方式：贪心，即「the player is greedy, i.e. the action with the highest value was selected.」
- 向听数大于 3 时**退回简单规则策略**：「When the shanten-number of the hand is greater than three, we adopt a simple rule-based strategy.」
- 对手被当作**固定的机会玩家**：「We considered the averaged behavioral strategies of a variety of experts to replace three of the four players with a chance player.」「The action probabilities of the chance player acting on behalf of three players are inferred from game records of experts and the authors' experience.」

**来源事实（结果与算力）**：

| 指标 | 本方法 | Bakuuchi | manue |
| --- | ---: | ---: | ---: |
| 第 1/2/3/4 位经验概率 | 0.33 / 0.28 / 0.21 / 0.17 | 0.32 / 0.27 / 0.21 / 0.20 | 0.17 / 0.22 / 0.29 / 0.31 |
| 平均顺位 | **2.23 ± 0.04** | 2.29 ± 0.04 | 2.74 ± 0.02 |

（表 I，3557 局东风战。表中「±」为论文给出的区间写法。）

- 统计口径原文：「the mean and deviation of the difference are 0.0574 and 1.822, respectively. Given the sample size was 3.56 × 10³, the sample mean was 5.74 × 10⁻², and the sample standard deviation was 1.822, the mean was positive with one-tailed significance level 0.03 from the analysis using the standard error of the mean.」
- 算力原文：「We also present that our player makes each decision **in a few seconds using a realistic computational resource**.」「**We reduced the number of MDP states to the extent that the expected final-rank error does not increase so that the calculation ends in a few seconds.**」以及脚注：「This took several months using an ordinary desktop PC.」（指 3557 局对局本身耗时数月）

**我的判断**：这是本题所需证据里**结构最相似**的一条——固定对手池、其中包含纯启发式蒙特卡洛机器人、台式机算力、以平均顺位（而非胜率）为指标，并且**赢了**。但必须同时看到三点限制：其一，差异幅度很小（平均顺位差 0.0574，单尾显著水平 0.03，属「边界显著」）；其二，作者自评「reached the world highest level」是**作者主张**，评测环境是自设对手池而非真实天梯；其三，期刊版可能修订了数字，本次未能核对。

#### 2.1.2 Cowling、Powley、Whitehouse 2012：信息集蒙特卡洛树搜索原论文

**来源**：Peter I. Cowling、Edward J. Powley、Daniel Whitehouse，*Information Set Monte Carlo Tree Search*，**IEEE Transactions on Computational Intelligence and AI in Games, 4(2):120–143, June 2012**，DOI 10.1109/TCIAIG.2012.2200894（**同行评审期刊论文**）。本次读取的是 White Rose 机构库的作者投稿版：[eprints.whiterose.ac.uk/id/eprint/75048](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf)。

术语：**确定化（determinization，把看不见的牌随机补全成若干个完整世界，再分别当作完全信息问题求解）**；**策略融合（strategy fusion，把同一观察下无法区分的情况当成可以分别决策，从而高估自己）**；**非局部性（nonlocality，忽略对手有能力把牌局引向或引离某些隐藏状态）**。信息集蒙特卡洛树搜索（Information Set Monte Carlo Tree Search，直接在「我方无法区分的状态集合」上建搜索树的方法）分 SO（单观察者）与 MO（多观察者）两种变体。

**来源事实**：

- 报告了**三个实验域**：桌游 Lord of the Rings: The Confrontation（LOTR:C）、幻影棋类 Phantom (4,4,4)、三人纸牌斗地主（Dou Di Zhu）。
- 确定性结论：LOTR:C 上 ISMCTS 显著优于确定化 UCT；但在 Phantom (4,4,4) 上，**决策时间超过约 1.5 秒后，SO/MO-ISMCTS 相对确定化 UCT 反而随算力增加而变弱**——原文解释是这两种算法悲观地假设对手知道部分或全部隐藏信息，从而错误地判定局面必败并随机出招。
- 决策时间与强度的关系（对本项目最直接）：LOTR:C 上「for 1 s of decision time, MO-ISMCTS is slightly inferior to determinized UCT, but when at least 3 s of decision time is used MO-ISMCTS is significantly stronger」；斗地主上「SO-ISMCTS appeared slightly weaker with less than 1 s of decision time」。
- 每迭代成本：「SO-ISMCTS and MO-ISMCTS are two to four times slower than determinized UCT」，且在斗地主与 LOTR:C 中「in 1 s of decision time SO-ISMCTS and MO-ISMCTS execute around a third the number of iterations that determinized UCT does」。
- 对**商业启发式 AI** 的对照实验（斗地主）：「This agent uses flat Monte Carlo evaluation coupled with hand-designed heuristics.」三个算法各与两份该商业 AI 对战 1000 局，各算法期望胜场为 500；结果「both determinized UCT and ISMCTS significantly outperform the AI Factory agent」。**关键限定**：「A further experiment was conducted to show that if we give the AI Factory player 100 times as many iterations as in the commercial version, the playing strength of all three agents is **not significantly different**.」
- 适用边界（论文自陈）：「To solve the problem of nonlocality requires techniques such as **opponent modeling and calculation of belief distributions, which are beyond the scope of this paper**.」
- 关于均衡策略与次优对手：「The definition of Nash equilibrium requires only that the strategy be optimal against other optimal (Nash) strategies, so **Nash strategies often fail to fully exploit suboptimal opponents**.」
- 对手建模的实现（MO-ISMCTS）：「MO-ISMCTS's opponent model is more realistic: each opponent action has its own statistics in the opponent tree and so the decision process is properly modeled, but whichever action is selected leads to the same node in the player's own tree.」

**我的判断**：这篇论文给本项目两条最实用的警告。第一，**「搜索更强」是有条件的，条件就是决策时间**——在 1 秒量级上，更复杂的搜索变体可能还不如简单的确定化搜索。第二，斗地主的商业 AI 对照说明：**启发式对手之所以被打败，部分原因是它的模拟次数少**；给它 100 倍迭代后差异就不显著了。这直接关系到本项目对「近半对手是纯启发式蒙特卡洛」这一前提的理解——**待确认假设**：这些对手是否也受同样的小预算限制。

#### 2.1.3 Mizukami 与 Tsuruoka 2015：对手模型 + 蒙特卡洛，以及一条**中等强度对手场下的零结果**

**来源**：Naoki Mizukami、Yoshimasa Tsuruoka，*Building a Computer Mahjong Player Based on Monte Carlo Simulation and Opponent Models*，**2015 IEEE Conference on Computational Intelligence and Games (CIG), pp. 275–283**，DOI 10.1109/CIG.2015.7317929（**同行评审会议论文**）。书目数据经 Crossref 与 Semantic Scholar 核对；IEEE Xplore 为闭源。作者实验室另有一份公开托管的 PDF：[logos.t.u-tokyo.ac.jp/~tsuruoka/papers/cig2015mizukami.pdf](https://www.logos.t.u-tokyo.ac.jp/~tsuruoka/papers/cig2015mizukami.pdf)。

**取证说明（据实记录）**：该托管文件（1,218,785 字节）在本次会话内**未能完整下载**（服务器带宽极低）。本文作者改为**直接对已下载到的分块字节做内容流解压与文本提取**，据此**自行核对**了下述引文（该 PDF 的文本以标准编码存放，可直接提取；因 PDF 字距微调，提取文本会出现「mo v es」这类空格伪影，本文引用时已归一化空格，**未改动任何词**）。因此本节引文为**本文作者核对**，但**未与 PDF 版面逐页比对**。

**来源事实（对手建模方式）**：摘要与第 IV 节写明，把对手行为拆成三个要素，用**专家人类牌谱**训练预测模型：「This paper describes a method for building a Mahjong program that models opponent players and performs Monte Carlo simulation with the models. **We decompose an opponent's play into three elements, namely, waiting, winning tiles, and winning scores, and train prediction models for those elements using game records of expert human players.**」「Opponents' moves in the Monte Carlo simulations are determined based on the probability distributions of the opponent models.」训练数据取自天凤「Houou」桌，「**Only the top 0.1% of the players are allowed to play in the Houou table**, so we consider the quality of those game records to be that of expert human players.」

**来源事实（算力与降级）**：

- 每次蒙特卡洛着法固定用 **1 秒**算完：「**Monte Carlo moves are always computed in a second.**」；实验设置处再次写明「The length of a game is four rounds. **The moves are computed in a second.**」
- **按状态阈值降级**：开局阶段蒙特卡洛着法不佳，因为可用模拟时间短；于是按阈值在两种着法间切换——「We switch from one-player Mahjong moves to Monte Calro moves as follows: (One-player Mahjong moves if Σ_{p∈opponents} EL(p, Tile) ≤ α; Monte Carlo moves otherwise), where α is the threshold.」阈值取值「**We set α to 0.2 based on the result.**」（α 用 10,000 个状态、以「与牌谱动作的一致率」为准则选择）
- 方差控制：「The same random numbers are used for controlling opponents' moves and for generating the wall to minimize the effect of randomness in simulation.」

**来源事实（对启发式对手的评估：零结果）**——这是本节最重要的一条：

> 「We compared our program against **Mattari Mahjong**. To the best of our knowledge, **Mattari Mahjong is the strongest among the publicly available Mahjong programs. The evaluation function of Mattari Mahjong is created by the heuristic combination of statics.**」
>
> 「We used a **match game type, which is a duplicate mode that generates the same walls and hands using the random numbers**, and allows us to compare the results of Mattari Mahjong plays and that of our program. **Our program plays 1000 games.** We use the **average rank** for evaluation.」
>
> 「We calculated the **confidence interval of the average rank (p-value = 0.05) using bootstrap resampling**. The difference between the average rank of previous work [5] and that of our program is statistically significant by welch t-test (p-value = 0.01). **In the case of Mattari Mahjong, the result of our program is better than that of Mattari Mahjong, but the difference is not statistically significant (p-value = 0.29).**」
>
> 表 VII（名次分布与平均顺位）：

| 程序 | 第 1 位 | 第 2 位 | 第 3 位 | 第 4 位 | 平均顺位 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 本方法 | 0.252 | 0.256 | 0.247 | 0.245 | **2.48 ± 0.07** |
| Mattari Mahjong（纯启发式评估函数） | 0.248 | 0.247 | 0.250 | 0.255 | **2.51 ± 0.07** |
| 作者前作 [5] | 0.243 | 0.226 | 0.222 | 0.309 | 2.59 ± 0.07 |

**来源事实（真实天梯评估）**：摘要即写明「We have evaluated the playing strength of the resulting program on a popular online Mahjong site "Tenhou". **The program has achieved a rating of 1718**, which is significantly higher than that of the average human player.」评估小节给出评分公式、初始 R = 1500，并说明「An improvement in average rank by 0.1 roughly corresponds to 100 rating points」，以及两种度量（stable rating／guaranteed rating）。结果与讨论：

> 「The difference between the average rank of previous work [5] and that of our program is **not statistically significant by welch t-test (p-value = 0.22)**. Our program, however, **improves the guaranteed rating**.」
>
> 「**Compared to our previous work, our program improves the result against Mattari Mahjong. On the other hand, it does not improve the result against human players.** A possible reason is that the winning ability of Mattai Mahjong is higher than that of human players, and Monte Carlo moves are used more often in the actual games.」

**我的判断**：这篇论文对本项目有三点价值，其中第三点是最重要的**负面**证据。

1. 它证明「**1 秒/次决策 + 蒙特卡洛 + 对手建模**」在真实麻将 AI 上是被实践过的工程口径，与本项目的时间窗口同量级。
2. 它的可靠性来自**阈值降级**（α = 0.2）：时间不够就退回廉价的单人麻将启发式着法。这**不是**「先有保底合法动作再改进」的机制，两者不要混为一谈（见 2.5.3）。
3. **对纯启发式程序（Mattari Mahjong）的 1000 局复式对局中，改进在统计上不显著（p = 0.29）；而在真实天梯上，相对前作的平均顺位差同样不显著（p = 0.22）。**作者自己的解释是：改进只体现在「对启发式程序」这一侧，**没有体现在对人类玩家一侧**。这直接说明：**即使对手是纯启发式程序，「用更复杂的模型去赢它」也可能拿不到统计上站得住的优势**——本项目的目标赛场正是这类对手，必须把这条当作正面设计约束，而不是当作已经成立的假设。

#### 2.1.4 「纯策略网络」路线的算力门槛

**来源**：Li 等，*Suphx: Mastering Mahjong with Deep Reinforcement Learning*，[arXiv:2003.13590v2](https://arxiv.org/abs/2003.13590)（**预印本，未发现同行评审记录**；arXiv 摘要页无 Journal reference、无会议/期刊 DOI）。本次读取 PDF 全文。

**来源事实**：

| 项目 | 原文数字 |
| --- | --- |
| 单次在线强化学习训练一个 agent | 「The training of each agent costs **44 GPUs** (4 Titan XP for the parameter server and 40 Tesla K80 for self-play workers) and **two days**.」（1.5 million games） |
| 单次**离线评估**一个 agent | 「the evaluation of one agent took **20 Tesla K80 GPUs for two days**.」（100 万局，对手固定为 3 个 SL-weak agent） |
| 最终系统规模 | 「Suphx is equivalent to RL-2 trained with about **2.5 million games**.」 |
| 线上成绩 | 「Suphx played 5000+ games in the expert room and achieved 10 dan in terms of record rank and 8.74 dan in terms of stable rank.」 |
| 线上推理形态 | 五个学习模型 + 一个规则和牌模型；耗时的运行时策略适应（run-time policy adaptation）**没有上线** |

**我的判断**：Suphx 的**方法组件**（全局奖励预测、观察编码、监督预训练 + 自对弈）与本项目的算力无关，可以借鉴；但**它的强度结论不能移植**，因为达到该强度所需的训练规模（数十张 GPU × 数天 × 数百万局）与本项目两台 Mac 不在同一量级。**工程建议**：把 Suphx 当作「方法词典」，不要当作「路线可行性证据」。

**补充来源事实（纯策略网络的推理成本，与训练成本要分开看）**：Mortal 官方文档写明推理吞吐「Up to 40K hanchans per hour[^env]」，脚注为「Evaluated on NVIDIA GeForce RTX 4090 with AMD Ryzen 9 7950X, game batch size 2000」——即**推理可以在单张消费级显卡上每小时跑数万局半庄**。同一文档集（README、docs/src/index.md、docs/src/perf/strength.md）中**未找到任何训练算力说明**。

#### 2.1.5 算力对照表

| 路线 | 代表系统 | 训练算力（原文） | 推理算力 | 结论适用边界 |
| --- | --- | --- | --- | --- |
| 价值模型 + 搜索/抽象 | Kurita 与 Hoki 2019 | 未给出训练算力；对局实验「several months using an ordinary desktop PC」 | 每次决策「a few seconds」，普通台式机 | 固定对手池（1 强 + 2 弱 MCTS），平均顺位小幅领先 |
| 蒙特卡洛 + 对手模型 | Mizukami 与 Tsuruoka 2015 | 未给出（训练数据为天凤 Houou 桌专家牌谱） | 每次蒙特卡洛着法 **1 秒** | 对纯启发式程序 Mattari Mahjong 1000 局复式：平均顺位 2.48 ± 0.07 vs 2.51 ± 0.07，**差异不显著（p = 0.29）**；上真实天梯 rating 1718 |
| 信息集搜索 | Cowling 等 2012 | 不适用 | 1 秒内 SO/MO-ISMCTS 迭代数约为确定化 UCT 的三分之一 | **1 秒时 MO-ISMCTS 略逊**；≥3 秒才显著更强 |
| 纯策略网络（监督 + 自对弈 RL） | Suphx 2020 | 44 GPU × 2 天/agent；总计约 250 万局 | 五个模型前向 + 规则和牌模型 | 强度结论依赖极大算力；运行时搜索被时限排除 |
| 纯策略网络（开源实现） | Mortal | **官方文档未说明训练算力** | 40K 半庄/小时（RTX 4090，batch 2000） | 官方强度证据为固定对手池（akochan 或自家历史版本），非天梯 |

### 2.2 问题二：与名次/晋级相关的目标建模

#### 2.2.1 Suphx 的全局奖励预测为什么必要（§3.2）

**来源事实（逐字）**：

> 「In Mahjong, each game contains multiple rounds, e.g., 8-12 rounds in Tenhou. ... Players receive round scores at the end of each round, and receive game rewards after 8-12 rounds. **However, neither round scores nor game rewards are good signals for RL training:**」
>
> 「Since multiple rounds in the same game share the same game reward, using game rewards as a feedback signal cannot differentiate well-played rounds and poorly-played rounds.」（理由一：同一局的各圈共享同一个局末奖励，无法区分打得好与打得差的圈）
>
> 「While the round score is computed for each individual round, it may not be able to reflect the goodness of the actions, especially for top professional players. For example, in the last one or two rounds of a game, **the rank-1 player with a big lead in terms of accumulated round scores will usually become more conservative, and may purposely let rank-3 or rank-4 players win this round so that he/she can safely keep rank 1 overall. That is, a negative round score may not necessarily mean a poor policy**: it may sometimes reflect certain tactics and thus correspond to a fairly good policy.」（理由二：单圈得分可能反映不了动作好坏，领先者可能故意让 3、4 位和牌以保住第 1 名）
>
> 因此引入全局奖励预测器 Φ：「we introduce a global reward predictor Φ, which predicts the final game reward given the information of the current round and all previous rounds of this game. ... the reward predictor Φ is a recurrent neural network, more specifically, a **two-layer gated recurrent unit (GRU) followed by two fully-connected layers**.」
>
> 「The training data for this reward predictor Φ come from the logs of **top human players** in Tenhou, and Φ is trained by minimizing the following mean square error」（式 (4)，对局末奖励做平方误差回归）
>
> 训练完成后：「for a self-play game with K rounds, we use **Φ(x^k) − Φ(x^{k−1})** as the reward of the k-th round for RL training.」
>
> 效果示例（§4.2，Fig. 9）：领先的南家在最后一圈「instead of playing aggressively to win this round, our agent plays conservatively, chooses the safest tile to discard, and finally gets the first place/rank for this game.」

**我的判断**：§3.2 给出的不是「多加一个特征」的建议，而是一个**目标函数不匹配**的论证：当最终目标是名次时，单圈得分不是该目标的合法替代信号，甚至可能方向相反。这条论证与本项目的赛事目标（阶段晋级、名次）直接同构。**工程建议**：本项目的目标建模应显式写成「最终名次/晋级」的函数，而不是「本局积分」的函数。

#### 2.2.2 麻将域其它把「最终名次」当作价值或学习目标的公开研究

**来源事实 A（名次收益作为手牌价值的终端值）**：Kurita 与 Hoki 2019 把一手牌当作截断的子博弈，终端给出的是**最终名次的期望收益**：

> 「U_hand^i(φ_hand) = Σ_{x∈{1,2,3,4}} P(RANK(x,i) | φ_hand) · U_game(x)」（式 (1)）
>
> 「Here, U_game(x_rank^i) is the payoff of rank x, which is **defined by the rules of the tournament** (normally, the higher the rank, the higher the payoff).」
>
> 「We compute U_hand^i(φ_hand) using Eq.(1), where P(RANK(x,i)|φ_hand) is inferred using **a multi-class logistic regression model**, as in a previous study [20].」
>
> 作者并把它类比为双陆棋（backgammon）的「match equity table」：「it is common to play one game of n point match backgammon as an individual game based on the reward of the match equity table [3].」

**来源事实 B（社区开源实现）**：Mortal 的模型源码中有一个与 Suphx 的 Φ 对应的模块（类名 `GRP`），输入为 `[grand_kyoku, honba, kyotaku, s[0], s[1], s[2], s[3]]`，输出 24 维 logits，注释写明「perms are the permutations of all possible rank-by-player result」，`calc_matrix` 把 24 种排列概率汇总成每个座位的名次概率。来源：[mortal/model.py](https://github.com/Equim-chan/Mortal/blob/main/mortal/model.py)（访问 2026-09-14，main 分支）。

**来源事实 C（评估指标而非学习目标）**：Meowjong（三人麻将 AI）以「第 1 位率 / 第 2 位率 / 第 3 位率 / 流局率」四项多项式分布作为评估指标，并用多项式显著性检验。来源：*Building a 3-Player Mahjong AI using Deep Reinforcement Learning*，[arXiv:2202.12847v3](https://arxiv.org/abs/2202.12847)（**预印本**；arXiv 页无会议/期刊信息）。

**来源事实 D（锦标赛目标的可加性反例，非麻将域）**：Gilbert，*The Independent Chip Model and Risk Aversion*，[arXiv:0911.3100](https://arxiv.org/abs/0911.3100)（math.PR，**预印本**）。独立筹码模型（Independent Chip Model，用「最终名次概率 × 奖金」而不是筹码量衡量一手牌价值）下：「Our first result is that **participating in a fair bet with one other player will always lower one's expected value** under this model. ... **We show that neither result necessarily holds for a fair bet among three or more players.**」

**我的判断**：把「最终名次/晋级」作为价值目标，在麻将域有**两条独立的一手证据**（Suphx 的全局奖励预测、Kurita 与 Hoki 的式 (1)），并且开源社区（Mortal）独立实现了同构模块。但要注意：Kurita 与 Hoki 的 `U_game(x)` 是「赛事规则定义的」，本项目必须按实际赛制自己定义，不能照抄。ICM 那条给出一个**重要的负面提示**：在两人情形成立的「公平赌注降低期望」结论，**在三人以上不必然成立**——也就是说，名次导向的价值函数在多人赛事里不能靠简单类比推导，必须按本项目赛制单独验证（**待确认假设**）。

#### 2.2.3 是否还有其他公开研究把「晋级概率」直接作为学习目标

**未找到。**本次检索没有找到把「赛事晋级概率」而非「单场名次」作为学习目标的公开麻将研究。能找到的同族证据只有上文的「最终名次」级目标。检索到的、性质相近但**不是**同一命题的材料：一件中国专利申请（CN121503570A「Decision-making method and system with staged reward as guidance」）在检索结果中出现，本次未核实其内容，**不作为证据引用**。

### 2.3 问题三：针对可预测的启发式对手取得优势

#### 2.3.1 支持侧的原文证据

| 来源（版本 / 评审） | 逐字关键句 | 支持什么 |
| --- | --- | --- |
| Lanctot 等，*A Unified Game-Theoretic Approach to Multiagent Reinforcement Learning*，[arXiv:1711.00832v2](https://arxiv.org/abs/1711.00832)（NIPS 2017，**同行评审**；本次读的是 camera-ready PDF） | 「we see that **PSRO/DCH are able to achieve higher performance against the fixed players**. Presumably, this is because the policies produced by PSRO/DCH are better able to recognize flaws in the weaker opponent's policies, **since the oracles are specifically trained for this**, and dynamically adapt to the exploitative response during the episode. So, NFSP is computing a safe equilibrium while PSRO/DCH may be **trading convergence precision for the ability to adapt** to a range of different play observed during training」；对应图题「Figure 6: Evaluation against **fixed set of bots**.」 | 针对固定对手集合专门训练的响应式策略，在该集合上确实优于安全均衡型策略；但这是**取舍**，不是白拿 |
| Billings 等，*Opponent Modeling in Poker*，AAAI-98, pp. 493–499，[cdn.aaai.org/AAAI/1998/AAAI98-070.pdf](https://cdn.aaai.org/AAAI/1998/AAAI98-070.pdf)（**同行评审**） | 「Thus, **a maximizing program will out-perform an optimal program against sub-optimal players** because the maximizing program will do a better job of exploiting the sub-optimal players.」；自对弈重复赛制 10 万手中「After 100,000 hands the SOM version was ahead roughly **$5,000**, while the BPM player had lost more than **$550 on average**.」 | 利用型（最大化型）策略对次优对手优于博弈论最优型 |
| Davidson 等，*Improved Opponent Modeling in Poker*（IC-AI 2000），[webdocs.cs.ualberta.ca/~games/poker/publications/ICAI00.pdf](https://webdocs.cs.ualberta.ca/~games/poker/publications/ICAI00.pdf) | 「This makes it **more successful against predictable players**, but also **more easily deceived against tricky opponents**.」；动作预测准确率「about **81%** of the time compared to **57%** for the old system.」 | 可预测对手是可利用的；但收益与「被反利用」同源 |
| Kurita 与 Hoki 2019（arXiv:1904.07491v1，预印本） | 把另外三家当作**固定概率的机会玩家**（见 2.1.1） | 麻将域达到当时最强水平的一手做法，本身就是「面向固定对手分布做优化」 |
| DeepMind 官方博客 *AlphaStar: Grandmaster level in StarCraft II*（[链接](https://deepmind.google/discover/blog/alphastar-grandmaster-level-in-starcraft-ii-using-multi-agent-reinforcement-learning/)，**官方项目文档，非同行评审**） | 「The key insight of the League is that playing to win is insufficient: instead, we need both main agents whose goal is to win versus everyone, and also **exploiter agents that focus on helping the main agent grow stronger by exposing its flaws**, rather than maximising their own win rate against all players.」 | 存在「专门训练利用型智能体」的成熟工程实践，但其用途是**陪练**而非对外作战策略 |

#### 2.3.2 限定与反对侧的原文证据

| 来源（版本 / 评审） | 逐字关键句 | 限定什么 |
| --- | --- | --- |
| Brown 与 Sandholm，Pluribus，**Science 365:885–890 (2019)**，[作者公开版 PDF](https://noambrown.com/papers/19-Science-Superhuman.pdf)（**同行评审**） | 「**shifting to an exploitative nonequilibrium strategy opens oneself up to exploitation because the opponent could also change strategies at any moment.** Additionally, **existing techniques for opponent exploitation require too many samples to be competitive with human ability outside of small games.** Pluribus plays a fixed strategy that does not adapt to the observed tendencies of the opponents.」；「despite **the lack of known strong theoretical guarantees on performance in multiplayer games**」 | 多人（>2）一般和博弈中，利用型策略无安全性保证；样本需求是硬约束 |
| Brown 与 Sandholm，Libratus，**Science 359:418–424 (2018)**，[作者公开版 PDF](https://noambrown.com/papers/17-Science-Superhuman.pdf)（**同行评审**） | 「**to a first approximation, Libratus did not perform opponent exploitation.** Instead, it used the data of the bet sizes that the opponents used to suggest which branches should be added to the blueprint」 | 顶级双人系统主动放弃利用以换取不可被针对（前提是两人零和有均衡保证） |
| Davidson 等 2000（同上） | 「Since strong players are able to detect this difference over time, they are able to **adapt their play to exploit this characteristic**. The lesson is that the modeling technique itself should be adaptive, based on the predictability of the opponent.」 | 激进建模的收益与自身可被预测程度绑定 |
| Billings 等 1998（同上） | 在线人类对局：「**not enough information has been gathered to safely conclude** that the opponent modeling versions of Loki are outperforming the previous best program in these games.」；「Humans are also very good at opponent modeling, and can be less predictable than the players in these simulations. **We have not yet investigated modeling opponents who vary their strategy over time.**」 | 作者自己声明封闭实验的收益不能外推到开放对手 |
| Johanson 与 Bowling，*Data Biased Robust Counter Strategies*，**AISTATS 2009, JMLR W&CP 5**，[PDF](https://webdocs.cs.ualberta.ca/~games/poker/publications/AISTATS09.pdf)（**同行评审**） | 「the limited data may be misleading or the opponent's strategy may have changed, suggesting an opponent-agnostic Nash equilibrium strategy」；「the model is likely formed through a limited number of observations ... and it may be incomplete ... or inaccurate. As we will show in this paper, **the restricted Nash response technique can perform poorly under such circumstances.**」；图 1(b)「we see how **a scarcity of observations results in poor counter-strategies**.」 | 基于历史数据的利用型策略在样本不足时**会退化**，瓶颈是样本量而非信息来源类型 |
| Goodman 与 Lucas，*Does it matter how well I know what you're thinking? Opponent Modelling in an RTS game*，[arXiv:2006.08659v1](https://arxiv.org/abs/2006.08659)（IEEE WCCI 2020，**同行评审**） | 「We show that **faced with an unknown opponent and a low computational budget it is better not to use any explicit model** with RHEA, and to model the opponent's actions within the tree as part of the MCTS algorithm.」 | 未知对手 + 低算力下，显式对手模型**反而有害** |
| Pluribus（同上），参考文献注释 | 「Recently, in the real-time strategy games Dota 2 and StarCraft 2, AIs have beaten top humans, but **as humans have gained more experience against the AIs, humans have learned to beat them**. This **may be** because for those two-player zero-sum games, the AIs were generated by techniques not guaranteed to converge to a Nash equilibrium.」 | 被适应后被打败的现实案例；注意作者用的是「may be」，属推断 |

#### 2.3.3 这些证据能支持什么（我的判断）

现有公开一手证据支持的是一个**条件命题**，不是无条件命题：

> **当对手分布固定、且该分布明显弱于均衡水平时，专门针对该分布训练的响应式或利用型策略，在同一分布上的表现可以超过安全均衡型策略。**

这个命题的三条支撑（PSRO、Billings 1998、Davidson 2000）都是在**研究者自设的封闭对手池**里验证的；麻将域的 Kurita 与 Hoki 是「把对手固定化为统计模型」的成功案例，但它建模的是**专家平均行为**，不是某个特定 Bot。**没有任何一条一手来源支持**「针对固定对手池优化后，在包含会观察并适应我方的对手、或强度更高的真实赛场里仍然更优」。

对本项目的含义（**工程建议**）：如果赛事的对手确实是固定的一批启发式 Bot 且不会针对我方调整，那么「针对该池优化」有证据支撑；但**这个前提本身是赛事观察问题，文献回答不了**。因此更稳的设计是「以稳健策略为主、把对手相关的调整限制在低风险范围内（例如防守阈值校准），而不是把全部筹码压在针对性建模上」。

### 2.4 问题四：开源麻将 AI 与论文如何评估强度

#### 2.4.1 逐项目做法（全部为项目官方资料或论文原文）

**A. Mortal（Equim-chan/Mortal，开源日麻 AI）**
来源：[docs/src/perf/strength.md](https://github.com/Equim-chan/Mortal/blob/main/docs/src/perf/strength.md)、[libriichi/src/arena](https://github.com/Equim-chan/Mortal/tree/main/libriichi/src/arena)、[mortal/one_vs_three.py](https://github.com/Equim-chan/Mortal/blob/main/mortal/one_vs_three.py)（访问 2026-09-14，main 分支；本次直接下载原文核对）。

- **对手池**：akochan（另一个开源 AI）或自家历史 checkpoint。文档小节标题即为「Mortal vs akochan」「Mortal vs Mortal」，并写明「Challenger is akochan and Champion is Mortal」，且有「Swapping Challenger and Champion」的反向重跑。
- **复式同牌山**：「The simulation employs a **1v3 duplicate mahjong** setup」，一套 4 局轮换座位；「each set of 4 games initialize with the same random seed. The emulator ensures that given the same `(seed, kyoku, honba)` combination, the walls, initial hands, dora/ura indicators, and rinshan tiles are deterministic and reproducible.」
- **样本量（原文表格取值举例）**：`"4.1c"`(×1) vs `"4.0"`(×3)：Games 1,000,000 / 3,000,000；`"3.1"`(×3) vs akochan(×1)：Games 39,456 / 13,152；另有「Seed: nonce=range(10000, 260000)」。
- **不确定性**：**完全没有**。对 strength.md 全文检索 `confidence`、`interval`、`variance`、`p-value`、`standard error`、`significan`，命中数为 0；只给点估计（率、Avg rank、Avg rank pt、总 Δscore）。
- **指标口径**：「The "rank pt" in all the tables are calculated using the distribution [90, 45, 0, -135].」

**B. Kanachan（Cryolite/kanachan，开源日麻 AI）**
来源：[kanachan/simulation/README.md](https://github.com/Cryolite/kanachan/blob/main/kanachan/simulation/README.md)、[官方 wiki: Methods and Metrics in Performance Comparison and Evaluation](https://github.com/Cryolite/kanachan/wiki/Methods-and-Metrics-in-Performance-Comparison-and-Evaluation)（访问 2026-09-14；本次直接下载原文核对）。

- **对手池**：「two given models are actually played against each other, and the statistical results obtained from a large amount of actual games are used as a benchmark for performance comparison.」对战风格有 1vs3、2vs2、3vs1。
- **复式同牌山**：wiki 明确定义「duplicate mahjong (複式麻雀)」；「in the 1vs3 style, there are a total of 4 possible seating arrangements ... so 4 games are played with the same tile wall but with different seating arrangements. These 4 games constitute one set of duplicate mahjong. ... The 2vs2 style has 6 possible seating arrangements for the two models, so 6 games with the same tile wall constitute one set.」
- **样本量单位**：以「套（set）」计，`-n` 指定套数；1vs3 一套 4 局，2vs2 一套 6 局。
- **不确定性（本项目最值得抄的一条）**：「For each metric, not only its mean value is shown, but also its **unbiased sample variance**. In addition, the **95% and 99% confidence intervals** for each metric calculated from the distribution that it (approximately) obeys are also provided.」并逐指标给出分布假设：「This obeys the **Student's t-distribution with n − 1 degrees of freedom**, where n is equal to (# of games) × PoV of the proposed model.」；首位率与连对率「obeys the **binomial distribution**, and its rate can be approximated very well by the normal distribution if the total number of games is reasonably large」；平均顺位差「is subject to a **paired difference test**」。
- **模拟环境**：可指定 baseline 模型「扮演的段位」与模拟房间（`--baseline-grade`、`--room`），即模拟段位战积分环境，而不是真的上天梯。

**C. Suphx（论文）**
来源：arXiv:2003.13590v2（见 2.1.4）。**真实天梯 + 固定池两条都用**：

- 线上（真实天梯）：「we let it play on Tenhou.net ... Suphx played **5000+ games** in the expert room and achieved 10 dan in terms of record rank and 8.74 dan in terms of stable rank.」
- 表 4 各参与者对局数：Bakuuchi 30,516；NAGA 9,649；Top human 8,031；Suphx 5,760。
- 不确定性的报告方式是**重采样分布**而非解析区间：「For each AI/human player, we randomly sample K games ... and compute the stable rank using those K games. We do such sampling for N times and show the statistics of the corresponding N stable ranks of each player in Figure 12.」「Statistics of stable ranks with **K = 2000 and N = 5000**.」
- 离线（固定对手池）：100 万局，「Each agent plays against 3 SL-weak agents」；「we randomly sampled **800K games from the one million games, for 1000 times**」，画的是四分位距（IQR）。
- 对样本量的官方说法（附录 C）：「it is usually assumed that **at least a few thousands of games are needed** to get a relatively reliable stable rank.」并指出天梯的对手由系统随机分配「brings in additional randomness」。

**D. Mizukami 与 Tsuruoka 2015（论文，早于上述开源项目）**
来源：IEEE CIG 2015, pp. 275–283（**同行评审**；取证方式见 2.1.3）。**这是本次找到的最早一份「复式 + 置信区间」的麻将 AI 评估实例**：

- **复式同牌山**：「We used a **match game type, which is a duplicate mode that generates the same walls and hands using the random numbers**, and allows us to compare the results of Mattari Mahjong plays and that of our program.」注意其用途是**配对比较**（同一牌山比较两个程序），而非仅降方差。
- **样本量与指标**：「**Our program plays 1000 games.** We use the **average rank** for evaluation.」
- **不确定性**：「We calculated the **confidence interval of the average rank (p-value = 0.05) using bootstrap resampling**.」并对组间差用 Welch t 检验报告 p 值（对前作 p = 0.01；对 Mattari Mahjong **p = 0.29**；天梯上对前作 **p = 0.22**）。
- **真实天梯对照**：同一篇论文同时给出天梯评分（rating 1718）与 rating 计算方式、初始 R = 1500、以及「average rank 改善 0.1 约对应 100 rating points」的换算。

**E. 官方赛事（IJCAI 国际麻将 AI 比赛，Botzone 平台）**
来源：[比赛官方页面](https://www.botzone.org.cn/static/gamecontest2026a.html)（访问 2026-09-14）。

- 用**赛制**而非统计区间控制运气：「Swiss-system tournament and **Duplicate Format** will be used」；「Stage 1: **256 rounds** of Swiss-system ... each group plays **24 games (full combinations of seating position)**」；「Stage 2: ... **512 rounds** of Swiss-system with each round consisting of **24 games**」。
- 官方成绩页只公布点估计分数与排名；对页面全文检索 `confidence`、`error`、`variance`、`interval`、`statistic` 命中数为 0。（**二手来源，未核实**：日本「麻雀AIコンテスト」的官方规则页本次未能访问，其时限与判罚口径不引用。）

#### 2.4.2 对照表

| 项目 | 对手如何确定 | 统计单位与样本量 | 不确定性报告 |
| --- | --- | --- | --- |
| Mortal | 固定对手池：akochan / 自家历史 checkpoint，交换 challenger 与 champion | 局（Games）；例 1,000,000 vs 3,000,000；nonce 扫 10,000–260,000 | **无**（关键词 0 命中） |
| Kanachan | 固定对手池：proposed vs baseline；模拟段位战与房间 | 套（set）：1vs3 一套 4 局、2vs2 一套 6 局；`-n` 指定 | **有**：均值 + 无偏样本方差 + 95%/99% 置信区间；t 分布（df = n−1，n = 局数 × PoV）、二项-正态近似、配对差检验 |
| Suphx（线上） | 真实天梯，系统随机分配对手 | 局（5000+；表 4 为 5,760） | 重采样分布（K=2000 × N=5000）；附录 C 说明「至少数千局」 |
| Suphx（离线） | 固定 3 个 SL-weak | 1,000,000 局；重采样 800K × 1000 | 四分位距图（IQR） |
| Mizukami 与 Tsuruoka 2015 | 固定对手池：三份 Mattari Mahjong（纯启发式程序） | 局（1000 局），**复式同牌山 + 配对比较** | **有**：bootstrap 重采样求平均顺位置信区间（p = 0.05）；组间差用 Welch t 检验报告 p 值 |
| 官方赛事（Botzone） | 瑞士轮按排名配对 | 轮 × 每轮 24 局（打满座位组合） | **无**（靠赛制压运气） |

#### 2.4.3 对本项目评估设计的直接含义（工程建议）

1. **统计单位必须写清楚**：Mortal 用「局」、Kanachan 用「套」、Suphx 用「局 + 重采样次数」——三者不可直接互换。本项目按 AGENTS.md 第 7 节以「完整桌赛 / 阶段 / seed」为单位，需在报告中显式声明换算。
2. **只做复式不给区间（Mortal、官方赛事）或只给区间不控牌山，都无法判定「是否真的变强」。**建议两者都做：同牌山换座位复式 + 按 Kanachan 的 t 分布/二项区间报告。
3. **固定对手池的结论只在池内成立**，必须在报告中写明对手池构成与版本（Mortal 的做法是把对手版本写进小节标题，值得照抄）。
4. **真实天梯不可得时的替代**：Suphx 用重采样分布代替解析区间、Botzone 用赛制代替统计——本项目若无法上天梯，应至少做「多牌山分组 + 聚类区间」。

### 2.5 问题五：可靠下限的工程共识

#### 2.5.1 平台侧的时限与代打

**官方已确认（日本天鳳）**：来源 [tenhou.net/man/](https://tenhou.net/man/) 的「■ 持ち時間」小节：

> 「表示：(標準の持ち時間）+（予備の持ち時間）」「標準の持ち時間を使い切ると予備の持ち時間を消費します」「**持ち時間が0になるとパスやツモ切りを行ないます**」（时间耗尽时由平台代替玩家执行 pass 或摸切）「ツモ巡に1秒以内（数字が出る前）に応答すると予備の持ち時間が1秒回復」「鳴きの応答では回復しません」「警告音（カチカチ）3回で時間切れ」「持ち時間は局開始毎に初期化」，以及两档数值「**普 5+10秒 / 速 3+5秒**」。

**官方已确认（Botzone 竞技麻将）**：来源 [wiki.botzone.org.cn 中文竞技麻将规则](https://wiki.botzone.org.cn/index.php?title=Chinese-Standard-Mahjong/en)：

> 「Notice: Botzone limits the program's calculation time, and **each interaction must be completed within 1 second for C++**!」

以及平台限制页的补充（由本次调研的子代理取得）：「每次运行，平台都要求程序在 1秒 内结束、使用的内存在 256 MB 内」「每场对局，每个 Bot 的第一回合的时间限制会放宽到原来的两倍」，并按语言给倍数（C/C++ 1 倍、Java 3 倍、C# 6 倍、JavaScript 2 倍、**Python 6 倍**）。

**我的判断**：两个平台给出的是**两种不同的下限范式**——天鳳在超时点**代打**（保证牌局继续），Botzone 只把超时记作 TLE 错误而**未承诺代打**。杭麻属于哪一类**未知**（**待确认假设**），因此在确认前，保底动作必须由我方在窗口内自行提交。

#### 2.5.2 Suphx：为时限放弃随时搜索

**来源事实**（arXiv:2003.13590v2）：

> §5 脚注 8：「Given that **Tenhou.net has time constraint for each action**, run-time policy adaptation was **not integrated** into Suphx while testing on Tenhou.net since it is time consuming.」
>
> §4.3：「run-time policy adaptation is time consuming due to the roll-outs and online learning. Therefore, at the current stage, we only tested this technique on **hundreds of initial rounds**. The wining rate of the adapted version of RL-2 against its non-adapted version is **66%**.」
>
> §3.4：「Monte-Carlo tree search (MCTS) is a well established technique in games like Go for run-time performance improvement. Unfortunately, as aforementioned, **the playing order of Mahjong is not fixed and it is hard to build a regular game tree. Therefore, MCTS cannot be directly applied to Mahjong.**」
>
> §2.1（唯一的非学习模块）：「Suphx employs another **rule-based winning model** to decide whether to declare a winning hand and win the round.」

**来源事实（论文未给出的）**：全文**没有**出现具体秒数（检索 `5 seconds`、`3 seconds`、`time limit`、`real time` 均无相关命中），只有定性的「time constraint」。要给出秒数必须引天鳳官方手册（见 2.5.1）。

**我的判断**：Suphx 的线上可靠性来自**「取消一切随时计算」**（五个前向推理模型 + 一个规则和牌模型），而不是「限时截断搜索」。这条证据支持「线上只做一次前向推理 + 规则保底」，反对把需要在线迭代/搜索/重训练的能力放进动作闭环。

#### 2.5.3 Mizukami 与 Tsuruoka：用阈值把昂贵搜索降级为廉价启发式

见 2.1.3。原文动机即「In opening states, Monte Carlo moves tend to play bad moves, **because the time that can be used for simulation is short**」，降级规则是「One-player Mahjong moves if Σ_{p∈opponents} EL(p, Tile) ≤ α; Monte Carlo moves otherwise」，α = 0.2。

**我的判断**：这是**「按状态裁预算」**的一手证据，可作为本项目「规则/启发式保底分支」的学术依据；但它不保证「停得下」，只保证「算得起」。本项目需要的第三种机制是：**候选动作先由规则层枚举（保证合法），再决定用哪个预算算分值**（AGENTS.md 第 6 节已要求）。

#### 2.5.4 「随时可中断」的正确口径

**来源事实**（Cowling 等 2012，IEEE TCIAIG 4(2):120–143）：

> §I：「MCTS has several strengths. It requires little domain knowledge ... **It is an anytime algorithm, able to produce good results with as much or as little computational time as is available.** It also lends itself to parallel execution.」
>
> §III-A：「**MCTS is an anytime algorithm**, requiring little domain knowledge.」

全文 `anytime` 仅出现这两次；`interrupt`、`time budget`、`time limit` 无相关命中。

**我的判断**：这是一条**常被过度延伸**的原文。论文声明的是 **MCTS 这一类**具有随时可中断（anytime）性质，**没有**为 ISMCTS 证明 anytime 性质，也**没有**给出「到点如何选最终动作」的规则。写「ISMCTS 保证随时可中断」属于超出原文的推断。正确口径是：**随时可中断只保证「能停」，不保证「停下来时手上一定有合法动作」**——合法动作保底必须由外层规则层负责。

#### 2.5.5 开源实现里的保底与降级（含负面结果）

| 项目（官方仓库） | 来源事实 | 是否有预算数字 |
| --- | --- | --- |
| Mortal | `libriichi/src/agent/tsumogiri.rs` 注释：「`Tsumogiri` always performs tsumogiri in all case and will not emit any action other than discard.」实现为「能打牌就打摸切牌，否则输出 `Event::None`」；`libriichi/src/mjai/bot.rs`：「Set `can_act` or `line_json['can_act']` to `False` to force the bot to only update its state without making any reaction.」 | **无**：对整个仓库检索 `timeout`/`deadline`/`fallback`/`time limit` 等关键词仅 2 处无关命中 |
| Kanachan | 同组关键词全仓库检索 **0 相关命中**；README 无延迟数字与降级描述 | **无** |
| gimite/mjai（mjai 协议参考实现） | `lib/mjai/tcp_player.rb`：`TIMEOUT_SEC = 60`；**静默断线**才代打 `{"type":"none"}`（合法 pass），**超时记为 error**；仓库附 `samples/tsumogiri_player.rb` 作为最小「永远合法」示例玩家 | **有**：60 秒 |

**本次调研的负面结论（有检索范围）**：在 Mortal、Kanachan、gimite/mjai 这三个官方仓库中，**没有找到**「动作级时间预算 + 超时前提交保底动作 + 模型失败自动降级到启发式」的完整公开实现。**我的判断**：这套机制在开源日麻 AI 里是缺失的，本项目需要自己设计，不能照抄。

### 2.6 问题五之外新增问题：对手身份不可信与「伪装实力」

（本节对应上级在调研中途追加的问题，独立成节。）

#### 2.6.1 是否存在「故意隐藏真实实力」的公开先例

**来源事实 A（棋类官方规则，一手）**：

- FIDE *Fair Play Regulations 2024*（[PDF](http://handbook.fide.com/files/handbook/FPL_Regulations_2024.pdf)，**官方规则文档**）第 8 页：「**Sandbagging refers to deliberately playing below one's actual ability in order to lower one's rating to play in a future event with a higher handicap and consequently with a better chance of winning.**」
- FIDE *Anti-Cheating Regulations*（[PDF](https://handbook.fide.com/files/handbook/ACCRegulations.pdf)，**官方规则文档**）：「"Cheating" in these regulations means: ... b) the manipulation of chess competitions such as, including but not limited to, result manipulation, **sandbagging**, match-fixing, rating fraud, **false identity**, and deliberate participation in fictitious tournaments or games.」

**来源事实 B（棋类官方判例）**：FIDE Ethics and Disciplinary Commission, Case no. 9/2025, "Alleged sandbagging at chess competitions"，判决 2025-07-31（[官方决定书](https://ethics.fide.com/wp-content/uploads/2025/08/CASE-9-2025-FINAL-DECISION_.pdf)）：

> 「the only plausible explanation for losing all games in two consecutive tournaments is **intentional defeat**」；认定「committed cheating through the **method of sandbagging**」，全球禁赛 6 个月。
>
> **同一决定书的异议意见**：「Professor Regan's report ... explicitly states that his statistical model is not validated for use in situations such as this. He writes, "**My model has not been validated for use on the lower extreme of the bell curve**" ... making it clear that his system cannot form a sound basis for determining guilt.」

**来源事实 C（平台官方条款）**：

- PokerStars 服务条款：「**You are only allowed one Account on the Website.**」
- Chess.com Fair Play Policy：「**Do not allow anyone else to use your account. Do not use anyone else's account.**」「**Do not artificially manipulate ratings, matches, or game outcomes.**」
- Kakao Games（Eternal Return）官方公告 *Smurfing (Malicious Use of Secondary Accounts) Policy Update*：「Disrupting matches or intentionally causing losses using a secondary account」被列为恶意使用；并承认技术限制：「**it's extremely difficult to definitively disprove claims like "it was not me, it was a family member who was playing" from a purely technical standpoint.**」

**来源事实 D（AI 系统自身的「策略性低表现」，一类先例而非比赛实例）**：

- van der Weij 等，*AI Sandbagging: Language Models can Strategically Underperform on Evaluations*，[arXiv:2406.07358v4](https://arxiv.org/abs/2406.07358)（**ICLR 2025，同行评审**）：「we define sandbagging as **strategic underperformance on an evaluation**」。
- Tice 等，*Noise Injection Reveals Hidden Capabilities of Sandbagging Language Models*，[arXiv:2412.01784v3](https://arxiv.org/abs/2412.01784)（**NeurIPS 2025，同行评审**）：「we find noise-injection is capable of eliciting the full performance ... in a setting where the model underperforms **without being instructed to do so**」。

**未找到（明确缺口）**：在**有奖金或晋级机制的竞技 AI 比赛**（Kaggle、ACPC 计算机扑克竞赛、RTS/电竞天梯）中，**没有找到**「参赛方故意用弱账号/弱身份隐藏真实实力」的公开实例。Kaggle 官方规则原文本次也未能取得（其规则页为前端渲染），因此**本文不引用任何 Kaggle 处罚说法**。ACPC 官网文本中检索不到 `anonymous`，**不能声称其设有匿名赛制**。

**我的判断**：可以写进方案的事实是——**「故意隐藏实力」在规则世界已被正式定义并有判例（棋类），在平台条款层面被普遍禁止，在 AI 评测层面被形式化复现；但在有奖金的 AI 比赛中没有可查证的公开实例。**另有两点值得注意：其一，FIDE 把 sandbagging 与 **false identity** 并列在同一作弊清单里，说明「身份不可信」与「实力不可信」在治理层面是同一个问题的两面；其二，**连 FIDE 的官方判定都依赖一个被异议成员质疑「未被验证」的统计模型**——这提示「识别对手是否在装弱」本身是高风险判定，任何基于对手行为的推断都带同样的不确定性。**工程建议：不要设计依赖「判定对手是否装弱」的逻辑。**

#### 2.6.2 「身份键对手建模」与「当局公开行为推断」的鲁棒性

**结论先行（我的判断）**：**没有找到任何一篇论文以「身份键 vs 当局行为」为自变量做受控比较实验**（明确「未找到」）。但存在四条互相独立的证据链，共同指向「身份不可信时，身份键建模退化」。

**证据链 1：顶级系统明确声明不使用对手身份、不做跨局适应（来源事实）**

- Pluribus（Science 365:885–890, 2019）：「**Pluribus does not adapt its strategy to its opponents and does not know the identity of its opponents**, so the copies of Pluribus could not intentionally collude against the human player.」
- Libratus（Science 359:418–424, 2018）：「to a first approximation, Libratus did not perform opponent exploitation」，取而代之的是「universal: They work against all opponents」的策略修正（**二手来源，未核实**：该 `universal` 句由本次调研的子代理从作者公开版 PDF 提取，本文作者仅核对了前一句）。
- DeepStack（arXiv:1701.01724v3，Science 356:508–513）：「continual re-solving **never keeps track of the opponent's range**」。

**必须同时写清楚的限定**：这些系统放弃的是**利用型（exploitative）身份画像**，它们仍然维护**当局的贝叶斯范围**（对手手牌分布）。所以正确的结论是「**不需要身份**」，**不是**「不需要任何对手推断」。

**证据链 2：基于历史交互数据的利用型策略被证明脆弱（来源事实）**

Johanson 与 Bowling，AISTATS 2009（**同行评审**，见 2.3.2）：把「利用过去与该对手交互的数据」与「对未见过对手安全的无对手均衡策略」明确对置，并证明前者在数据有限时会退化。

**我的判断**：这是最接近本命题的原始论述，但它给出的机制解释是**瓶颈在样本量，而不在信息来源类型**——这意味着即使改成「当局行为推断」，只要当局信息量不足，同样会退化。这条区分非常重要，不能把「身份不可信」当成「当局推断就安全」的理由。

**证据链 3：多智能体领域的「类型键」方法论批评（来源事实）**

Mirsky 等，*A Survey of Ad Hoc Teamwork Research*，[arXiv:2202.10450v3](https://arxiv.org/abs/2202.10450)（arXiv 元数据标注 EUMAS 2022，**同行评审**）：

> 「**Type-based methods.** ... **It is assumed that new teammates encountered by the learner have behaviors specified by one of these types.**」
>
> 「For type-based methods, it is typical to **assume each teammate's type does not change over time** ... if a teammate changes to a type which the learner has assigned low (or zero) probability to ... the learner might struggle (or be unable) to quickly update its belief to reflect the new true teammate」

**我的判断**：身份键建模的底层假设是「同一身份 ⇒ 同一稳定类型」；这条假设一旦被违反（换人、故意伪装、策略迭代），模型就失效。注意这是**综述**（其论断来自它引用的原始工作），本节按「来源事实」引用其表述。

**证据链 4：「身份不可信」本身的理论与官方依据（来源事实）**

- Douceur，*The Sybil Attack*，IPTPS 2002（**同行评审 workshop**）：「**without a logically centralized authority, Sybil attacks are always possible except under extreme and unrealistic assumptions** ... it is always possible for an unfamiliar entity to present more than one identity」。
- Kakao Games 官方公告（见 2.6.1 来源 C）：平台自己承认账号归属在技术上无法证伪。

**来源事实 E（当局内推断的原始论述）**：Southey 等，*Bayes' Bluff: Opponent Modelling in Poker*，[arXiv:1207.1411](https://arxiv.org/abs/1207.1411)（UAI 2005，**同行评审**）：「In all cases we compute a response at the beginning of the hand and play it for the entire hand.」「**It seems likely that the posterior distribution does not converge quickly against a non-stationary opponent**」，「extending the approach to non-stationary approaches is under active investigation」。

**我的判断（对本项目的直接含义）**：文献里更稳健的做法**不是**「改用当局推断」，而是**把画像的作用域限制在一场/一个阶段内，并以稳健策略作为安全底座**（Ganzfried 与 Sandholm 的 DBBR 只在「throughout the match」内累积计数；Libratus 的策略修正对**所有**对手通用）。**工程建议**：本项目若要做对手画像，作用域应设为**单场/单阶段**，账号 ID 不作为主键，且必须保留不依赖画像的基线策略路径。

#### 2.6.3 「自适应激进程度」的公开证据与所需观察量

**来源事实（唯一找到的量化数字，两人有限注扑克）**：Ganzfried 与 Sandholm，*Game Theory-Based Opponent Modeling in Large Imperfect-Information Games*，[AAMAS 2011 PDF](https://ifaamas.org/Proceedings/aamas2011/papers/B4_R56.pdf)（**同行评审**）：

> 「**we ran GS5 for the first 1000 hands of each match and recomputed an opponent model and best response every 50 hands subsequently** ... Since each match consists of **3000 duplicate hands**, this means that GS5 and DBBR play the same strategy for the first third of each match.」
>
> 「We set T = 1000 since it is essential that our algorithm **obtains a reasonable number of samples of the opponent's play** ... **before attempting to exploit**.」
>
> 「In both of these matches, **the win rate decreases significantly for the first several hundred hands before it starts to increase**.」

**来源事实（麻将域的自适应不是对对手强度的适应）**：Suphx 的运行时策略适应（pMCPA）适应的是**自己的初始手牌**（「he/she will play aggressively to win more given a good initial hand, and conservatively to lose less given a poor initial hand」），其 100K 是**模拟轨迹条数**（计算预算），不是「观察对手多少手」；且「the policy adaptation is performed for each round independently」，并且**没有上线**。

**未找到**：麻将或其他多人不完全信息博弈中，「**根据观察到的对手实际强弱**调整进攻/防守需要多少局内观察才生效」的公开数字——**未找到**。

**我的判断**：唯一的量化数字（1000 手预热 + 其后数百手负收益）来自**两人零和、有限注、同一对手连续对局、对手为固定风格 bot**的设定，**不能换算成麻将局数**。本项目若要给出「观察多少局后开始调整」的参数，必须标注为**外推假设**并自行实测。

#### 2.6.4 反面证据：对手建模收益有限或容易过拟合

| 来源（评审） | 逐字关键句 | 反面结论 |
| --- | --- | --- |
| Pluribus（Science 2019，同行评审） | 「existing techniques for opponent exploitation **require too many samples to be competitive with human ability outside of small games**」 | 六人桌下因样本量而不可用 |
| Libratus（Science 2018，同行评审） | 「to a first approximation, **Libratus did not perform opponent exploitation**」 | 利用对手 = 暴露自己被利用 |
| Johanson 与 Bowling（AISTATS 2009，同行评审） | 「the restricted Nash response technique **can perform poorly** under such circumstances」（模型不完整/不准确/观测有限） | 基于历史观测的对手模型会退化 |
| Goodman 与 Lucas（IEEE WCCI 2020，同行评审） | 「faced with an unknown opponent and a low computational budget **it is better not to use any explicit model**」 | 未知对手 + 低算力下显式模型有害 |
| Suphx（预印本，§3.3） | 「(2) **We ignore opponents' behaviors** and only consider drawing and discarding behaviors of our own agent.」 | 麻将顶级 AI 在自己的前瞻特征里主动忽略对手行为 |
| Southey 等（UAI 2005，同行评审） | 「the posterior distribution **does not converge quickly against a non-stationary opponent**」 | 非平稳对手下当局推断同样慢 |
| Caen 等，*StratFormer*，[arXiv:2604.25796v1](https://arxiv.org/abs/2604.25796)（arXiv 元数据标注 "Accepted at Computers and Games 2026"，**待正式出版**） | 「StratFormer achieves an **average exploitation gain of +0.106 BB per hand over GTO**, with peak gains of **+0.821 against highly exploitable opponents**」 | 现代方法在小游戏（Leduc）上平均收益也很小；只有对手高度可被利用时收益才大 |

**我的判断**：反面证据的密度高于正面证据，且方向一致——**对手建模的期望收益小、方差大、需要大量样本，并在对手未知、非平稳或算力受限时变差**。文献中持续使用对手建模的场景，几乎都限定在**小游戏**或**对手明显弱且稳定**的前提。

---

## 3 各机制的增益与成本对照表

下表把本文涉及的机制放在一起，**「增益证据强度」列是本文作者对一手证据充分程度的评级，不是来源给出的数字**。所有数字均可在第 2 节找到出处。

| 机制 | 一手来源报告的增益 | 成本／门槛（原文） | 适用边界 | 增益证据强度 |
| --- | --- | --- | --- | --- |
| 手牌价值 = 最终名次分布 × 名次收益 + 抽象搜索 | 3557 局平均顺位 2.23 ± 0.04 vs 当时最强 AI 2.29 ± 0.04（单尾显著水平 0.03） | 每次决策「a few seconds」；对局实验耗时「several months using an ordinary desktop PC」 | 固定对手池（1 强 + 2 弱 MCTS）；东风战规则；差异幅度小 | **中**（有直接实验，但差异边界显著、期刊版未核对） |
| 全局奖励预测（把局末奖励分摊到各圈） | 作者报告 RL-1 优于 RL-basic，且示例显示行为从「争这一圈」转为「保第 1 名」 | 需要专家对局日志训练 GRU；本身算力需求小 | 多圈赛制；奖励表由赛制定义 | **中**（有消融与定性示例，未给单一数字） |
| 蒙特卡洛 + 对手建模（把对手行为拆成听牌/待牌/点数三要素并用专家牌谱训练） | 复式 1000 局平均顺位 **2.48 ± 0.07 vs 2.51 ± 0.07，差异不显著（p = 0.29）**；天梯 rating **1718**，但对前作平均顺位差**不显著（p = 0.22）** | 每次蒙特卡洛着法 **1 秒**；阈值降级（α=0.2） | 固定对手（含纯启发式程序）；作者自陈改进体现在对程序一侧、**未体现在对人类玩家一侧** | **弱到中**（同行评审，但主要对比是零结果） |
| 信息集搜索（MO-ISMCTS） | LOTR:C 上 ≥3 秒时显著强于确定化 UCT | 每迭代比确定化 UCT 慢 **2–4 倍**；1 秒内迭代数约为其 1/3 | **1 秒时略逊**；Phantom(4,4,4) 上算力越多反而越弱 | **中**（同行评审，但域不是麻将） |
| 针对固定对手池专门训练（PSRO/DCH） | 「higher performance against the fixed players」 | 需要针对该池训练 oracle；代价是牺牲收敛精度 | 研究者自设固定 bot 集合 | **中**（同行评审，域为 Leduc） |
| 利用型对手建模（扑克） | 自对弈 10 万手：SOM 领先约 $5,000，无建模版本平均亏损 > $550 | 需要大量对局样本；会提高自身被利用程度 | 封闭自对弈池；作者自陈不能外推到开放对手 | **中** |
| 基于行为历史的现代利用（StratFormer） | Leduc 上平均 +0.106 BB/手；对高度可被利用对手峰值 +0.821 BB/手 | 两阶段训练 + 每个对手的正则化日程 | 极小游戏（6 张牌） | **弱到中**（待正式出版） |
| 跨场次账号画像 | 未找到任何直接量化其增益的一手来源 | 需要身份稳定假设；平台官方承认归属无法证实 | **无来源支持在身份可疑下使用** | **弱**（本文未找到正面证据） |
| 复式同牌山评估 | 不产生「增益」，是**降方差**手段（Mortal、Kanachan、Botzone 官方赛制均采用） | 需要可复现发牌（同 seed 同牌山）与换座位 | 固定对手池 | **强**（三个独立项目 + 官方赛制） |
| 置信区间报告 | 同上，是**判定手段**；Kanachan 官方规定到指标分布假设一级 | 需要明确统计单位与分布假设 | 固定对手池内 | **强**（Kanachan 官方 wiki） |
| 阈值降级（昂贵搜索 → 廉价启发式） | 不产生增益，是**保底**手段 | 需要两套可切换策略与阈值 | 任意 | **强**（Mizukami 与 Tsuruoka 有明确阈值） |
| 超时前提交保底合法动作 | 不产生增益，是**保底**手段 | 需要规则层枚举合法候选 | 平台不承诺代打时是必需项 | **弱**（本次在三个开源项目中**未找到**完整公开实现） |

---

## 4 证据薄弱或相互矛盾之处

1. **「在中等强度对手场取胜」的两条直接证据里，有一条是零结果。**这是本文最重要的一条负面发现。Kurita 与 Hoki 的 3557 局报告了优势（平均顺位 2.23 ± 0.04 vs 2.29 ± 0.04，单尾显著水平 0.03，属边界显著）；但 Mizukami 与 Tsuruoka 在 1000 局复式对局中**对纯启发式程序 Mattari Mahjong 的优势在统计上不显著（p = 0.29）**，在真实天梯上对前作的平均顺位差同样不显著（p = 0.22），作者自陈改进「**未体现在对人类玩家一侧**」。**结论：不能把「对手是启发式程序」当成「我们更容易赢」的保证。**
2. **Kurita 与 Hoki 的期刊版未核对。**本文引用的是 arXiv v1（2019），而同一工作已发表为 IEEE Transactions on Games 13(1):99–110（2021）。期刊版是否修订了 3557 局、2.23 ± 0.04 等数字，**本次未核实**。任何对外引用应先取期刊版核对。
3. **Mizukami 与 Tsuruoka 2015 的引文未经版面比对。**该文 IEEE 闭源；本文引文由本文作者**直接从作者实验室托管 PDF 的部分下载字节中解压内容流提取**（文本为可直接提取的编码）。因此引文用词可核对，但**未与 PDF 排版逐页比对**，且该 PDF 的**完整下载在本次会话内未完成**。**「1 秒/次」「α=0.2」「1000 局」「p = 0.29」这四个数字在正式对外引用前应再核对一次完整 PDF 或 IEEE 版。**
4. **ISMCTS 论文内部就存在方向矛盾的结果。**LOTR:C 上 ISMCTS 优于确定化；Phantom (4,4,4) 上超过约 1.5 秒后反而随算力变弱；斗地主上 1 秒内 SO-ISMCTS 略弱。**「ISMCTS 更好」不是无条件结论**，本项目不能以「用了 ISMCTS」作为正确性论证。
5. **「anytime」被过度延伸。**原论文只声明 **MCTS 类** anytime，未为 ISMCTS 证明，也未给出到点选动作的规则。任何「随时可中断 ⇒ 一定有合法动作」的推论都超出原文。
6. **对手建模的正面证据与反面证据不对称。**正面证据（PSRO、Billings、Davidson、Kurita 与 Hoki）都在**研究者自设的封闭对手池**中取得；反面证据（Pluribus、Libratus、Johanson 与 Bowling、Goodman 与 Lucas）来自更强的系统与更一般的设定。**引用正面证据时必须连带引用其封闭池限定。**
7. **「身份键 vs 当局行为推断」没有受控比较实验。**本文明确**未找到**。四条证据链只是**间接**支持「身份不可信 ⇒ 身份键退化」，且 Johanson 与 Bowling 的机制解释（瓶颈是样本量而非信息来源类型）**削弱**了「改用当局推断就能解决」的推论。
8. **「需要多少局内观察才能自适应」完全没有麻将域证据。**唯一的量化数字来自两人有限注扑克（1000 手预热）。任何把它折算成「杭麻需要 N 局」的说法都是**外推假设**。
9. **平台超时判罚口径在杭麻未知，且两个参照平台不一致。**天鳳代打、Botzone 只记 TLE。**不要用日本平台的行为推断杭麻平台的行为。**
10. **算法**「随时搜索」**被顶级系统主动放弃**，而**「有界搜索」在 1 秒窗口内的证据是负面的**（ISMCTS 1 秒时略逊）。这意味着本项目的搜索必须做得**足够小、足够早剪枝**，而不是「用搜索换强度」。这是本文所列证据里对路线选择最不利的一条。
11. **麻将域的「提升」可能只对程序成立、对人不成立。**Mizukami 与 Tsuruoka 自陈「our program improves the result against Mattari Mahjong. On the other hand, **it does not improve the result against human players**」。这提示：**在固定对手池里测出的提升，未必对应「更强的麻将」**——评估报告必须显式声明提升是针对哪个对手总体测得的。
11. **两处内部矛盾/不一致的记录**：（a）Suphx 论文只有定性的「time constraint」而无秒数，但常被转述成具体秒数——正确做法是引天鳳官方手册；（b）官方赛事（Botzone）用复式赛制压运气但**不报告任何统计区间**，与 Kanachan 的官方协议是两种范式，不能互相替代。
12. **本次未找到的项目（明确缺口）**：把「赛事晋级概率」作为学习目标的公开研究；麻将域「对手观察量 → 自适应生效」的数字；Kaggle 官方规则原文；日本「麻雀AIコンテスト」官方规则页；竞技 AI 比赛中「故意用弱账号隐藏实力」的公开实例；三个开源日麻仓库中的「超时前提交保底动作 + 模型失败降级」完整实现。

---

## 5 来源与访问说明

### 5.1 来源清单

| 编号 | 来源 | 链接 | 版本／评审状态 | 访问日期 |
| --- | --- | --- | --- | --- |
| S1 | Kurita、Hoki，*Method for Constructing AI Player with Abstraction to MDPs in Multiplayer Game of Mahjong* | [arXiv:1904.07491v1](https://arxiv.org/abs/1904.07491) | 预印本 v1（2019-04-16）；期刊版 IEEE ToG 13(1):99–110 (2021-03)，[DOI](https://doi.org/10.1109/TG.2020.3036471)，**未取得全文** | 2026-09-14 |
| S2 | Cowling、Powley、Whitehouse，*Information Set Monte Carlo Tree Search* | [White Rose 作者投稿版](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf) | IEEE TCIAIG 4(2):120–143, 2012，**同行评审** | 2026-09-14 |
| S3 | Mizukami、Tsuruoka，*Building a Computer Mahjong Player Based on Monte Carlo Simulation and Opponent Models* | [DOI](https://doi.org/10.1109/CIG.2015.7317929)；IEEE CIG 2015, pp. 275–283；作者实验室公开托管版 [PDF](https://www.logos.t.u-tokyo.ac.jp/~tsuruoka/papers/cig2015mizukami.pdf) | **同行评审会议论文**；IEEE 闭源；引文由本文作者从托管 PDF 的**部分下载分块**解压内容流提取，**未做版面比对** | 2026-09-14 |
| S4 | Li 等，*Suphx: Mastering Mahjong with Deep Reinforcement Learning* | [arXiv:2003.13590v2](https://arxiv.org/abs/2003.13590) | **预印本**（无 Journal reference／会议 DOI） | 2026-09-14 |
| S5 | Kurita、Hoki 期刊版书目数据 | [Crossref 10.1109/TG.2020.3036471](https://api.crossref.org/works/10.1109/TG.2020.3036471) | 书目元数据（非正文） | 2026-09-14 |
| S6 | Mizukami、Tsuruoka 书目数据 | [Crossref 10.1109/CIG.2015.7317929](https://api.crossref.org/works/10.1109/CIG.2015.7317929) | 书目元数据（非正文） | 2026-09-14 |
| S7 | Mortal 强度评估文档 | [docs/src/perf/strength.md](https://github.com/Equim-chan/Mortal/blob/main/docs/src/perf/strength.md) | 官方仓库文档，main 分支 | 2026-09-14 |
| S8 | Mortal 文档首页与 README | [docs/src/index.md](https://github.com/Equim-chan/Mortal/blob/main/docs/src/index.md) | 官方仓库文档 | 2026-09-14 |
| S9 | Mortal 模型源码（名次预测模块） | [mortal/model.py](https://github.com/Equim-chan/Mortal/blob/main/mortal/model.py) | 官方仓库源码 | 2026-09-14 |
| S10 | Kanachan 评测程序文档 | [kanachan/simulation/README.md](https://github.com/Cryolite/kanachan/blob/main/kanachan/simulation/README.md) | 官方仓库文档 | 2026-09-14 |
| S11 | Kanachan 官方 wiki：评价方法与指标 | [Methods and Metrics in Performance Comparison and Evaluation](https://github.com/Cryolite/kanachan/wiki/Methods-and-Metrics-in-Performance-Comparison-and-Evaluation) | 官方 wiki | 2026-09-14 |
| S12 | 天鳳官方手册（持ち時間） | [tenhou.net/man/](https://tenhou.net/man/) | **官方已确认** | 2026-09-14 |
| S13 | Botzone 官方 wiki：中文竞技麻将规则 | [Chinese-Standard-Mahjong/en](https://wiki.botzone.org.cn/index.php?title=Chinese-Standard-Mahjong/en) | 官方 wiki | 2026-09-14 |
| S14 | IJCAI 国际麻将 AI 比赛官方页面 | [gamecontest2026a.html](https://www.botzone.org.cn/static/gamecontest2026a.html) | 赛事官方页面 | 2026-09-14 |
| S15 | Pluribus（多人扑克） | [作者公开版 PDF](https://noambrown.com/papers/19-Science-Superhuman.pdf) | Science 365:885–890 (2019)，**同行评审** | 2026-09-14 |
| S16 | Libratus（双人扑克） | [作者公开版 PDF](https://noambrown.com/papers/17-Science-Superhuman.pdf) | Science 359:418–424 (2018)，**同行评审** | 2026-09-14 |
| S17 | PSRO | [arXiv:1711.00832v2](https://arxiv.org/abs/1711.00832) | NIPS 2017 camera-ready，**同行评审** | 2026-09-14 |
| S18 | Billings 等，*Opponent Modeling in Poker* | [AAAI-98 PDF](https://cdn.aaai.org/AAAI/1998/AAAI98-070.pdf) | AAAI-98, pp. 493–499，**同行评审** | 2026-09-14 |
| S19 | Davidson 等，*Improved Opponent Modeling in Poker* | [IC-AI 2000 PDF](https://webdocs.cs.ualberta.ca/~games/poker/publications/ICAI00.pdf) | 同行评审会议（会议名来自官方文件名，正文未标注） | 2026-09-14 |
| S20 | Johanson、Bowling，*Data Biased Robust Counter Strategies* | [AISTATS09 PDF](https://webdocs.cs.ualberta.ca/~games/poker/publications/AISTATS09.pdf) | AISTATS 2009, JMLR W&CP 5，**同行评审** | 2026-09-14 |
| S21 | Ganzfried、Sandholm，*Game Theory-Based Opponent Modeling in Large Imperfect-Information Games* | [AAMAS 2011 PDF](https://ifaamas.org/Proceedings/aamas2011/papers/B4_R56.pdf) | **同行评审** | 2026-09-14 |
| S22 | Goodman、Lucas，*Opponent Modelling in an RTS game* | [arXiv:2006.08659v1](https://arxiv.org/abs/2006.08659) | IEEE WCCI 2020，**同行评审** | 2026-09-14 |
| S23 | Southey 等，*Bayes' Bluff: Opponent Modelling in Poker* | [arXiv:1207.1411](https://arxiv.org/abs/1207.1411) | UAI 2005，**同行评审** | 2026-09-14 |
| S24 | Mirsky 等，*A Survey of Ad Hoc Teamwork Research* | [arXiv:2202.10450v3](https://arxiv.org/abs/2202.10450) | arXiv 元数据标注 EUMAS 2022，**同行评审**（综述） | 2026-09-14 |
| S25 | Douceur，*The Sybil Attack* | [PDF](https://www.freehaven.net/anonbib/cache/sybil.pdf) | IPTPS 2002，**同行评审 workshop** | 2026-09-14 |
| S26 | Meowjong（三人麻将 AI） | [arXiv:2202.12847v3](https://arxiv.org/abs/2202.12847) | **预印本** | 2026-09-14 |
| S27 | Gilbert，*The Independent Chip Model and Risk Aversion* | [arXiv:0911.3100](https://arxiv.org/abs/0911.3100) | **预印本**（math.PR） | 2026-09-14 |
| S28 | Caen 等，*StratFormer* | [arXiv:2604.25796v1](https://arxiv.org/abs/2604.25796) | arXiv 元数据标注 Accepted at Computers and Games 2026（**待正式出版**） | 2026-09-14 |
| S29 | DeepMind 官方博客，AlphaStar | [官方博客](https://deepmind.google/discover/blog/alphastar-grandmaster-level-in-starcraft-ii-using-multi-agent-reinforcement-learning/) | **官方项目文档，非同行评审** | 2026-09-14 |
| S30 | FIDE *Fair Play Regulations 2024* | [PDF](http://handbook.fide.com/files/handbook/FPL_Regulations_2024.pdf) | 官方规则文档 | 2026-09-14 |
| S31 | FIDE *Anti-Cheating Regulations* | [PDF](https://handbook.fide.com/files/handbook/ACCRegulations.pdf) | 官方规则文档 | 2026-09-14 |
| S32 | FIDE EDC Case no. 9/2025（sandbagging 判例） | [决定书 PDF](https://ethics.fide.com/wp-content/uploads/2025/08/CASE-9-2025-FINAL-DECISION_.pdf) | 官方决定书 | 2026-09-14 |
| S33 | Kakao Games，*Smurfing Policy Update* | [官方公告](https://playeternalreturn.com/posts/news/2834?hl=en-US) | 发行商官方公告 | 2026-09-14 |
| S34 | van der Weij 等，*AI Sandbagging* | [arXiv:2406.07358v4](https://arxiv.org/abs/2406.07358) | ICLR 2025，**同行评审** | 2026-09-14 |
| S35 | Tice 等，*Noise Injection Reveals Hidden Capabilities of Sandbagging LMs* | [arXiv:2412.01784v3](https://arxiv.org/abs/2412.01784) | NeurIPS 2025，**同行评审** | 2026-09-14 |
| S36 | gimite/mjai（mjai 协议参考实现） | [lib/mjai/tcp_player.rb](https://github.com/gimite/mjai) | 协议作者官方仓库 | 2026-09-14 |

### 5.2 访问与核实说明

1. **本文作者直接核实的内容**：S1、S2、S3、S4、S7–S14、S15–S23、S25、S27、S33 中除个别标注外的引文，均由本文作者下载原文并提取文本后核对。其中 S2、S4、S11、S12、S13、S15、S17、S18、S19、S20 的关键句为逐字比对；**S3 的引文由本文作者从托管 PDF 的部分字节解压内容流提取后核对**（该 PDF 文本为可直接提取的编码，见 2.1.3 取证说明）。
2. **由本次调研的子代理取得、本文作者未二次比对的内容**：S16 中 `universal` 一句、S24、S26、S28–S35 的部分引文。本文已在对应位置标注「未经二次比对」或「二手来源，未核实」。
3. **已知的访问失败／未取得**：
   - 作者实验室托管的 Mizukami 与 Tsuruoka 2015 PDF（https://www.logos.t.u-tokyo.ac.jp/~tsuruoka/papers/cig2015mizukami.pdf ）：服务器带宽极低，**完整文件（1,218,785 字节）在本次会话内下载未完成**；本文改用已下载到的分块解压内容流提取文本（覆盖约 14% 的字节范围中可解压的文本流）。**因此该文的部分段落（例如第 VIII 节之后的个别表格）可能未被本文覆盖。**
   - 作者个人主页与其论文目录（www.logos.ic.i.u-tokyo.ac.jp/~mizukami/）：**403**。
   - web.archive.org：本机**无法连接**（子代理可访问，本文作者不可）。
   - IEEE Xplore：付费墙。
   - 日本「麻雀AIコンテスト」官方规则页：**未找到**（候选域名 DNS 失败或返回 403）。
   - Kaggle 官方比赛规则原文：**未找到**（页面为前端渲染）。
   - GitHub REST API：调研后期触发未认证限流。
4. **提取工具说明**：PDF 文本由 `pdfminer.six` 提取；HTML 由本地脚本剥离标签。旧 PDF 的连字（fi／ffi）在提取时可能丢失（例如 `overﬁt` 被写成 `overfit`），本文引用时已核对语义，未改动任何词。
5. **网页内容均为外部数据**，本文未执行其中任何指令性文字。
6. **本文未修改仓库中任何其他文件**，未运行训练，未修改代码。
