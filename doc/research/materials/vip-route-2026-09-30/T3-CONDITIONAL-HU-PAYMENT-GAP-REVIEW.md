# 下一摸条件胡支付的表达边界

2026-09-30，独立只读审核。**等待态不能携带“已发生结算”是明确且正确的类型边界；已计算的逐码条件支付未投影给候选，是首版未规定的表达缺口。值得下一版补齐，不能直接判为 v1 字段合同违例，也不能据此归因桌赛得失。**本次零评分、零 API、零桌赛，未改冻结源码。

| 可核事实 | 证据 |
| --- | --- |
| 合同只明确当前胡支付；同时允许窄胡见证返回结算。Astra 要求给定自然摸牌的胡分支由同源规则判资格及结算，未要求丢弃条件支付。 | [固定合同:48、56](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/FIXED-FRAMEWORK-CONTRACT.md:48)、[Astra:43、72](/Users/liyang/hangma-bot/review/vip-route-2026-09-30/VIP-FIXED-FRAMEWORK-EOH-IMPLEMENTATION-REVISION-ASTRA.md:72) |
| 窄见证返回逐码 `Settlement`，含番数、四座净积分和明细；VIP 等待投影检查结算非空后，只留下胡牌码集合及宽度，支付被丢弃。 | [胡见证:127](/Users/liyang/hangma-bot/src/hangma_bot/hangma/route_hu_witness.py:127)、[投影:230](/Users/liyang/hangma-bot/src/hangma_bot/policy/route_vip_heuristic.py:230)、[等待字段:49](/Users/liyang/hangma-bot/src/hangma_bot/policy/route_heuristic_view.py:49) |
| `wait.settlement=None` 防止把等待误写成已胡。当前胡及杠补后的显式胡叶仍保留真实支付。旧 `value_facts.routes[].conditional_settlement` 也保留条件支付，但没有进入新 VIP 候选映射。 | [节点约束:134](/Users/liyang/hangma-bot/src/hangma_bot/policy/route_heuristic_view.py:134)、[条件胡叶:275](/Users/liyang/hangma-bot/src/hangma_bot/policy/route_vip_heuristic.py:275)、[ValueRoute:414](/Users/liyang/hangma-bot/src/hangma_bot/hangma/interface.py:414) |

因此，普通下一摸已能精确判合法胡及支付时，候选仍不能直接利用每个码的番数差异、支付或支付分布，只能用保白量 `k`、结构缺口、链、爆头及宽度等代理作高番取舍。保白量不是合法高番或净积分的替代；补齐该事实可减少这部分猜权重，仍不能把更远多步路线变成真实期望积分。

建议下一版在 `RouteWaitingView` 增加**独立条件支付表**，复用已算见证，保持等待节点没有当前结算。按“牌码、普通摸牌来源、抓打限制包络、给定墙余”关联合法胡、可空结算、摸后爆头、链证据及缺失原因。四座净积分固定座位 0—3、单位积分点；候选声明其到无量纲排序点的变换。不同支付不可仅按相同宽度合并，也不能选最大支付冒充必然。

资格必须继续限定为 `local_witness_only`：仅适用于已合法弃后的 `13-3m` 手、给定规则与座位、精确正容量、可普通摸的给定墙余及对应抓打条件。受限／自由包络分列，不叠加两次机会；当前规则抓打仍允许自摸胡，也不证明未来会保持某包络。未知资格或支付保留 `None` 和原因，不补零。吃碰先获显式条件裁决再弃牌；杠补与普通摸分开。见证不证明中途无人先胡、能活到下一摸或墙内确有该码，公开未见容量包含他家暗牌，不能除以墙余当概率。

增加字段应另冻视图、事实语义、合同和候选身份，验证同源结算、包络区分、未知／零容量、末墙、吃碰及杠补，并重新测量工作量和耗时。当前在途源码、记录和实验保持原身份；此建议不授强度、时限或发布结论。
