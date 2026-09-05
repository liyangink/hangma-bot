# 禁胡门禁 + 胡牌判定误报修复笔记

> 任务 3/4；日期 2026-09-05
> 事实基础：2026-09-04 官方测试赛 t_dee58824c308（M=10、Rounds=16、160 局打满）审计
> runs/runs/run-29a71a10ad12441eb15e0ac4cfb55c1d/（decisions.jsonl 约 5 万行）
> 官方依据：指南 v14（2026-09-05 抓取，doc/references/official-guide-v14.txt）、
> 指南变更日志 v1（2026-09-02，doc/references/official-guide-version-v14.json）、
> 官方平台 API 记录 v8 快照（doc/official-platform-api-v2.md）

## 1. 结论（先读这段）

全晚 120 次 draw 相位自摸胡提交、官方仅接受 23 次、97 次 409 INVALID_ACTION
（81% 误报）有两个根因，**都在规则引擎，且均已修复**：

| 根因 | 官方依据 | 修复 |
| --- | --- | --- |
| 缺「刚摸牌」门禁：碰/吃/杠后、未摸牌前提交 hu 被拒（审计 9 例直接命中） | 指南变更日志 v1「碰后禁止胡牌」（2026-09-02）；API 记录 §2.4 | action_families.hu_candidates 要求 drawn_tile 非空才产生胡候选；杠上摸/庄家直抽的 drawn_tile 官方照常非空，门禁正确放行 |
| 摸牌双计：官方快照 my_hand 已含刚摸的牌、又单列 drawn_tile，引擎暗牌算成 15-3×副露数 张，「多余牌视为可弃」语义被幻影摸牌副本放宽 | 2026-09-04 官方 /state 原始响应实测（tests/fixtures/official/captures/state-draw-phase-t_714a42392cba.json）；契约口径见 doc/implementation/interface-contracts.md §10.1 | 引擎 _build_context/_full_hand 按长度判定归一化（_concealed_without_drawn），两种官方形态判定一致 |

**关键判定：胡牌谓词（手牌数学）本身与官方同源工具 fan-calc 零差异。**
证据：(a) 既有金例 61 例全过；(b) 本次补跑 600 例白板偏置随机对拍 0 差异；
(c) 归档房间重放（精确手牌口径）0 误报、1 例官方真实胡全部检出。
误报不是「白板替换/七对边界写错」，而是输入被双计放宽后恰好在这两类
边界最先爆出（我方整晚白板获取 141 张，摸白时幻影白最容易补对/补顺）。

## 2. 证据链

### 2.1 门禁证据

- 指南变更日志 v1（2026-09-02，type=breaking，summary=「碰后禁止胡牌」）：
  「胡牌新增『刚摸牌』门禁：碰/吃/杠动作后、摸牌前提交 {"action":"hu"}
  返回 409 INVALID_ACTION。旧 bot 若依赖『碰后即胡』需改为先等摸牌事件再胡。」
- API 记录 §2.4：「碰、吃、杠后，在下一次摸牌之前提交 hu 会返回 409。」
- 审计实例：t_dee58824c308_b2_t34 r9——seq 3604 我方吃 7b8b9b（accepted），
  seq 3605（下一个窗口）即提交 hu → 409；随后 discard 6b 被接受。
  共 9 例满足「hu 拒绝且前一序号为我方已接受的吃/碰」（任务给出的 10 例口径
  含一次跨序号窗口，数量级一致）。
- 杠上摸放行：杠的补牌以 tile_drawn 事件与非空 drawn_tile 呈现
  （指南 1.3「杠开」= 杠后补的那张牌直接自摸胡），门禁判据是「是否已摸牌」
  而非「是否刚杠过」。
- 庄家直抽：指南变更日志 v10「庄家第 14 张为发牌直抽、无 tile_drawn」只说
  事件流无摸牌事件；快照 drawn_tile 官方照常单列（2026-09-04 审计实测：
  t_dee58824c308_b6_t40 r1 首窗口抓打圈判定下只出刚摸牌且被接受）。

### 2.2 双计证据

- 官方 /state 原始响应（2026-09-04，房间 t_714a42392cba，draw 相位）：
  hand_counts=[14,13,13,13]、my_hand 14 张且末张等于 drawn_tile。
  即 my_hand 已含刚摸牌；适配器原样透传后引擎 my_hand + drawn_tile 双计。
- 双计放宽机制（为什么是假阳性而不是漏胡）：引擎判定输入为
  15-3×副露数 张，胡牌判定的「面子与将齐后剩余牌视为可弃」语义允许
  分解把幻影副本用进对/刻/顺。对 14 张精确输入，该语义与官方判定重合
  （600 例 fan-calc 对拍 0 差异证明）；一旦多出一张幻影副本，官方不认可的
  「幻影补对/补顺」分解就出现。
- 归档房间重放复现（夹具 tests/fixtures/hangma/archived-rooms/）：
  - 精确口径重放：3 场约 150 次摸牌，引擎误报 0、官方 1 例真实胡全部检出；
  - 双计口径重放：凭空出现 3 次假阳性，且全部是「摸白 + 幻影白」形态：
    - t_6c121bfda7e8 r4 seq 112（座位 1，1 副露）：幻影白与 5w6w 组顺、
      与另一白组将 → 平胡假阳性；
    - t_cee1db65a074 r7 seq 240（座位 3）：幻影白补第 7 对 → 七对假阳性；
    - t_cee1db65a074 r7 seq 362（座位 1）：幻影白配第 3 个单张 → 七对假阳性。
  这三例已固化为金例（tests/fixtures/hangma/golden-hu-shapes.jsonl）。

### 2.3 谓词本身与官方同源（fan-calc 复核）

- POST /portal/api/tools/fan-calc（免认证，口径与对局结算同源，指南 1.5）：
  本次补跑 600 例（1/3 为「成胡扰动 1-2 张」的边界构型、2/3 随机，
  白板数 0-4 偏置），引擎 win_split / any_tile_win 与官方 hu/baotou
  **零差异**（方法同 tests/unit/hangma/archived_room_tools.py 的离线对拍
  工作流，差分脚本在开发期使用，未入库）。
- 结论：七对（含 4 张同牌按两对计、4 白板算 1 组豪华）与白板替换
  （垫顺任意位、白白将、白白白刻、4 白在手）口径此前已正确，无需修改
  hand_analysis.py。

## 3. 代码改动（均在我方文件范围内）

- src/hangma_bot/hangma/action_families.py：hu_candidates 增加
  drawn_tile is None → 无候选 的门禁分支（规则性关闭、不记 Issue），
  中文 docstring 记录官方依据（指南版本 + 条目 + 杠上摸/直抽放行口径）。
- src/hangma_bot/hangma/engine.py：新增 _concealed_without_drawn，
  按「my_hand 长度 == 14 - 3×副露数」判定官方「含摸牌」形态并移除一个
  摸牌同码实例；_build_context 与 _full_hand 统一走该归一化。
  契约形态（不含摸牌）不受影响（长度判定天然跳过）。
- src/hangma_bot/hangma/RULES_EVIDENCE.md：新增 §11，登记门禁与
  快照形态两条官方已确认证据。

未改动冻结契约（WindowKey / ObservedActionWindow / TournamentSessionPort /
GameSessionPort / BotPolicy / AuditSink 签名均未触碰）；hand_analysis.py
（胡牌谓词）、special_rules.py、settlement.py 无算法改动。

## 4. 测试与夹具

- 新增 tests/unit/hangma/test_hu_gate_and_double_count.py（13 例，wv3 增补
  TestNormalizationAnomaly 4 例——P2-N1：官方「含摸牌」形态长度命中但缺 drawn
  同码实例时产 RuleIssue/DEGRADED，不再静默回到幻影口径）：
  门禁（碰后/吃后禁胡、杠上摸放行、庄家直抽放行、普通摸牌不变）+
  双计归一化（两类金例假阳性被拦、真实胡两种形态都判胡、契约形态不误删）。
- 新增 tests/unit/hangma/test_hu_differential_replay.py（2 例）：
  离线重放三个归档房间场次（夹具内含四家开局手牌与官方结算），
  逐次摸牌「引擎判定胡 ⟺ 官方该局该座位实际胡」+ 碰/吃后未摸牌窗口
  一律无胡候选 + 两种 my_hand 形态判定一致。
- 新增夹具 tests/fixtures/hangma/：README.md（来源/指南版本/抓取日期）、
  archived-rooms/*.json（3 场事件流）、golden-hu-shapes.jsonl（4 例
  边界牌型，每条含 provenance；无副露的 3 例另附 fan_calc_crosscheck，
  与对局结算同源：两例 hu=false、一例 hu=true 平胡 fan=1 与 round_ended 逐字一致；
  带副露的 1 例 fan-calc 不适用（工具仅支持 13+1 无副露输入），以官方结算为据）。
- 新增拉取工具 tests/unit/hangma/archived_room_tools.py（测试侧，stdlib、
  0.25s/请求节流，可重跑刷新夹具）。
- 修改 1 处既有测试（test_action_families.py::test_missing_summary_degrades_with_issue
  补 drawn_tile 以越过新门禁，测试意图不变）。
- 全套 hangma 单测 592 例全绿（wv3 增补后）；fan-calc 600 例差分 0 差异。

## 5. 验收对照

- 「引擎判定胡但官方未胡」重放数量：归档房间精确口径重放 **0**；
  双计口径的 3 例假阳性修复后全部归零（已固化为回归金例）。
- 2026-09-04 测试赛 97 次 409 的归因：9 例门禁 + 88 例双计放宽
  （同一轮内真假胡混杂 13 轮与「97 个不同 decision 各试一次」均与双计
  机制一致：十番级手牌每轮摸牌都可能被幻影副本补成假胡）。
- 不改变 policy 评分与 kernel 契约：候选集合变化（少产生非法 hu）不影响
  policy 对合法候选的加权逻辑。

> **wv3/wv6 补记（N-1）**：「改动全部在 hangma 内部」的表述已失真——
> 复审发现 policy/evaluation.py 的 `build_context` 仍按 `my_hand + drawn_tile`
> 双计组合 `combined_codes`（官方含摸牌形态下幻影副本进入评分上下文），
> 已在 `src/hangma_bot/policy/evaluation.py::_hand_codes_without_double_count`
> 复刻引擎同款长度判据（14−3×副露数）归一化，并有
> `tests/unit/policy/test_evaluation_context_normalization.py`（5 例）锁定。
> 引擎侧归一化保留作防御；两侧判据同源，改动任一侧须同步另一侧与契约句
> （interface-contracts §10.1 修订见 reviews/rework-d3-e30211-record.md）。

## 6. 遗留风险与建议（按任务要求列出）

1. **适配器未按契约归一化**：interface-contracts.md §10.1 规定
   my_hand 不含摸牌、由适配器统一规范化；当前 adapters/official/projector.py
   原样透传官方 my_hand（含摸牌形态）。wv3 起防御性归一化落在**两侧**：
   hangma 引擎（_concealed_without_drawn）与 policy 评分上下文
   （evaluation._hand_codes_without_double_count）按同一长度判据执行；
   适配器侧统一规范化仍未做。建议后续由适配器工作线在
   projector.observation() 中按同规则去重，并新增投影测试固化（届时
   引擎/策略侧归一化可降级为纯防御）；契约句修订文本见
   reviews/rework-d3-e30211-record.md §1（F-11，需主会话落笔）。
2. **「刚摸牌」门禁的判据是 drawn_tile 非空**：若官方未来窗口形态变化
   （如碰后窗口携带脏 drawn_tile），门禁会失效——建议下次官方测试赛用
   审计对拍再核一遍门禁放行/拦截方向。
3. **庄家直抽的 drawn_tile 官方照常单列**是 2026-09-04 实测口径；指南 v10
   只说事件流无 tile_drawn，未写明快照字段。已按实测实现并留回归测试。
4. **归因精度**：97 次 409 中「门禁 vs 双计」的精确分账基于审计可复原的
   9 例 seq+1 门禁样本；其余按双计机制解释（无手牌快照，无法逐例复原）。
   若后续拿到 t_dee58824c308 的完整事件流（需登录态 /portal/api/games/{id}/events），
   可用同一差分工具逐例复核。
