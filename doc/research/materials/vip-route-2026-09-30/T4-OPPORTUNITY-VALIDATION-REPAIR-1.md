# T4 机会自续打量具 v2 修订与机械证据

日期：2026-10-01。**v2 已新增来源封存、完整母体核验、物理起庄修复和严格预算读取；正式机会测量仍未启动，也不自行宣布正式入口通过。**正式母样本与机会样本均为 0。[新草案04](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/draft-preregistration-04.json)的母种子、Hash份额、正式实例／墙钟预算仍为空，不能交给正式入口执行。生产核心、受控合同、候选原件、旧工具、旧机械04和旧独立审查原件均保留。两臂中的A为注册R18对照，C为当前Sol v2 i1候选。

本次依据 [独立审查F1—F3](./T4-OPPORTUNITY-TOOL-INDEPENDENT-REVIEW.md)与 [原复现脚本](./evidence/t4-conditional-payment-batch-1/opportunity-tool-independent-checks.py)修复。原独立机器报告 SHA256 为 `97363c43554f990d12ae39383f4340c493bc8251b572dcd04db5e7834c2ff2a9`。本报告只替代量具入口的工程状态，不产生候选改进、自然均分或发布结论。

## 修订结论与信任边界

**完整扫描原件必须先由独立调用方签收，再打开候选续打结局。**新增 [v2工具](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py) SHA256 为 `c6cd151f4a95d45a29d9b6e86aeb6c75b31fd3ef30da0ac2b49ce54b7beb0a31`。旧工具 SHA256 仍为 `936d89001ad84f3f29bfc790f88d4453a8168a708638458d80c0fbee5952d6f2`，旧机械04摘要仍为 `d27976e16fa1cc0a38a0c81e467b818e380e4d31b3d11ace9fb1987ca02c8111`。

| 发现 | v2行为与拒绝依据 |
| --- | --- |
| F1：删根、伪空、缺母体与改焦点身份 | `evaluate`必须显式接收`scan_seal_path`及`expected_scan_seal_sha256`。期望SHA只能来自独立调用方在C结局打开前冻结的记录；入口不从来件JSON自取。先核封条字节，再核完整文件集合、生产者绑定、75项源码快照、冻结登记、计划母种子×H/M×四映射、全部严格完整桌状态、实际配置、全部根合并、全字段身份、实际Hash命中和预留／结算费用。之后经公开模拟器重建每桌全部合法轨迹、全部焦点行动前窗口及每单局首槽位根，逐字段相等后才允许C。 |
| F2：策略映射误作物理庄 | [match_spec](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:431)直接把冻结的`initial_dealer_physical=0`传给模拟器；映射只分配策略身份。来源核验同时核实际完整配置。四映射的真实初始公开帧均观察物理庄0。 |
| F3：预算缺键与非有限数 | [read_plan](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:181)在创建输出或启动世界之前核固定全部必需预算键、正值、有限性和类型；实例与步数只接受整数。新增完整来源验证实例及墙钟预算，实例必须覆盖全母体。续打预算至少能覆盖一个完整两臂根；打开结果前还核全部选根两臂世界预算。最小有意义分差也必须有限。 |

扫描封条（`ScanSeal`，覆盖本次扫描全部原件且由外部期望SHA绑定的文件）不具有自我证明能力。`sealed_before_candidate_continuation=true`只记录生产者声明，独立调用方的签收时点才授予该来源信用。根任务需在运行`evaluate`前另行保留封条SHA及签收记录；评估输出复制外部期望SHA，但不会自动生成外部授权。在这一可信来源下，可不重复评分R18，来源验证仍需完整重建所有合法轨迹和行动前首槽位。

验证实例与续打实例分账：完整来源验证一桌预留1实例，结束事件仍记1，失败不退款；两臂续打预留2，顶层异常结束仍记2。费用文件是阶段事件，预留与结束不能相加成重复收费。来源核验失败时，全体已计划根／世界仍输出未知结局、总体估计为空，C不启动；后来未开始的母桌和配对也保留。真实零命中需核完整母体与真实轨迹，仍不输出`complete=true`或效果均值。

## 机械05与定向回归

**机械材料证明局部接线与拒绝行为；没有覆盖非零正式母体完整`evaluate`成功路径。**[机械05摘要](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-05/summary.json)固定人工seed=0，不按未来结局挑样。初始A/C各完成1单局；C为51／51本人窗口实际评分，运行计数全部为0。完整来源复核重建107步、44个焦点行动前窗口，真实首槽位根数为0，再完成1个机械单局。四策略映射实际初始帧的物理庄均为0。

[新05固定前缀补充](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-05/supplementary-summary.json)只复用旧04已封存人工A原件的首根及原人工配置，未选新母样本：134步公开合法前缀重建后，v2直接`run_pair`使A/C各完成1单局，C为1／1实际本人评分。原件在 [fixed-public-prefix-pair.json](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-05/fixed-public-prefix-pair.json)。这证明同一原始世界的严格自续打仍可行，不等于完整消费者入口非零成功；本次未做八单局H/M四映射母体，也未做额外相容世界。

[定向回归脚本](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/opportunity_validation_v2_regressions.py)及 [guard-check-05原件](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/guard-check-05.json)共58项检查通过。多数攻击先重新封存内部自洽来件，使拒绝原因不能仅归于未重写内部SHA。两个人工根只用于攻击静态门，不声称是真实机会根；完整公开轨迹核验能拒绝这组自造首槽位。控制流收费检查将`read_plan`、验证或`run_pair`明确替换为内存桩，不作为正式成功验证。回归额外完整重放1个固定人工单局、初始构造1个公开人工帧，候选评分与真实候选续打调用均为0。

| 有意义检查组 | 结果 |
| --- | --- |
| 选择账删已选根、伪空、缺全母桌 | 内部重新封存后仍拒绝；不能改成完整估计 |
| 改焦点座位／未知池／反映射、修改全表根焦点、修改母体映射／物理起庄 | 拒绝；不能把改写元数据送入候选续打 |
| 全表根与全选择账同时改为错误Hash命中 | 重算冻结Hash后拒绝 |
| 扫描不完整、`source_stable=false`或缺字段、删费用事件 | 拒绝；源当前恢复也不能弥补扫描声明失败 |
| 封条被替换或原件字节改变而外部期望SHA不变 | 拒绝；内部JSON不能代替外部锚 |
| 全部内部母体／摘要一致但伪造行动前首槽位根 | 真实完整合法轨迹重建拒绝 |
| 全部7项预算分别缺键、Infinity、NaN、布尔值、0；验证预算不足、两臂预算不足、最小分差非有限 | `read_plan`启动前拒绝 |
| 来源验证顶层异常 | 所有计划配对保留未知、均值为空；验证预留1与失败结束1，无C调用 |
| 续打顶层异常 | 所有计划配对保留；预留2与失败结束2，无退款 |
| 人工`+24、−8` | 两根均值8；保持冻结分母删负根后均值为空；真实零根不算完整效果验证 |

13张暗手另列摸白与14张已含摸白两个原始表示，在同源规则规范库存中均为2白、相同早期／远距离标签、普通型距离3／七对距离5。当前白数仍取实际规范库存加回实际白弃，不取弃后用途白数`retained_whites`。这些谓词及层是工程定义，不称官方大牌资格。

## 覆盖范围与下一步

**下一步是独立复核关闭F1—F3，再冻结新母样本及预算；当前没有可执行的正式机会登记。**[artifact-check-05](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/artifact-check-05.json)逐核旧04／新05各75项快照与当前字节一致，记录`nonzero_full_evaluate_actual_run_covered=false`及`formal_entry_approval_claim=false`。后续需要在冻结母体的非零真实根上走完整消费者入口，不能把直接前缀`run_pair`或内存桩成功迁移为该入口的证据。

选择能力沿用原行动前定义：未可胡、可弃且当前白库存≥2覆盖早期弃牌／自然面子路线；距离0／1／2／>2／未知只分层、不排除。实际弃牌根直接普通摸牌支付≥4番另成近端层；当前可胡<4番且可继续另成等待层；低墙和未知事实保留。同根多标签不重复抽样，全焦点窗口含未命中分母。候选只收合法`PlayerObservation`规则映射，不读取他家手牌、未来牌墙、标签或选根种子。

评估保留焦点当前单局与完整余桌两个账，结局覆盖本人普通胡、4—7番、≥8番、他家先胡、流局与未知未完成，记录普通出口损失、高番置换、放弃当前Hu及正负尾。默认只用同一原始世界A/C完整自续打；额外相容重采样必须显式开关、预算并声明后验相容假设。R18到达条件均差与自然完整桌均分独立，不能把父代到达分布改称自然均分。

| 新原件 | SHA256 |
| --- | --- |
| v2工具 | `c6cd151f4a95d45a29d9b6e86aeb6c75b31fd3ef30da0ac2b49ce54b7beb0a31` |
| 定向回归脚本 | `14f8d59dddd64db7ad3bf0d6371f391425bc72b4de183ac1350750de2fa911cc` |
| 草案04 | `5f5502005841af190178801d5630eb068de6e517c4542826b31ccda61c0d7bc4` |
| 机械05摘要 | `2848022b4ab7fbd23bbde165ce700c0c3c1b920112c89f4d8ce28f6a635167e1` |
| 机械05补充摘要 | `e543f0d31108820f8a91963d52ce601a24cebb7f840272a099c037419766f23e` |
| 新05固定前缀配对 | `4cc884dfe0cd840cf53b09b79f1d039edd2243eb96e687010bd323b845f5b4b2` |
| guard-check-05 | `d63afe407082e456da462173be450046676a8af76a8d8962e69b3998b788a3ca` |

所有新写入仅在本批研究脚本及新原件／本修订报告。没有网络、模型API、官方流程、DB或Git写入，没有读取新自然确认种子的效果，也没有新增正式机会母种子或费用预算。
