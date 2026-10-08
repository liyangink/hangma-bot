# T8 两作者结果与固定模板修复

截至 2026-10-01，两次主作者GLM 5.3 API、两份修后身份各285机械及15历史评分已闭合；各64完整桌现已自然结束并通过独立全链审核。**历史弃牌有具体改进信号，但完整桌均为负差，不晋升。目标保持 active。** 修复没有新增模型调用；另有原登记S03的一次真实GLM参数关闭对照，其机械274次完成、11窗准备因我方漏文件失败，另件恢复中，历史15次尚未执行。

## 修后实际结果

两份新身份仅修正解释记录格式，保留作者公式、费用与原失败。生产修复工具151项测试通过；[独立驱动预检](./evidence/t8-bounded-natural-geometry-1/trace-repair-driver-final-preflight/REVIEW.md)已通过。两候选各285/285实际完成，全部合法根有限、来源前后稳定；原各57次成功候选评分的绝对分与完整排序精确相同，原各48次失败现均完成。根对账见[S01F](./evidence/t8-bounded-natural-geometry-1/S01F-glm-m1-v4-repair/ROOT-MECHANICAL-AND-HISTORICAL-POSTCHECK.json)、[S02](./evidence/t8-bounded-natural-geometry-1/S02-glm-m1-v4-repair/ROOT-MECHANICAL-AND-HISTORICAL-POSTCHECK.json)。[独立机械签收](./evidence/t8-bounded-natural-geometry-1/mechanical-post-review/REVIEW.md)已通过；[历史数学](./evidence/t8-bounded-natural-geometry-1/geometry-independent-math-review/HISTORICAL-REVIEW.md)与[保存机械视图数学](./evidence/t8-bounded-natural-geometry-1/geometry-independent-math-review/MECHANICAL-SAVED-VIEW-ADDENDUM.md)各候选复算39行355根，评分与排序差异0。独立数学范围不等于全部1234机械合法根。

| 实际检查 | S01F | S02 | 能说明什么 |
| --- | --- | --- | --- |
| 87窗口相对真实直接父 | 25窗绝对分变，首选0变 | 25窗绝对分变，首选1变 | 打法改变有限；S02唯一变化为暗杠3条改弃8饼，未证明收益 |
| 历史五窗三包评分 | 15/15完成 | 15/15完成 | 只读本人可见历史观察，不续打、不作独立确认 |
| `a0525-seq1350` | 首选由弃4万变为弃西 | 仍弃4万 | S01F区分了父代聚合进张同分的自然组成 |
| 其余四历史窗 | 首选全同父 | 首选全同父 | 没有扩大为全局行为改进 |
| 两个新身份的完整桌 | 64实例全部完成，H/M差−13.25/−4.875 | 64实例全部完成，H/M差−13.375/−4.875 | 各32配对、四共享母根，两者不晋升 |

1350窗口父代弃4万和弃西均为11.198347107438018。S01F分别评分11.263140495867768、11.285434995112414，真实选择弃西；S02两动作仍同分11.41469489414695。这里是启发式排序单位，不是积分或胡牌概率。独立复算确认，保留4万时摸5万可以形成456或567两种互斥自然顺子，5万的公开容量只计一次；没有把共享牌的两种组合当作同时完成的两副面子。该根改选来自普通结构支持项，不能称已证明保白高番路线兑现、自然面子成形更快或桌分更高。

## 已完成与当前限制

| 项目 | 当前观察 | 边界 |
| --- | --- | --- |
| 两次真实作者调用 | S01F、S02 均交付有效源码；合计 248642 token，包含推理 token，不重复相加 | Sol 分配受线程数量限制而失败，实际 Sol 作者调用为 0；不能称本批使用了 Sol max |
| 原候选机械检查 | 各实际执行 285 次，各完成 237 次、失败 48 次 | 原回复、源码、失败与费用保持；均未通过机械门，未执行自然桌 |
| 失败归因 | 96 次失败均为解释记录嵌套超过 3 层 | 来源是我方 v3 固定模板；不是作者越界、操作预算超额或官方超时 |
| 修正版默认控制 | v4 实际 105/105 完成，512 个动作评分均有限；全部窗口绝对分、排序和首选与旧参考一致 | 是默认公式的工程对照，不是模型候选的效果 |
| 修正版启用控制 | 实际 105/105 完成，512 个动作评分均有限；189 个动作产生有效结构解释，共 479 条解释记录 | 人工启用结构权重，验证实际分支可运行；不是强度提升 |

两作者分别尝试了“同一进张牌存在多少种自然顺子组合”和“组合完成后剩余对子、邻接结构是否较好”。这些是解决聚合进张同分后无法区分牌形的候选办法，仍需逐项复算与实际选牌验证。不能把多种互斥组合相加为多次进张概率，也不能强制把历史上某一张弃牌当作标准答案。

## 缺陷与修复

v3 只在结构权重实际启用时输出解释记录。记录中另包了一层牌码元组，超过执行器的三层上限；先前默认全 1 控制没有输出这段记录，因此漏测了该分支。这是我方控制覆盖不足。

v4 将同一条记录中的牌码展开，保留顺序及重复信息；评分公式、规则和预算没有随修复改变，沙箱限制也没有放宽。根代理逐件核对两组控制的封条、109 件输入、全部动作、有限数值、记录深度与观察不变性，见[修复后核对](./evidence/t8-bounded-natural-geometry-1/ROOT-V4-CONTROL-POSTCHECK.json)。这是根代理复核，尚未另授独立 agent 签收。

原失败详见 [S01F](./evidence/t8-bounded-natural-geometry-1/S01F-glm-m1/ROOT-MECHANICAL-FAILURE-DIAGNOSIS.json)、[S02](./evidence/t8-bounded-natural-geometry-1/S02-glm-m1/ROOT-MECHANICAL-FAILURE-DIAGNOSIS.json)；实际用量见[两作者闭合费用](./evidence/t8-bounded-natural-geometry-1/ROOT-TWO-AUTHOR-TERMINAL-COST.json)。前述v4控制是修后候选评分前的历史对照，现已另建明确的`trace_codec_repair`来源修复身份；原作者记录和编解码修复分别归属，不冒充新作者或新评分算法。

## 下一步

自然桌尚未启动时，根发现修复计划把原作者前完整种子`2026100901—0904`转录成了`901—904`。已[另件纠正](./evidence/t8-bounded-natural-geometry-1/ROOT-NATURAL-SEED-TRANSCRIPTION-CORRECTION.json)，保留原错误计划和封条；下一自然入口须绑定此纠正件，恢复原完整种子，64/候选与两主128桌实例预算不变。这不改变已完成的机械或历史评分。

1. 独立机械、保存视图数学及[自然入口合同审核](./evidence/t8-bounded-natural-geometry-1/natural-entry-contract-review/REVIEW.md)已通过。既有285与历史15不重跑；未知条件等未动态覆盖分支继续保留范围限制。
2. 两份预登记完整桌已自然结束，各4完整种子、H/M两池、四换座、每桌8局，各64实例，合计128。各405件输入和额外真实父代行为签收已绑定；S01F见证是已知历史1/5，原87窗为0，不伪称未见根或作者前1/5阈值。各129件原件先封再开效果，独立全链错误0。[完整结果](./T8-NATURAL64-CLOSED-RESULT-AND-NEXT.md)同时保留负桌均和同一母根的两次四番兑现；[封包](./T8-CLOSED-NATURAL64-ARCHIVE-INDEX.md)保留全部原字节。
3. S03参数关闭对照已实际一次GLM API交付，唯一把`SHAPEA`从0.5改为浮点0.0，其他源码逐字相同；[范围门](./evidence/t8-bounded-natural-geometry-1/S03-glm-m2-ablation-preparation/SOURCE-SCOPE-GATE.json)通过。实际机械执行结束，未知4、三题9、行为261次评分完成，11窗准备缺少`slot-and-evaluation-plan.json`，因此[原门](./evidence/t8-bounded-natural-geometry-1/S03-glm-m2-ablation-preparation/mechanical-results/MECHANICAL-GATE.json)失败；这是我方评测准备缺陷，原失败及274次完成保留，另件恢复前先查全输入。539件输入和驱动输出封条稳定，候选未被修改，15次历史尚未执行，新增自然桌预算0。新联合多父代方向另件前登记，重点检验普通出口与多白用途的共同权衡；仍需新机会根、未见母牌山确认及真实时限、接线与发布门。

上一批 T7 的 64 个完整桌实例已经独立复核，H/M 平均桌净分差为 −17.0625/−21.625，不晋升。完整原件已封存，见[归档索引](./T7-CLOSED-NATURAL64-ARCHIVE-INDEX.md)。T8同样未优于R18；两批母牌山不同，不能直接将负差缩小说成新公式改善。
