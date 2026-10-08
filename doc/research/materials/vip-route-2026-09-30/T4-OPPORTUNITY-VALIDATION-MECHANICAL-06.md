# T4 机会量具机械06：真实非零完整消费者入口

日期：2026-10-01。**机械06已通过真实非零完整`evaluate`路径：完整扫描8桌、完整重建8桌来源、10个真首槽位根的20个A/C续打臂均严格完整。**候选C在1925／1925个本人窗口实际自行评分。这里的A为注册R18对照，C为Sol v2 i1候选。该批明确为`mechanical_only`，正式机会母样本与正式机会样本仍为0，不授算法效果、自然强度、官方实网时限或发布信用；正式机会登记仍待独立交叉审查后另冻。

本批补齐 [v2修订报告](./T4-OPPORTUNITY-VALIDATION-REPAIR-1.md)中未覆盖的真实非零消费者路径。v2冻结源码始终为 `c6cd151f4a95d45a29d9b6e86aeb6c75b31fd3ef30da0ac2b49ce54b7beb0a31`，没有修改生产或受控合同，也没有修改旧机械01—05或其独立审查原件。所有新机械材料位于 [mechanical-fixture-06](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06)。

## 扫描前冻结与C前独立签收

**样本、Hash和费用在扫描前冻结，外部封条在C前由根任务独立签收。**本批只用固定机械母种子`2030100601`；H/M各四映射，8桌每桌完整8单局，物理庄均0、初分均0。Hash固定1／4及固定salt，原世界1、额外相容世界0。没有因命中数或结局重新设种子／Hash，没有删根缩分母。

| 冻结材料 | 作用与SHA256 |
| --- | --- |
| [mechanical-full-entry-06-plan.json](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-full-entry-06-plan.json) | 外层明确机械用途及失败保留；`c77c8efb942fcf0b0dbcab8e6cc7d877de93bce10b39e9991827c6ff58750a4a` |
| [执行草案](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-entry-06-execution-proposal.json) | 扫描前提案；`05a66e343f342e10582fdf89106bbceab1cfb2256aaddad5c69b6e7e54257a01`，原件不改 |
| [冻结执行原件](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-entry-06-frozen-execution.json) | 仅将草案status升为v2既有执行状态，机械`claim_scope`不变；`954d423bcdd1814078de97f0806ae63f3cab8f3f84385ace7d22b4fdca3f7951` |
| [预算冻结回执](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-entry-06-budget-freeze-receipt.json) | 根任务扫描前批准固定范围与预算；`63107a8f08484b2119c2aa7bfddae73d6688549fad9d265b4d897c80f3cc744a` |
| [扫描封条](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06/scan/scan-seal.json) | 完整扫描原件集合；`6925a42ba2640afb7444adfe66ff3def26535f55f1eb4b58dc55cff51784f6c6` |
| [根独立签收回执](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06/scan-seal-acceptance.json) | C前独立核验登记、完整来件与快照，以literal期望SHA接受封条；`f06fb4d2afc7db6a4eb37ead11d08634a61118c0d3fc1779568703d34c53ad6b` |

签收回执保存在`scan`封存目录之外。`evaluate`调用显式传入根已接受的期望SHA `6925…f6c6`，没有从被检查JSON取得期望值；签收前没有`evaluation`目录或C续打。v2先公开重建每桌全部合法动作、全部焦点行动前窗口与每单局首槽位根，8桌全通过后才预留第一对续打。

## 完整来源、真实根和自身续打

**完整来源与两臂终点均通过，早期弃牌与近端支付路径实际进入消费者。**扫描完成64单局，全部42个首槽位根均在选择账中，Hash纳入10个唯一根；未命中及未知事实原件保留。来源重建再次完整覆盖8桌并逐字段重生全部行动前记录，无伪造根或验证桩。

| 真实选根标签 | 根数与边界 |
| --- | --- |
| 早期非胡、可弃且规范当前白库存≥2 | 7；具备早期弃牌／自然面子路线入口 |
| 实际弃牌根直接普通摸牌支付≥4番证据 | 2；与早期标签重叠，不增加样本数 |
| 当前可胡<4番且可继续 | 3 |
| 远距离结构控制 | 2；只是工程分层，不排除 |
| 未知事实 | 完整源账含2个标签根、其中实际弃牌支付未知控制1个；此次Hash没有选中 |
| 墙余≤24控制 | 本批没有实际命中；机械05纯函数已有保留检查，不能称该负控真实正向覆盖 |

7个非胡根和3个当前可胡根合计10个唯一根；多标签不重复抽样。两臂各从同一原始世界的合法前缀重建，分别持续选择本人所有窗口到原完整桌终点。20／20臂达到8单局终态，候选本人1925／1925窗口均完整自行评分，双方`timeouts/illegal_choices/fallbacks/auto_actions/audit_missing`汇总全部为0。没有强制一次C动作后返回R18，没有额外相容世界。

[全结局摘要](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06/evaluation/summary.json)保留10／10计划配对、3条正尾和7条负尾。焦点当前单局的两臂结局均为本人普通胡；当前单局账与完整余桌账分开。固定机械账中的余桌差保留原值，不据此推断候选增强，也不能把R18到达条件账当自然完整桌均分。

## 预算与最终核验

**预留与最终计费一致、无失败退款，所有墙钟阶段低于冻结上限。**费用文件是阶段事件，预留和结束不能简单相加为双倍收费。最终实用36实例：扫描8、来源重建8、两臂续打20。

| 阶段 | 冻结实例上限 | 实际预留／最终计费 | 墙钟实用／上限（秒） |
| --- | --- | --- | --- |
| 母体扫描 | 8 | 8／8 | 224.351／900 |
| 完整来源验证 | 8 | 8／8 | 219.588／900 |
| A/C完整余桌续打 | 64 | 20／20 | 415.945／1800 |

[机械用途最终摘要](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06/mechanical-only-summary.json)SHA256为 `99e007fe8023c632661acfafa462e278ec3a25517d523af732882d433f4d1906`；[消费者原始摘要](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06/evaluation/summary.json)为 `2b5c0205697f0a102bdc05bf22ae358e3eef36e0a38f5e438a8e7a2efca1761c`；[全选择账](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06/scan/selection.json)为 `1defa4a8c3a8ea8973b9744a019e0f26b6a840444ce0a3440f26adcace023cf9`。最终再次核验原扫描封条与全部文件集合不变，来源绑定稳定；续打目录75项源码快照与当前字节逐项相符。

本结论仅为作者机械验证结果。独立交叉审查需另外确认F1—F3拒绝行为及本批真实正向来件，随后根任务才能另冻正式机会母样本／Hash／预算。当前没有网络、模型API、官方流程、DB或Git写入，没有读取新自然确认种子的效果，没有把本机械母种子计入正式能力分母。
