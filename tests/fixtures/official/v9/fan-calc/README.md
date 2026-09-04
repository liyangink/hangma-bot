# 官方 fan-calc 金例夹具（v9）

> 来源：`POST https://10.240.169.190:18080/portal/api/tools/fan-calc`（免认证试算工具，口径与对局结算同源）
> 官方指南版本：v9（`../guide-version.json`，2026-09-03 抓取；规则语义与 v8 一致）
> 抓取日期：2026-09-03（Asia/Shanghai）；采集脚本：`capture.py`（可重跑刷新）
> 脱敏说明：fan-calc 为免认证纯计算接口，请求/响应不含 Token 或身份信息

## 文件

- `cases.jsonl`：25 例主套件（支付公式、番数公式、七对/豪华、4 白板、财神替代、未胡反例、400 校验）。
- `cases-baotou.jsonl`、`cases-baotou2.jsonl`：12 例爆头边界探测。
- `cases-chain4.jsonl`：3 例链型命名补录（count=piao=4 → 连飘×4）。
- `cases-random-crossval.jsonl`：59 例随机偏置对拍（seed 987654321，23 例成胡；本地判定与官方 0 差异）。
- 每行一个 JSON：`{tag, request|hand/draw/chain, response|resp}`；400 用例带 `http_status`。

## 结论摘要（详细推导见 `src/hangma_bot/hangma/RULES_EVIDENCE.md`）

- 总番 = 分支 × 2^链次数 × (4白板?2) × (爆头?2)；庄家胡 +24·番·底，闲家胡 +10·番·底（庄 -8·番·底，闲 -1·番·底）。
- 爆头判定为金例拟合规则（无官方条文），全部 37 例必须回归通过。
