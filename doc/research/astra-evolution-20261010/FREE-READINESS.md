# 自由赛第19房只读取证修复

第19房的未归类拒绝源于恢复快照仍为摸牌阶段但行动座位已经改变，现已用独立模块证明完整恢复链。旧运行根及失败门保持原件，当前没有激活新监督器或恢复匹配。本结论仅解决离线取证遗漏，不证明原弃牌没有错过、算法增强或候选可以发布。

## 原件事实与最小反馈

原四条均为官方`INVALID_ACTION`，原文`cannot discard in phase 2`。三条旧证明通过，未归类一条在第4单局、序号710、本家座位3。原规则完整、弃7w合法、即时复核通过、唯一尝试与POST各1。适配器结果为`SubmitRejectedClosed`，完整权威刷新713在结果返回前已经应用。刷新仍是`draw`，行动座位0；后来本家新摸牌窗731完整合法并唯一弃6w成功。没有盲目重复旧动作。

完整反馈两次稳定为`scan_complete=true, illegal_submissions=1, phase_index_complete=true, reclassified_proofs=3`。按同桌、同单局、原及恢复决策缩到14条两层审计、三份权威锚点，原结果不变；仅保留证明实际使用的两个窗口计数。两个应用层结果为谱系证据，不能冒称是prove的必要条件。缺证据型失败不会因删证据变绿，最小化保留待解释项及三个正控制，不以删除原问题制造成功。

按[诊断技能](/Users/liyang/.agents/skills/diagnosing-bugs/SKILL.md)先建立红反馈，再展示三个可证伪假设。只改恢复快照相位名为已支持的响应相位，其他字段不变，原prove通过；这是诊断反事实，不能改写真实输入。说明其他合法性、唯一提交及恢复时序条件均已满足，遗漏点在同相位换座守卫。

## 窄修复与反控

[生成工具](../../../tools/offline/free_match/runtime/closed_discard_repair.py)只接受第19房实际取证源SHA `501d62bfed009371e2efd2dfe8d18ff78d809360500fc2815cfebca20de62e18`。在原相位相同的拒绝条件中，仅增加真实摸牌阶段、有效整数行动座位、且不同于本家这一分支；旧完整证明逐项继续执行。布尔、缺失、越界座位及仍为本家行动继续阻断。不扩大其他动作类别，不按本机钟推断服务器收包或真实超时。

新模块SHA为`c4297fac0649426c4e95384e7829c541ada8e210fc4e70711a18facbd1cbfca4`，只写入本机`free-readiness/repaired_phase_rejection.py`及独立收据。生成器拒绝来源漂移和覆盖目标，不启动进程、发HTTP或修改旧门。

[回归](../../../tests/unit/offline/test_free_closed_discard_repair.py)在真实公开prove接缝先红后绿，共48项通过。覆盖原完整链、三个锚点、必要记录、旧／新重复POST、适配器重复意图、非法根、错误协议牌、错误座位／单局、未应用／有缺口／应用过晚、恢复失败及未知来源。完整回归需本机冻结原件；缺原件时明确跳过该部分，独立座位守卫和来源拒绝检查仍运行，不能把跳过算成完整验证。

全量原审计重新走未修改controller，仅换独立phase模块，得到`scan_complete=true, illegal_submissions=0, phase_index_complete=true, reclassified_proofs=4`。原三条proof逐字一致，controller与旧LIGHT-GATE摘要一致。再次用原phase重扫仍为非法1，证明原运行字节未被修改。四条可能错过弃牌、时钟及关闭原因未知保留。

## 产物与后续边界

全部原件在本机`.private/astra-evolution-20261010/free-readiness/`：`FEEDBACK-001/002.json`、`CASES-001/002/003.json`、`HYPOTHESIS-PROBES-001.json`、`REPAIRED-FEEDBACK-001.json`、`ORIGINAL-AFTER-REPAIR-FEEDBACK-003.json`及生成收据。公开精选回归输入已脱敏，完整房审计不入Git；诊断脚本只保存在明确的私有诊断目录，没有临时运行探针。

旧停止状态仍按[接手入口](../lowwhite-160-20261009/FREE-MATCH-TAKEOVER.md)核验。新根接续须独立冻结来源、保持唯一owner、旧资源自然终态和包作用域／生命周期回归。候选进入自由赛另需完整160单局独立效果门及真实截止可靠性；不能凭重分类为0自动激活或借用旧批准包身份。
