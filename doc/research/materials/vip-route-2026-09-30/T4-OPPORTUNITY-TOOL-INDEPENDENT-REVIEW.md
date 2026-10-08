# T4 机会自续打量具独立审查

日期：2026-10-01。**冻结工具暂不通过正式机会测量入口：发现两类 P1 阻塞与一项 P2 输入完整性问题。**本次未打开正式母样本、未运行真实牌山或候选评分，正式样本数为 0。当前没有由本量具证明的稳定增强候选。

审查对象为 [最终工具](./evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation.py)，SHA256 为 `936d89001ad84f3f29bfc790f88d4453a8168a708638458d80c0fbee5952d6f2`；审查前后相同。[作者方案](./T4-OPPORTUNITY-VALIDATION-PLAN.md)与 [VIP 评测合同](./EVALUATION-CONTRACT.md)共同界定范围。本结论不自动覆盖随后另名修订的工具或新机械例。

## 阻塞性发现

**F1／P1：续打入口没有核验完整选择账，删根和篡改身份仍能进入配对。**定位为 [工具第640行](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation.py:640)、第644—648行、第665行与第693行。入口只核 `schema`、登记文件摘要和 `outcome_labels_used_for_selection=false`，随后从来件 `roots` 直接决定计划分母；表内归属检查只比较 `root_id`。它没有核完整母种子 × H/M × 四映射的桌清单、每桌完成状态、扫描源稳定性、全根合并、实际 Hash 筛选或根的全字段绑定。

有限合成检查使用真实 `read_plan` 和 `evaluate` 输入控制代码，续打函数替换为内存桩（`SyntheticRunPair`，只返回人为算术结果的函数）；源码快照复制也替换为空操作。没有创建完整世界（`WorldState`，模拟器持有的暗牌和未来牌墙），没有候选评分。各来件均使用实际冻结登记的字节摘要，当前代码绑定核验通过。人工分差只说明分母漏洞：

| 合成来件 | 入口结果 | 实际含义 |
| --- | --- | --- |
| 两根人工差 `+24、−8`，缺全部母体／桌清单，且 `selection.source_stable=false` | `complete=true`，计划2对，人工均差8 | 只相信 `scan_complete=true`，缺扫描完整证据仍通过 |
| 以上删掉负根，保留声明 `selected_root_count=2` | `complete=true`，计划1对，人工均差24 | 表内仍有两根，选择账删根未拒绝，分母随来件缩水 |
| 以上改为 `roots=[]` | `complete=true`，计划0对、均差为空 | 没有证明合法零命中；伪空无法区别于真实零选择 |
| 保持同 `root_id`，把焦点座位改3、池改 `UNREGISTERED`、映射改 `[3,2,1,0]` | 元数据原样送入续打桩 | 归属只看标识，未保证本座策略与物理计分座位相同 |

这里的“源漂移通过”特指扫描来件中的 `source_stable=false` 被忽略；当前源文件与登记不同仍会在 `read_plan` 被拒绝。若扫描期间曾漂移、后来恢复到原字节，当前源核验不能替代扫描完整性核验。正常由冻结代码生成的扫描采用行动前谓词；问题在于消费者不能证明读入的选择账仍是该完整扫描原件。

修复建议：在打开续打结局前，由独立调用方冻结并提供扫描封条（`ScanSeal`，记录完整扫描原件摘要且独立于来件的绑定）。先核其期望摘要，再核全部母体桌、完整合法动作前缀、桌配置／费用／完成状态和源稳定性。通过公开 `start/frame/advance` 重建所有焦点行动前观察，重生所有每单局第一槽位根，重算 Hash 筛选，逐字段核根／母种子／池／映射／焦点座位／窗口／观察绑定。真实零命中也必须从完整扫描导出。额外验证回放要有独立冻结的实例与墙钟预算，不能隐去费用。

**F2／P1：扫描实际物理庄家违背登记。**定位为 [工具第444行](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation.py:444)。草案第151行、验证第190行以及作者报告均要求 `initial_dealer_physical=0`，但 `MatchSpec` 使用 `permutation.index(0)`；[模拟器第76行](/Users/liyang/hangma-bot/src/hangma_bot/simulation/engine.py:76)直接将该字段作为物理庄家。

| 策略映射 | 焦点物理座位 `permutation[0]` | 登记物理庄家 | 实际扫描物理庄家 |
| --- | --- | --- | --- |
| `[0,1,2,3]` | 0 | 0 | 0 |
| `[1,2,3,0]` | 1 | 0 | 3 |
| `[2,3,0,1]` | 2 | 0 | 2 |
| `[3,0,1,2]` | 3 | 0 | 1 |

这改变三映射的规则场景和到达分布。机械例04只有第一映射，因此未暴露该错误。修复时应直接把冻结的物理庄家传给 `MatchSpec`；映射只用于把逻辑策略身份放到实际座位，并对四映射起庄作纯算术断言。

## 其他输入问题

**F3／P2：必需墙钟预算缺字段仍通过登记读取，非有限数也未拒绝。**定位为 [工具第210行](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/vip_opportunity_validation.py:210)。验证遍历来件已有 `limits` 字段，只另外强制访问三个整数字段。移除 `scan_wall_seconds` 与 `evaluation_wall_seconds` 后，`read_plan` 仍返回成功；二者为 `Infinity` 也返回成功。后续会因缺字段或严格 JSON 写入失败，未形成可用效果估计，但拒绝发生在新目录／证据初始化之后，不能称为完整登记门。

修复建议：先核固定的全部必需预算键，再核类型、正数与有限性；实例和步数只接受正整数。最小有意义分差也须为有限数。应在创建输出目录与任何实例尝试之前完成这些校验。

## 通过与受限项

**核心行动前权限和自续打路径没有发现新的越权或回退实现；它们不能抵消上述入口阻塞。**以下判断结合静态源码与机械例04原件，只对已冻结范围成立。

| 关注点 | 独立复核结果及边界 |
| --- | --- |
| 行动前选择权限 | `select_facts` 只读玩家观察（`PlayerObservation`，本座当时依法可见的事实）、同次规则根和公开图；`SelectPolicy` 装在 R18 焦点策略，候选评分和后续结局不参与谓词。根标签与种子只入审计，不传候选评分映射。 |
| 当前白库存 | 从所有合法弃牌根规范库存加回实际白弃，再与公开图交叉核对，未用用途白数 `retained_whites` 代替实体库存。作者13张暗牌＋单列摸白与14张已含摸白两表示都记录2白、相同标签、普通型距离3／七对距离5、无事实缺口。此处是作者冻结原件复核，没有独立重跑规则。 |
| 远／未知与多标签 | 纯函数检查确认 `D>2` 和 `unknown` 都保留；墙余低与未知控制保留。`SelectPolicy` 每单局第一槽位和固定根标识只作一次 Hash；正式消费者完整性仍受F1阻塞。 |
| 合法前缀与权限 | `rebuild` 经公开 `start/frame/advance` 核 revision、窗口、合法动作、本座观察与完整帧摘要；没有读取完整世界私有字段。帧级其他响应者摘要仅用于重建核对，没有传给本座候选。 |
| A/C分别自身续打 | 两臂新建独立运行时，从同一前缀续到引擎完整桌终态；候选每个本人窗口重新完整评分。`strict_policy=True` 拒绝异常、空计划、非法动作和超时，候选评分包装另核全部合法根的 `SCORED`。不存在强制一次C动作后回R18的实现。 |
| 当前单局／余桌与计分 | 结算分类覆盖普通胡、4—7番、≥8番、他家先胡、流局与未完成未知；余桌从根时积分扣除，逐物理座位取分。纯算术在物理座位3得到当前／余桌差−32；严格失败余桌差为空、缺席配对均差为空、未完成不会合成流局。输入座位身份受F1阻塞，物理起庄受F2阻塞。 |
| 固定费用与异常 | 正式计划实例先落盘，实际续打前预留两臂费用。合成续打异常保留预留 `charged_continuation_instances=2`，失败结束事件仍为2，总估计为空；没有退款。`charges.jsonl` 是阶段事件，预留与结束不能简单相加成两次费用。运行前缺席仍留在计划分母。 |
| 冻结与草案拒绝 | 当前 `binding_stable=true`；工具摘要前后相同。机械04快照索引75项的快照字节和当前原件均匹配；实际草案与自然确认禁用种子均在 `read_plan` 被拒绝。源稳定性的扫描来件核验仍受F1阻塞。 |

机械例04原件复核：初始帧A/C各完成1单局；C有64个焦点窗口，64／64实际自身评分；合法前缀配对又各完成1单局，C为1／1自身评分；两组严格完成且运行计数全零。四个完成实例都是人工机械单局，正式母样本与机会样本均为0。摘要 SHA256 仍为 `d27976e16fa1cc0a38a0c81e467b818e380e4d31b3d11ace9fb1987ca02c8111`。没有重新运行母体扫描、八单局H/M四映射、额外相容世界或真实异常恢复，不对这些未覆盖项授予通过。

## 复现与下一门

**保留旧工具与机械04，修复应新增工具身份和机械材料，正式机会登记继续关闭。**修订需首先拒绝删根、伪空、缺母体、扫描不完整／源漂移、错误Hash与篡改座位；还需断言四映射物理庄家一致、预算缺键及非有限数在启动前拒绝。外部扫描封条应由根任务在打开续打结局前独立签收；在该可信来源下，不必额外重跑全部R18评分来重复证明已审核的生产者装配，但所有合法前缀与行动前首槽位必须核全。

可复现入口为 [独立合成检查脚本](./evidence/t4-conditional-payment-batch-1/opportunity-tool-independent-checks.py)，命令如下。脚本写临时输入到系统临时目录，真实模拟器／评分调用均为0。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/opportunity-tool-independent-checks.py
```

完整检查原件、精确定位、机器判定及费用事件在 [opportunity-tool-independent-review.json](./evidence/t4-conditional-payment-batch-1/opportunity-tool-independent-review.json)，SHA256 为 `97363c43554f990d12ae39383f4340c493bc8251b572dcd04db5e7834c2ff2a9`。本次只新增该原件、报告与独立复现脚本；生产、作者冻结材料、数据库、官方入口和网络均未触碰，也未读取新Sol自然验证效果。
