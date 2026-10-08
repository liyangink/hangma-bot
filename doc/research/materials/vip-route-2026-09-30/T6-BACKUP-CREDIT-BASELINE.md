# T6 备用奖励反向诊断与父代基线

已实际检出原 S06 的分项反例，快速命令返回 **RED，退出码 1**。三份源码在同一真实公开观察的全部 11 合法根上各新评分一次，共 3 次收费评分、33 根；全部有限，分数和追踪记录与 T5 原件精确一致。该诊断检验公式性质，不证明宽动作必胜，不是官方规则错误或固定弃牌门。模型、网络、新桌赛、完整世界推进均 0。

## 最小反例可直接给作者

夹具是**纯算术（`arithmetic-only`，仅改变公式中的抽象集合）**，不是新的玩家可见状态（`PlayerObservation`）或生产视图。目标、所有逐码公开容量、缺口、保白与待弃成本均取自真实双白题弃6万后的普通等待前驱目标；它只有距离事实，没有伪造历史自然码或成牌见证。

固定目标：`retained_whites=1, natural_need=4, white_discard=0, natural_discard=4`。原锚为 `[3w,8w,3b,8b,1t,2t,7t,白]`，8码/22公开未见张。只从**抽象锚**删除 `3w`，该码真实公开容量为3；其余目标和容量向量均不变。缩减锚7码/19张，目标减锚的支持从73增至76。

```text
S06 backup = max(0, max_target(
  1.6 + 0.75*min(3,kept) - 1.15*need
  - 0.45*white_drop - 0.22*natural_drop + 0.09*差集公开容量))
speed = 6*锚容量/(14+锚容量)*锚码数/(锚码数+4)
```

|分项|原锚|删除一码锚|变化|
|---|---:|---:|---:|
|S06备用|3.44|3.71|+0.27|
|速度|2.4444444444|2.1983471074|−0.2460973370|
|S06速度加备用|5.8844444444|5.9083471074|**+0.0239026630**|
|cash父备用|0.27|0.42|+0.15|
|cash父速度加备用|2.7144444444|2.6183471074|−0.0960973370|

目标没有改善，S06的联合分项却因主锚缩小而增加。cash父也有备用反向，但这一个码的删除尚未令它的联合分项反增。完整检查枚举187个真实根派生的单码算术夹具，S06备用反增20个，速度加备用反增19个；不是187个新观察或独立统计样本。

短材料为 [author-counterexample.json](evidence/t6-absolute-route-credit-1/diagnostic/author-counterexample.json)，仅2725字节，SHA `02ec4a20f35b8dde44afb7d566c55df2be829fda60093042924871bdea5403af`。完整11根、42目标逐码算术见 [backup-credit-check.json](evidence/t6-absolute-route-credit-1/diagnostic/backup-credit-check.json)。

## 两个机制风险分别保留

真实观察中，弃3万/8饼的普通与七对向听均2，综合最佳推进23码/77或76张、备用0；弃6万普通向听变3、七对仍2，综合最佳推进8码/22张、S06备用3.44。此处只是完整合法替代根之间的事实关联，不能推出动作收益支配。

|真实根|普通向听/其自身支持|七对向听/其自身支持|
|---|---|---|
|弃3万|2 / 19码66张|2 / 8码22张|
|弃8饼|2 / 19码65张|2 / 8码22张|
|弃6万|3 / 26码90张|2 / 8码22张|

第一风险是锚差集制造备用信用；第二风险是更慢的普通路线可能有更大的绝对进张集合。下一联合公式应分别保存普通、七对、保白目标的绝对距离与支持，明确距离折减和主路机会成本，再处理交集去重及备用边际信用。不能直接把各路线公开支持相加，也不能把公开未见张数当牌墙命中概率。新公式仍需真实观察和续打证据；这里不给任何一张牌设必打效果门。

## 实际基线、身份和费用

用生产 `HangmaRules` 与 `build_vip_route_scoring_view` 重建完整 v2 图，通过 `ActionValueExecutor` 的受限 `score_actions` 接缝评分，每次上限300000操作。公共图 SHA 为 `6ef6466e9b66f8cd9f4c89760d63104ffb0b85d8998349413adb91fcbb0fa253`。图有11根/11节点，没有条件图缺口；本卡未知资格码为0，全部未知/可空字段原状态逐节点保存，未将 `None` 转成零或空列表。

|源码|源SHA|真实首选|操作数|实际新评分|
|---|---|---|---:|---:|
|GLM cash父|`33e71d021397873dc303796dcc5315e6b66a62eb81184994469366948755a590`|弃3万|12386|1|
|S06|`0c7001986006e7eaddeb90894919333a03e3089c9c64c751114014434e62b297`|弃6万|12386|1|
|S01|`c2e018be1fe15f87bc1dfbf5791aacb13b0074c9e72a5a21299ec7aa0cd33dd6`|弃8饼|7967|1|

身份、合同、生产闭包、额度和原输入在运行首尾稳定。先验 [plan-v3.json](evidence/t6-absolute-route-credit-1/diagnostic/plan-v3.json) SHA `876d4a2caf559cecf10a727b5ed9af6da39241ea31616c93b32c531831cb4d33`；完整新评分 [raw-scores.json](evidence/t6-absolute-route-credit-1/diagnostic/raw-scores.json) SHA `957cd4804b61563b8739de30bbf6832ee5295c384f08fdd8ce51ed9eb5fb038c`；[收费收据](evidence/t6-absolute-route-credit-1/diagnostic/score-receipt.json)明确计3次。旧评分仅交叉核验，没有冒充新调用。

首两次控制器在评分前失败，均新增评分0，原脚本、计划和失败保存：第一次是审计映射中的DTO元组与JSON列表直接比较，图SHA实际完全相同；第二次是规则原序合法根与排序序列直接比较。第二次之后误提前启动的算术命令退出2，保存为无效先决条件，不记RED。新v3仅规范化审计JSON和合法根比较次序，不改真实View、候选或生产代码。全部T5原件未改。

## 可复算命令和通用三题入口

从仓库根运行，正常发现反例时退出1；输入/适配器失效时退出2。此命令约20毫秒，不装载或评分候选，可重复运行且不覆盖证据。

```bash
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/diagnostic/backup_credit_diagnostic_v3.py check
```

该脚本 SHA `017b51fc4a1ecb920157f407851bfbb436d482683256c4d52a74534b6ed43db6`；[实际RED进程收据](evidence/t6-absolute-route-credit-1/diagnostic/red-execution-receipt-v3.json)保存命令、stdout和真实退出码1。机器检查 SHA `51f7a117c24a13a6c693ba7545bd855cd974a5b511ff2c6484df2858c87cbba6`；简明机器基线 [baseline-result.json](evidence/t6-absolute-route-credit-1/diagnostic/baseline-result.json) SHA `fedbfcb24d041b5fdddedcdd0be2ad093dc6b8225d4991fbcf96933fb3b138ed`。

[run_three_cards.py](evidence/t6-absolute-route-credit-1/diagnostic/run_three_cards.py) SHA `4b1401b13228b3439bc9ffb1bae59a9f918a3fe118d0b9ffd40d25043396d3a1`，支持 `prepare`/`execute`、新输出目录及重复 `--package ROLE=PATH`、`--source-sha ROLE=SHA256`。角色是 `manual,parent_1,parent_2,candidate`，e2两父明确绑定提案原父身份；每题每角色真实1次，失败保留分母。三题顺序固定，不以结果换题，原评分不充作新评分。该通用候选执行入口尚未对新T6提案运行。

已实际运行其 `verify-views` 零评分预检：大牌正控7根、双白11根、未知支付2根，三份完整当前图与旧冻结SHA分别精确相同，未知状态原样保留。详见 [三图验证](evidence/t6-absolute-route-credit-1/diagnostic/three-view-verification/view-verification.json)。此预检新增候选装载与评分均0，不增加任何候选行为信用。
