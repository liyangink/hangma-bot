# 主线可用策略枚举

2026-10-04更新：新testroom_v6／free_v4已完成T161自由赛和T163四席M10/R8快速测试房的真实工程验收；对局摸切、429、计算故障/重启均0，原截止、限深1、公式和稳定默认版本不变。T163一只过评分超期及两只过零规划例外保留，严格零降级false；T161缓发虽开启但因快照时间依据不足全跳过，不能授缓发改善信用。T148强度false仍保留，正式/测试赛事发布门未授。详情见[验收报告](../../review/vip-route-2026-09-30/evidence/t163-received-fix-fast-four-seat-testroom-1/REPORT.md)。

省略 `strategy` 时，代码默认仍为 `weighted_heuristic`（V0），不会自动选择最新策略。2026-09-29 的连续自由赛运行清单使用显式配置的 `r18_integrated_positive_v2`；模板、代码默认值和实际运行身份是三件事，后者须从相应运行清单核对。当前进化与接线结论从[研究证据索引](../../review/INDEX.md)进入。

| 枚举值 | 支持的运行模式 | 说明 |
| --- | --- | --- |
| `weighted_heuristic` | 全部 | 冻结V0，省略配置时的默认值 |
| `weighted_heuristic_v1` | 全部 | 冻结V1，历史对照 |
| `weighted_heuristic_v2` | 全部 | 稳定基线；Tier-A 的对照基准 |
| `r18_integrated_positive_v1` | 历史冻结范围为 `test_room` / `test_tournament` / `auto_match`；**当前主线规则下拒绝装配** | 旧包绑定原规则源码，没有制作当前规则的新包；历史身份保留，不是默认策略 |
| `r18_integrated_positive_v2` | 历史四种模式；当前main规则源码绑定不匹配，拒绝重新装配 | 原评分源码和旧包保留，未绕过旧摘要；需要另行验证新绑定，既有旧运行身份不受重写 |
| `vip_s02_bounded_d1_testroom_v6` | 仅 `test_room`，显式绑定当前包 ID、SSE | T159完整回信回收修复包，尚未联网；旧v5完整10桌零摸切／对局429／计算故障，但1仅过评分迟到，旧包与证据保留 |
| `vip_s02_bounded_d1_free_v4` | 仅显式实验 `auto_match`，绑定当前包 ID、SSE | T159修复新包，尚未联网；旧v3十桌+112仅观察性，零我方摸切、2状态429及3处可能损失碰／杠机会，不授独立增强或正式赛事 |
| `v2_hu_upgrade_v1` | **全部（含正式赛事）** | V2有界等胡（Tier-A）；下方是 2026-09-11 的本地验证快照，不代表当前最强策略。2026-09-18 起冻结：后续数值调整一律走 `v2_hu_upgrade_v2` |
| `v2_hu_upgrade_v2` | 全部（与 v1 同口径） | **新参数批次载体**：与 v1 同结构，只换 `policy/weights_v1.py` 的 `V2_PARAM_BATCH_WEIGHTS`。2026-09-18 着陆时该常量与冻结 V2 逐字相同（零行为变更），数值由「一次一个参数、单独提交 + 策略目录门禁」逐步标定；候选取值与扫描协议见 `review/test-tournament-20260917/policy-param-batch-spec-2026-09-18.md` |
| `v2_balanced_shadow_v1` | **仅 `test_room` / `auto_match`** | 多路线前沿审计层：复用 `v2_hu_upgrade_v1` 保底并追加路线理由，**不改变动作顺序**；不得用于正式赛事提交 |
| `weighted_heuristic_v2_white_guard` | 全部 | V2普通弃财保护变体。**已证明为无行为差异**（V2 与 Tier-A 上各 256 桌，符号检验 0 正/0 负/256 平）——保留是因为有 21 处测试/脚本/对手池引用，不要当作独立候选再验 |
| `safe_fallback` | 全部 | 规则紧急动作，保底/诊断用途 |
| `claim_if_legal` | 解析器接受全部，用途限测试 | 主动鸣牌探针，不推荐自由赛策略比较 |
| `catch_play_probe` | 仅测试房 | 抓打圈取证探针，可将弃白排在胡前，不用于争取积分 |

## `r18_integrated_positive_v1` 测试与自由赛冻结包

**当前主线状态（2026-09-29）：**下述旧身份只适用于原规则源码；新增吃碰后继事实后，旧 v1 发布包会在装配时拒绝规则摘要漂移。它保留作历史对照，不能把解析器接受该策略名误作当前可启动。[G194](../../review/freematch-deep-dive-20260925/G194-R18-V2-RULE-BINDING-RESULT-2026-09-29.md)只为活动的 R18 v2 制作了新规则绑定包。

该枚举是候选 `r18_integrated_positive_v1` 的真实环境发布包，不是离线研究名的别名。发布包身份为
`0b6c39204f0fcaf094b4ea3c5f9cceae2d97e50c62461107602817a3ff40bc1a`，候选源码摘要为
`0d3c094d9ee5f5fd0316d0c3db7563523ce1d8d2fafb0e64d3d9b93817909b2d`。每次运行的
`RUN_MANIFEST.policy_release` 都保存完整候选身份、允许模式、规则范围、完整规则源摘要及 P45—P48/P55 证据摘要。
记录端对该受控子树内的严格 SHA-256 做路径限定豁免，包 ID 不再被通用长串脱敏误删。
运行配置必须另写 `expected_policy_release_id`，值为上述完整包 ID。缺失、旧摘要或普通策略误带该字段均在
联网前拒绝；测试房入口把同一摘要传给四个身份。这样同名策略在发布包轮换后不能沿用旧配置静默启动。

只允许以下环境：

- `test_room`：验证四身份隔离、协议、规则、恢复和动作时限；
- `test_tournament`：执行官方测试赛事发布门禁；
- `auto_match`：收集自由赛完整桌和真实机会触发证据。

适用规则固定为 `hangma-mvp-v10-public-counts`、底分 1、`YouCaiBiKao=false`，最低已适配官方指南为 v34。房间规则不符或配置声明的已知指南低于 v34 时在动作前
拒绝该候选身份。`official_tournament` 继续由组合根拒绝，默认策略也不改变。离线研究名
`action_value:r18_integrated_positive_v1` 在所有网络模式中仍被拒绝。配置样例见
`configs/r18-integrated-positive-v1.*.example.json`。测试房与测试赛事的专用冻结包及离线装配验收见
`review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/`
`r18-p59-network-mode-freeze-01-20260923/`。

## `v2_hu_upgrade_v1`（Tier-A）历史发布状态

**2026-09-11 接线变更：解除模式限制。** 此前它被限制在 `test_room` / `auto_match`，现在四种模式
（`test_room` / `test_tournament` / `official_tournament` / `auto_match`）均可显式选择。
**放开的是"可选性"，默认值仍是 V0**，必须显式写配置才生效：

```json
{"strategy": "v2_hu_upgrade_v1"}
```

本地门禁五项判据全部通过：

| 判据 | 读数 |
| --- | --- |
| 完整桌赛净分正 | +4.586（对冻结 V2） |
| 按根聚类 95% 区间下界为正 | [2.784, 6.388]，256 根 |
| 精确二项符号检验 | 56 正 / 6 负，p < 1e-4 |
| 第一名比例不退化 | 通过 |
| 时限与降级计数 | 全 0 |

**发布前须知（不要按 +4.586 外推）：**

- 真实房 2 对 2 配对 A/B **功效不足**：−9.30 [−27.65, +9.05]，每场配对差 sd 29.6——这是"测不出来"，不是否证。
- 强对手池（对手 = 3 x Tier-A）重跑：**+1.945 [−0.445, +4.219]，不显著**。⇒ **对外部对手的预期收益应按 +2/场 量级估计。**
- **官方测试赛事门禁未跑过**。本地门禁不能替代它（见根 `AGENTS.md` §7）。

增强范围为底分1、`YouCaiBiKao=false`、规则版本 `hangma-mvp-v10-public-counts`。自由赛实际规则不适用时
完整退回 V2 并审计，继续完成已入席房间；测试房仍拒绝不适用配置。风险参数来自 V2 模拟对手池，
不代表真实对手风险已校准。配置、生效核验、条件事实和验证结果见[接入说明](v2-hu-upgrade-experimental.md)。

## 已移出清单的实验臂（2026-09-11）

以下枚举**已从 `_STRATEGY_FACTORIES` 删除，模块与单元测试一并移除**。它们不是"待验证"，
而是**已被证据关闭**；研究记录保留在 `review/heuristic-balanced-2026-09-10/`，不要再当作候选重测：

| 已移除枚举 | 关闭理由 |
| --- | --- |
| `v2_hu_upgrade_tierb_v1` / `v2_hu_upgrade_tierb_v3` | 概率档等胡**显著负**：正确支付版 −2.301 [−4.117, −0.734]，符号 1/11，p=0.0063 ⇒ 放宽"可证明性"本身有害 |
| `v2_hu_upgrade_dealer_v1` | 庄位速度偏置**显著负**：−1.168 [−4.297, +1.902]，符号 46/38 |
| `v2_hu_upgrade_dealer_v2` | 庄位权重 v2 **显著负**：−0.520 [−4.355, +3.375]，符号 57/59 |
| `v2_value_upgrade_v1` | 一摸价值层叠加**无增益**：+1.733 但中位 0、符号 98/94、p=0.773 |
| `v2_hu_upgrade_risk_v3` | 风险表 v3 **结构性空操作**：差分 0/10,769 窗口 |
| `v2_hu_upgrade_white_guard_v1` | "等胡 x 护白"组合臂中护白**结构性空操作**：256 桌 x 2 组，符号 0 正/0 负/256 平 |
| （`route_preserve`） | 路线保留**从未注册**，4,359 窗口无系统增益；本次一并删除死代码 |

另：`v2_hu_upgrade_v1` 的等胡轴**两侧已封口**——放宽侧（Tier-B）与收紧侧（`safety_margin` 0.60/0.70/0.85
分别 −1.85 / −3.41，符号 10/32 与 11/49）均显著负，而 `safety_margin <= 0.55` 是结构性空操作
（咬合边界 0.55–0.60）⇒ **当前 `safety_margin = 0.10` 就在本轴最优点上，继续调参无路**。

## 研究枚举与后端说明

`one_draw_value_v1`、`hu_upgrade_v1`、`v2_claim_piao_v1`、`v2_seven_pairs_wait_v1` 等研究枚举
**没有在主线接入中开放**。主线虽然包含等胡实现依赖的分值工具类，但不能因此把类名当成可配置策略。
（`v2_seven_pairs_wait_v1` 的独立验证结论是"没有证明整桌净分提升，保持稳定选用 V2"；
`v2_claim_piao` 的记录结论是"无增量"。）

`c_grouped`/`python_grouped` 是规则数学后端，`YouCaiBiKao` 是平台规则配置，均不是策略枚举。
