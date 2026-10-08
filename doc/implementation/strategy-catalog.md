# 主线可用策略枚举

## 2026-10-09：共享存储迁移

当前正式赛采用 P0 approved-v5，测试房、测试赛事和自由赛采用 G37-RF1 v2 包装；策略枚举保持原值。目录迁移只重冻结源码摘要，算法、规则、编译体及原批准资格保持。参赛配置见[操作说明](../participate-quickstart.md)，公共工具与本机历史边界见[研究索引](../research/INDEX.md)。下文日期段是交付时快照。

## 2026-10-09：实验默认与真实并发验证

**测试房、测试赛事和自由赛默认改用G37-RF1；正式锦标赛默认仍为P0 approved-v4。** 用户已恢复自由赛，M10/R16四席同RF1测试房与M10/R8自由赛并行运行。原算法、规则、编译体和动作预算保持；新独立控制器只适配修复准入与不同认证域的玩家检查，共用原全局Token owner和后台统计锁。真实160单局压力与自由赛结果待自然完赛，不写成已通过。[当前操作、冻结根和验收](../research/materials/vip-route-2026-09-30/evidence/t227-rf1-default-and-live-1/README.md)。下文T226的默认/暂停描述是交付时快照。

## 2026-10-08：G37-RF1 独立可选评分修复（修复发布）

**四个 G37-RF1 策略已作为独立可选修复版发布，当前获启动准入；参赛默认保留 P0。** 资格类型为评分缺陷修复（`scoring_defect_repair`，修复故障 G37 的费用恒压与可胡分支自然质量未传递）；该修复不表示 P0 规则有误，也不授强度晋级。

| 策略枚举 | 唯一运行模式 | `configs/` 内模板 | 当前资格 |
| --- | --- | --- | --- |
| `vip_g37_rf1_testroom_v1` | `test_room` | `vip-g37-rf1-v1.test-room.example.json` | 修复准入，非强度晋级 |
| `vip_g37_rf1_free_v1` | `auto_match` | `vip-g37-rf1-v1.free-match.example.json` | 修复准入，非强度晋级 |
| `vip_g37_rf1_test_tournament_v1` | `test_tournament` | `vip-g37-rf1-v1.test-tournament.example.json` | 修复准入，非强度晋级 |
| `vip_g37_rf1_official_tournament_v1` | `official_tournament` | `vip-g37-rf1-v1.official-tournament.example.json` | 修复准入，非强度晋级 |

启动准入字段（`startup_admitted`，允许该冻结包在指定模式启动）为 `true`，绑定已获批的真实修复、原生评分等价、原截止及时合法和代表性回归收据。强度准入字段（`strength_admission`，相对稳定版本的增强资格）保持 `false`。按[当前修复验收](../research/materials/vip-route-2026-09-30/evidence/t224-G38-four-source-effect-1/REPAIR-ACCEPTANCE.md)，不要求 +8 或参加官方现场比赛；正式／测试赛事另验基础接线、配置与包作用域和生命周期。

RF1 编译目录为 `prebuilt/vip-g37-rf1-compiled-v1/`，复用 S03 合法保底、原生规则后端（`native`，已核验的 C 数学实现）、原截止和服务器通知流（`SSE Notify Stream`，事件水位通知）。独立预热 10 个每桌专属工作进程，`max_pending=0`；配置必须明确选择本模式策略与对应冻结包，不能因枚举存在而忽略准入。资源及依赖见[架构](../architecture.md#g37-rf1-独立可选评分修复接线2026-10-08)。

本轮实包和回归结果见[G37-RF1交付报告](../research/materials/vip-route-2026-09-30/evidence/t226-minimal-scoring-repair-1/REPORT.md)；真实自由赛继续暂停，接线不自动启动比赛。

## 2026-10-08：P0参赛发布包装

**P0 四模式当前使用 `approved-v4` 清单与 `configs/vip-s03-rulefix-p0-approved-v4.*.example.json` 模板，策略枚举仍为 `vip_s03_rulefix_p0_*_v1`。** v2迁移启动依赖，v3重新冻结此前主线更新后的源码；v4仅因 `bootstrap.py` 增加 RF1 接线造成包源码清单（`source_manifest`，运行源码路径及摘要）漂移而重冻，候选身份、原公式、核心、二进制、旧批准资格、参数及原截止保持。9件批准原件随 `prebuilt/vip-s03-rulefix-p0-release-evidence-v1/` 交付，运行无需 `review/` 或 `datasets/`。旧包装保留，测试赛v2快照不重写，旧摘要不自动升级。目录和验签边界见[架构](../architecture.md#参赛发布依赖独立交付2026-10-08)。

## 2026-10-06 T194：T110-S03-E2审计工程后继

**E2只减少审计同步重复编码，不改变S03公式、38核心、D1、原截止、QPS或十桌专属计算。** S03四scope v3；S02备用testroom_v12/free_v10/两赛事v4。八包绑定同183完整来源，全部旧包逐字保留并在新来源下明确拒装。正式／测试赛事只验基础接线及生命周期，实际工程房和自然切换由总筹执行；未授strict/OPERABILITY通过。

`JsonlAuditSink.emit`在返回前仍拥有新不可变字符串，结构快速编码复用原protect、最终字符串扫描、restore及JSON编码；敏感键下非JSON秘密先整值脱敏。非原生形态、typed键或坏context立即回旧路径，不能额外消费自定义容器。高优先级、队列容量、失败计数、后台写盘、关闭和快照所有权不变。公开`redact_json_line(str)`原语义保留；新增内部`redact_record_line(envelope)`同步返回完整字符串或None（需旧路径），不排队、不写盘、不修改输入。

3对真实1.55MB记录实省46.562–60.500ms，中位52.250ms；20ms计时器仍迟，不能冒称原477ms完全解释或漏吃已修。初次自定义dict红例保留，公共E1对照26+5同字节、相关175pass/1历史缺夹具skip。证据及候选边界见[本轮工程交付](../../review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/engineering/AUDIT-READOUT.md)。

## 2026-10-06 T192：T110-S03-E1工程后继

**E1只接入已复核的适配器可靠性修复，不改S03公式、确认CID或算法强度范围。** S03四模式分别为`vip_s03_bounded_d1_testroom_v2`、`vip_s03_bounded_d1_free_v2`、`vip_s03_bounded_d1_test_tournament_v2`、`vip_s03_bounded_d1_official_tournament_v2`；S02备用为testroom_v11、free_v9及两赛事v3。八包绑定同183件完整运行来源；旧八包保存并在新来源下明确拒装。38件S03核心、编译公式／共享助手、C数学、D1、原截止／QPS和10个每桌专属进程不改。

`OfficialGameSession.aclose`只对尚未取消的本场owned任务发cancel，shield等待HTTP／SSE finally完成后才返回；重入不二次打断，调用者取消完成收尾后传播。永久不协作关闭并未被证明可回收。无兴趣响应单步只在新鲜snapshot-first、同单局／phase／弃牌周期、非本人下家、无抓打圈／保留墙／未决动作时暂缓一次GET；不推进last_seq、不猜timeout，原1.2秒探针与核验失败关闭过滤保持。下一未知帧照常读取。

正式／测试赛事只验基础接线、配置绑定和生命周期，按用户2026-10-06[现行口径](../research/materials/vip-route-2026-09-30/evidence/t192-targeted-followup-1/ACCEPTANCE-POLICY.md)执行；官方现场不是候选上线门。上线与真实必要测试房由总筹按已有授权在旧房自然边界接入，副本不启动网络玩家、迁移watchdog或触碰Token。旧S03实测与效果证据复用，不冒称新工程包已联网；两次真实worker故障仍未知。当前核验与模板见[工程后继交付](../../review/vip-route-2026-09-30/evidence/t192-targeted-followup-1/wiring/REPORT.md)。

## 2026-10-06 T191：T110-S03候选与S02备用

**S03是成熟胡等待的单项修复；当前是否启用查实际交接与玩家身份。** 独立冻结混合池净分通过，伴随大牌收入下降，不授榜前或晋级优势。[公式、接线及运行证据](../../review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1/README.md)。

| 策略 | 唯一模式 | configs内模板 |
| --- | --- | --- |
| `vip_s03_bounded_d1_testroom_v1` | `test_room` | `vip-s03-bounded-d1-v1.test-room.example.json` |
| `vip_s03_bounded_d1_free_v1` | `auto_match` | `vip-s03-bounded-d1-v1.free-match.example.json` |
| `vip_s03_bounded_d1_official_tournament_v1` | `official_tournament` | `vip-s03-bounded-d1.official-tournament.example.json` |
| `vip_s03_bounded_d1_test_tournament_v1` | `test_tournament`兼容 | `vip-s03-bounded-d1.test-tournament.example.json` |

S03格式`vip-route-bounded-release/3`，必须对应完整包ID和SSE。S02当前来源备用为测试房v10、自由赛v8、两类锦标赛v2；旧包不因名称相近恢复资格。正式模板须真实赛事ID和专用Token；测试锦标赛已取消，兼容包不要求该活动ID。

## 2026-10-05 T191：原S02赛事运行候选

用户于2026-10-05确认官方测试锦标赛已无安排，不再等待其开放。测试赛事模式和历史未执行记录保留；后续按[当前验收依赖纠正](../../review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/ACCEPTANCE-CORRECTION-2026-10-05.md)使用工程生命周期、必要测试房及自由赛证据，并核正式赛实际配置。

**四个独立模式候选已整合主线，自由赛已自然迁移为free_v7。** 测试房后继 `vip_s02_bounded_d1_testroom_v9`、自由赛后继 `vip_s02_bounded_d1_free_v7`、测试赛事 `vip_s02_bounded_d1_test_tournament_v1`、正式赛事 `vip_s02_bounded_d1_official_tournament_v1` 各自只能绑定一个模式及完整包ID。包仍为 `vip-s02-bounded-release/2`，绑定实际完整源码、C数学后端和四模块编译原件；旧v8/v6清单及旧R18摘要拒绝保留。候选装配范围不授实际官方测试赛事、独立强度、生产默认或正式上线。

赛事组合根复用 `ParticipantRuntime` 与 `TournamentSupervisor`，预热在初始化/报名/到位前完成，规则分析始终先准备合法保底。实际规则只接受 `hangma-mvp-v10-public-counts`、底分1、`YouCaiBiKao=false`；实际 `config.M` 超过10时在报名/到位前拒绝，不静默缩小容量。应用按 `active_games` 取得/回收每桌专属槽，使用原增强/保底/提交截止；空集合不等于结束，动态阶段、候补资格、阶段中断及决赛新场次继续走既有生命周期。

十个同步3秒弃牌窗的同一绝对截止检查已观察到10次及时合法提交，其中部分窗口按原增强截止跳过完整评分；不能因此授十窗全评分门。实际正式赛事ID、开赛时间、M/Rounds、时限及规则配置仍待取得；自由赛持续积累真实接线证据，不等待已经没有安排的测试锦标赛。证据与门禁详见[T191接线报告](../../review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wiring/REPORT.md)。

测试房启动器的 `load_room_config` 复用新后继包核验；`child_config_mapping` 逐身份透传精确包ID与SSE，四份凭证仍只经隔离子进程环境注入。自由赛身份不能误接测试房；不启动子进程也能通过公开解析与派生接口检查。

明确拒绝后合法备用（`rejected_emergency_backup`，同一权威窗口中原规则紧急候选确认未执行且被拒后，准备同次合法集中未拒的动作）在主评分之前按动作键确定并审计。原规则无紧急候选或合法集全拒时仍为空；窗口变更与 `AMBIGUOUS` 不走追加提交。应用统一核对备用的合法键及动作，并在提交前调用唯一规则引擎复核。完整S02评分与排名优先，备用仅补缺，标记 `is_emergency=false`，不修改规则紧急身份、不重授原预算。它修复原紧急候选被拒后评分失败或增强截止已过时无可提交退路的缺口；SafeFallbackPolicy 的既有语义保持。

2026-10-04 T179当前枚举：已启用实验 `testroom_v8` / `free_v6`，冻结包格式 `/2`，绑定四模块编译制品、181件运行源码及每桌专属计算。396项回归、10原预算工厂及四席小房通过；自由赛M10/R8已实际开打。旧v7/v5及R18旧绑定只保留历史身份，摘要漂移保持拒装，不重授正式门。[当前接线与验收](../../review/vip-route-2026-09-30/evidence/t179-production-wiring-1/REPORT.md)。下方为历史快照。

2026-10-04 T167当前枚举：T110新testroom_v7/free_v5与当前规则R18测试对照只增加实验接线，不改公式或正式门。137处R18包装全计划精确，114接线检查通过；原T112全部137限深触发输入首选无一改变，旧/新批均值差不能直接归因限深。[最新接线](../../review/vip-route-2026-09-30/evidence/t167-mixed-testroom-current-r18-wiring-1/REPORT.md)、[持续实战](../../review/vip-route-2026-09-30/evidence/t165-live-watchdog-1/README.md)。

2026-10-04更新：新testroom_v6／free_v4已完成T161自由赛和T163四席M10/R8快速测试房的真实工程验收；对局摸切、429、计算故障/重启均0，原截止、限深1、公式和稳定默认版本不变。T163一只过评分超期及两只过零规划例外保留，严格零降级false；T161缓发虽开启但因快照时间依据不足全跳过，不能授缓发改善信用。T148强度false仍保留，正式/测试赛事发布门未授。详情见[验收报告](../../review/vip-route-2026-09-30/evidence/t163-received-fix-fast-four-seat-testroom-1/REPORT.md)。

省略 `strategy` 时，代码默认仍为 `weighted_heuristic`（V0），不会自动选择最新策略。2026-09-29 的连续自由赛运行清单使用显式配置的 `r18_integrated_positive_v2`；模板、代码默认值和实际运行身份是三件事，后者须从相应运行清单核对。当前进化与接线结论从[研究证据索引](../research/INDEX.md)进入。

| 枚举值 | 支持的运行模式 | 说明 |
| --- | --- | --- |
| `weighted_heuristic` | 全部 | 冻结V0，省略配置时的默认值 |
| `weighted_heuristic_v1` | 全部 | 冻结V1，历史对照 |
| `weighted_heuristic_v2` | 全部 | 稳定基线；Tier-A 的对照基准 |
| `r18_integrated_positive_v1` | 历史冻结范围为 `test_room` / `test_tournament` / `auto_match`；**当前主线规则下拒绝装配** | 旧包绑定原规则源码，没有制作当前规则的新包；历史身份保留，不是默认策略 |
| `r18_integrated_positive_v2` | 历史四种模式；当前main规则源码绑定不匹配，拒绝重新装配 | 原评分源码和旧包保留，未绕过旧摘要；需要另行验证新绑定，既有旧运行身份不受重写 |
| `vip_s02_bounded_d1_testroom_v9` | 仅 `test_room`，绑定新包ID、SSE | T191已整合主线的测试房候选；不覆盖旧v8清单，不授尚未执行的新联网门 |
| `vip_s02_bounded_d1_free_v7` | 仅实验 `auto_match`，绑定新包ID、SSE | 已自然迁移并自动续打；与赛事候选共享182来源/原公式 |
| `vip_s02_bounded_d1_test_tournament_v1` | 仅 `test_tournament`，测试类别Token、绑定新包ID、SSE | 原S02测试赛事运行候选；当前官方已无测试锦标赛安排，未执行记录保留 |
| `vip_s02_bounded_d1_official_tournament_v1` | 仅 `official_tournament`，正式类别Token、绑定新包ID、SSE | 原S02正式赛事运行候选；实际规则/日期与官方发布门未授 |
| `vip_s02_bounded_d1_testroom_v8` | 仅 `test_room`，显式绑定新包ID、SSE | T179实际编译接线；十个专属预热槽；四席小房656完整评分，测试房不续 |
| `vip_s02_bounded_d1_free_v6` | 历史实验身份；当前源码绑定不匹配，拒绝恢复 | T179已自然交接至T191/free_v7，旧owner禁止恢复；原件保留 |
| `vip_s02_bounded_d1_testroom_v7` | 历史实验身份；当前接线不再装配 | T167混合接线源码的新冻结；原S02/限深1不变，旧v6完整十桌零摸切/对局429/故障，三个只过边界保留；新包未完赛不授新实测 |
| `vip_s02_bounded_d1_free_v5` | 历史实验身份；已自然换版，不重开 | T167新冻结；原公式/限深/截止不变，旧v4十桌−141仅观察，工程全评分通过；新包不授强度或正式赛事 |
| `r18_v2_current_rules_testroom_20261004` | 历史 `test_room` 对照；旧包与新源码摘要不匹配，拒装 | 原R18公式/默认2048分析限额，绑定当前规则与全部运行源码；供两席T110两席R18对照，不改变旧正式包、默认或发布权限 |
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
