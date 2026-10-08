# T4 机会量具 v2 独立返修复核

2026-10-01。**原 F1—F3 的对应实现和有界复算未重现原缺口；输入拒绝、物理起庄和真实零根来源核验通过本轮独立检查。非零根经完整 `evaluate` 的实际成功路径仍未覆盖，正式机会入口继续未验收。**本轮正式母样本、机会样本、候选评分和真实候选续打均为 0，没有自然效果、强度、晋升或发布结论。

审查对象为[新增 v2 工具](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py)，源码 SHA256 `c6cd151f4a95d45a29d9b6e86aeb6c75b31fd3ef30da0ac2b49ce54b7beb0a31`，审查前后相同。依据为[原独立审查 F1—F3](./T4-OPPORTUNITY-TOOL-INDEPENDENT-REVIEW.md)、[原独立脚本](./evidence/t4-conditional-payment-batch-1/opportunity-tool-independent-checks.py)、[作者返修说明](./T4-OPPORTUNITY-VALIDATION-REPAIR-1.md)、[作者回归原件](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/guard-check-05.json)和当前 v2 源码。旧工具、旧审查、旧机械04、候选、生产核心及费用原件保持不变。

## 原发现的返修判定

**v2 将来源核验放在候选续打之前，同时保留独立调用方的信任责任。**扫描封条（`ScanSeal`，覆盖完整扫描原件且由外部期望 SHA256 绑定的文件）不能仅靠来件内部的摘要或声明证明可信。

| 原发现 | 静态实现与独立实测 | 本轮判定及边界 |
| --- | --- | --- |
| F1：删根、伪空、母体不完整及焦点身份被改 | `evaluate` 显式接收外部封条路径与期望摘要；`verify_selection_envelope` 核全部文件、快照、冻结登记、完整母桌、实际配置、全部根合并、完整身份、Hash 与费用；`verify_table_trace` 重建完整合法轨迹、全部焦点行动前窗口和每单局首槽位根。删已选根、伪空、改焦点、缺母桌、源漂移及扫描不完整均拒绝；内部自洽伪根最终被真实轨迹拒绝。 | 原来只相信根来件的缺口已修复。只独立重放一个已封存人工单局；没有完整八单局 H/M 四映射的非零正向消费证据。 |
| F2：映射误作物理庄 | `match_spec` 直接传 `plan.initial_dealer_physical`。四映射分别实际公开初始化，`MatchSpec.initial_dealer` 与观察中的庄家均为 0，焦点座位分别为 0／1／2／3。 | 起庄错误已修复；四次检查都是初始帧，不冒充四张完整桌。 |
| F3：预算缺键及非有限数晚拒绝 | `read_plan` 核全部且仅有七项必需预算，正值、有限性和类型；实例／步数必须为整数，完整来源验证预算也须覆盖母体。独立运行 64 种错误预算／阈值来件，全部启动前拒绝。 | 原缺键与非有限数问题已修复。没有用错误来件创建输出或启动世界。 |

精确入口定位：[外部摘要及完整封存核验](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:495)、[完整合法来源重建](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:607)、[物理起庄](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:430)、[预算早拒绝](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:219)。

完整来源验证不重复评分 R18。它证明给定已签收生产者原件的合法轨迹、到达观察和首槽位；R18 来源身份仍依赖打开候选结局之前的独立外部签收。`sealed_before_candidate_continuation=true` 与 `source_stable=true` 只是生产者声明，不能取代签收时点和完整原件。来源验证单独占实例及墙钟预算，没有隐藏为免费检查。

## 独立有限复算

**77 个独立拒绝案例全部按预期拒绝，真实零根通过完整重建，伪根没有取得来源信用。**[新复算脚本](./evidence/t4-conditional-payment-batch-1/opportunity-v2-independent-checks.py)与[独立 JSON](./evidence/t4-conditional-payment-batch-1/opportunity-v2-independent-review.json)是本轮新增材料，不覆盖作者回归或旧审查。

| 独立检查组 | 实测结果 |
| --- | --- |
| 七预算逐项缺键、正／负 Infinity、NaN、布尔值、0、负数、字符串；四实例／步数字段小数；预算多键；最小分差非有限或布尔值 | 64／64 拒绝。通过实际 `evaluate` 检查的 56 个预算错误来件均未创建输出目录；其余在 `read_plan` 拒绝。 |
| 外部期望 SHA 缺失、格式错误、错误值，内部重新封存后仍沿用原外部锚 | 拒绝。期望摘要不从待验封条 JSON 内取值；内部自报一致不能替代固定外部锚。 |
| 删已选根、选择账伪空、改焦点座位、缺母桌、源漂移、扫描不完整 | 攻击来件在临时目录重新封存后仍被拒绝。 |
| 实际完整零根来源 | 机械05固定 seed=0 原件通过封存／母表核验；公开重建 107 步、44 个焦点行动前窗口、1 个完整人工单局，首槽位及选根均为 0。单调墙钟观察约 2.871 秒。 |
| 内部母表、根表、选择账、费用与封条全部自洽，但伪造两个首槽位根 | 静态包络接受其内部一致性；真实完整轨迹重建拒绝，原因为“完整终点／全部行动前窗口／第一槽位根被删改”。伪根不是有效机会根。 |
| 机械配置／封条交正式入口 | `read_plan` 拒绝机械状态；默认来源核验拒绝 `source_kind=mechanical_fixture`。测试许可未自动扩展到正式入口。 |

测试脚本预置机械05期望摘要 `932b6efba8a01f63d6a05bd6291d6e4683028d357391971a4df80713232032a7`，与已封存机械摘要 receipt 一致；不在验证调用中从封条内部自取。这里只授机械只读核验范围，不冒充正式候选结局打开之前根任务的签收信用。构造攻击另行使用测试生成的锚，目的仅是检验内部绑定和真实重建两层的差别。

本轮实际额外完整轨迹重放 2 次：一份真实零根来源、一份伪根攻击。另有 5 次公开初始帧构造，其中四次核起庄，一次构造攻击观察；这些未完成桌。没有候选评分或真实候选续打。完整世界（`WorldState`，模拟器拥有的他家暗牌和未来牌墙）只通过公开 `start/frame/advance` 交互，未查看其私有字段。正式母样本未打开，也未读取任何自然效果。

## 失败分母、费用与零根

**失败没有缩小计划分母、退款或生成完整均值。**费用控制流复算明确使用伪根及内存桩（`SyntheticRunPair`，只触发人为异常、不启动候选世界的检查函数）。为检查机械来件的消费者控制流，临时替换 `read_plan`、机械来源许可、轨迹验证、续打及快照写入；因此这些通过不能称为真实非零完整入口成功。

来源验证异常时，两个计划配对都保留为未知，观察分母仍为 2，候选不启动，整体 `complete=false`、均值 `None`。验证费用先预留 1，失败结束仍记 1。续打顶层异常时，两对均保留，预留两臂 2，失败结束仍记 2，均值仍为空。费用文件为阶段事件，预留和结束不能相加成双倍收费。

[汇总器](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation_v2.py:861)现在要求 `planned>0` 才可能完整；独立调用 `summarize_pairs([],0,scan_complete=True,source_stable=True)` 得到 `complete=false`、均值为空、`no_selected_opportunities=true`。这是合法零命中的表示，不能拿它抵充非零完整评估。

## 有效非零完整入口的剩余门

**机械05及新固定前缀配对仍不能证明有效非零根经完整 `evaluate` 可执行。**这是目前的覆盖缺口，没有据此报告新的源代码 P1 缺陷。

作者[补充原件](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-05/fixed-public-prefix-pair.json)复用旧04已冻结人工首根与原配置，直接调用 v2 `run_pair`，134 步合法前缀后 A/C 各完成 1 单局，C 为 1／1 自评分。本轮只读核对该原件与摘要，没有再运行或把其分差算为效果。原件 SHA `4cc884dfe0cd840cf53b09b79f1d039edd2243eb96e687010bd323b845f5b4b2`。

当前可复现边界是：

1. 机械05完整真实来源确有 0 根，来源核验可通过，零根汇总必须不完整且无均值。
2. 两个人工伪根的内部摘要可自洽，真实全部首槽位重建必拒绝；它们只能用于攻击和费用桩。
3. 旧04首根的直接 `run_pair` 可完成，但绕过了正式 `read_plan`、完整母体封存、全部来源重建及 `evaluate` 消费链。
4. 把机械05当前配置直接交 `read_plan` 会以“正式机会测量必须先有根审核后的完整冻结登记”拒绝；即使单独请求默认封条核验，也会以机械 `source_kind` 拒绝。

后续需要独立冻结一个明确仅作机械测试的完整八单局 H/M 四映射母体，扫描出真实非零首槽位，先签收外部封条与预算，再从未替换的 `evaluate` 入口完成全部来源核验和 A/C 自续打。零命中、预算超限或失败均保留原件，不按结局换种子、删根或缩水分母。本轮没有执行这个后续计划，也没有授予正式入口批准。

## 冻结与复现

**新旧原件及 v2 源码的审查前后摘要全部相同。**完整列表保存于独立 JSON，包括旧工具、旧审查脚本、作者 v2／回归／guard05、机械05原件与全部来源封存文件。本轮只新增本文、新复算脚本和独立 JSON，没有 Git、模型、网络、数据库、官方流程或生产写入。

| 新增项 | SHA256 |
| --- | --- |
| 独立复算脚本 | `15b9efe0ce5ed6789354f1a5e64303fad05d452063f8ed149de9695b1b98c6b9` |
| 独立 JSON | `fbcb6919d8ad7f4b881491d60cf9291acdfbd5bebbcc7fec9e614aa42255a1e6` |

从仓库根目录运行以下命令，输出必须是不存在的新文件；会再增加 2 次人工完整轨迹重放和 5 次初始帧构造，候选调用仍为 0。使用仓库 `.venv/bin/python`，不经 console `pytest`。

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-v2-independent-checks.py \
  --out /private/tmp/opportunity-v2-independent-recomputed.json
```

结果应为 77 个拒绝案例全部拒绝、错误预算输出目录数 0、原件摘要稳定；真实零根轨迹为 107 步／44 窗。单调耗时可随机器及缓存变化。本轮结论仅关闭原 F1—F3 已识别缺口的对应返修检查，并继续保留有效非零完整入口与正式机会门。
