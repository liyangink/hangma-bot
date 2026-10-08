# P0 分支支付资格受控契约草稿

本稿仅用于父agent合入正式契约、架构和主技术方案。生产文档未修改。变更保持`HangmaRules`公共接口签名；政策层、观察序列化和网络协议不新增字段。

`WinSplit`是hangma内部14张胡牌分解元数据，追加字段`seven_pairs_baotou: Optional[bool] = None`，不改变已有五个位置参数。字段只表达七对分支爆头**支付**资格，不替代`any_tile_tenpai`或权威`RulePublicState.baotou`。

| 值 | 语义 | 允许使用 |
|---|---|---|
| true | 准确无副露摸前13张符合七对任意听 | 全局旗true时额外乘2 |
| false | 同上下文确认七对不是任意听 | 全局旗true也不额外乘2；不撤销Hu资格 |
| null/None | 缺摸前上下文，14张分解无法判断 | 七对且全局旗true时支付失败；不得默认true或false |

内部公式单元测试可由封存官方明细显式给已付资格；这只复现该版本公式，不构成现行手牌资格推断。真实调用方必须提供本人准确摸前暗牌。非bool且非None的资格抛ValueError。

`settle_win(..., *, pre_draw_hand: Optional[Tuple[Tile, ...]] = None, meld_set_count: int = 0)`新增两个keyword-only参数。前者只含本人暗牌，不含本次摸牌、他家手牌或未来牌墙；后者是当时副露面子数。七对且全局爆头true时，有pre_draw_hand则每次由唯一hand_analysis重新资格化，覆盖旧对象元数据；没有上下文且资格None则明确失败。有副露、长度不是13或第五张同种牌不得用来计算七对支付资格。平胡/全局旗false不增加此输入依赖。

`qualify_seven_pairs_baotou(win, pre_draw_hand, meld_set_count)`是hangma内部纯数学入口：无I/O、无网络/时间/模型、副作用仅返回新的不可变WinSplit。无副露、准确13张时，白数j > 自然奇数张码个数q恰为七对任意听。14张分解LRU中资格维持None，不能把某次draw的资格存入最终14张缓存。同final14三种draw交替测试必须通过。

所有七个生产支付调用位置已统一传准确前驱，详见p0-evidence/INVESTIGATION.md；模拟与offline审计同用settle_win，不建立第二套规则。`compute_fan`保持原四参数签名，消费已核元数据；七对/globaltrue/None显式ValueError。合法动作、紧急路径和YouCaiBiKao门保持全局旗既有语义。无drawn14张无法恢复前驱时支付报错，不能擅自移除某张，基本分析保持既有胡门/降级语义。

证据为指南v35（2026-09-23更新）及2026-10-06 UTC的13原始fan-calc HTTP200。正式规则身份必须由组合根统一指定，并重新绑定核心源码摘要、编译包与作用域；旧在线free包不得自动拾取新hangma而沿用旧验签。此隔离源码冻结不等于发布批准。
