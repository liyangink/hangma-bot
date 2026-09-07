# 特殊胡牌与有财必拷响对拍样本

2026-09-07（UTC抓取时间逐条保存），从官方 `POST /portal/api/tools/fan-calc` 采集299个固定计算输入：298个HTTP 200（206成胡、92未成胡），1个白板总量越界HTTP 400。指南v18（updated_at=2026-09-06），原始响应见guide.json；完整来源及字节摘要见manifest.json。

## 覆盖

- 普通胡、财神参与顺/刻/将、非成胡反例；摸东/摸白对照。
- 普通型爆头、七对爆头、豪华/双豪华/三豪华七对，普通型与七对多解优先级。
- 杠开、连续杠、财飘/双财飘/三财飘、混合杠飘链。
- 手留四白排除爆头、手留加链内飘白合计四张加倍、512倍公式组合。
- 固定种子2026090709的80个随机样本，其中40个均匀抽牌，40个由成牌结构扰动，不用本地判断筛选官方输入。
- 既有v9金例重新请求当前v18计算器；相同请求去重并保留多个tags。

## 三种不同证明范围

1. **计算器数学对拍**：tests/unit/hangma/test_official_fan_matrix.py逐项比较成胡、静态爆头、番数、明细及庄闲结算。chain.count覆盖0—6，是工具参数边界；例如七对加纯杠链或六连杠能被工具计算，并不意味着真实牌局可达。高于真实牌局上界的合成倍率不得作为赛事策略效果依据。
2. **配置资格对照**：依据用户确认的“开关开启时有财必须爆头”，对同一结果分别应用false/true，验证规则候选及最终复核。计算器没有此开关，所以这是以其hu/baotou事实为基准叠加已确认房规，不伪造服务端已接受两种房规动作的证据。
3. **原场景与生命周期**：两次M4拒胡的副露原样场景由test_youcai_integration.py覆盖；这里A/B展开牌形只是数学对照。持续爆头继承由已有v18/action-chain官方轨迹另测，不能用静态计算器覆盖权威god。

## 复现

默认测试只读固定响应，不联网：

```bash
.venv/bin/python -m pytest -q tests/unit/hangma/test_official_fan_matrix.py tests/unit/hangma/test_youcai_integration.py
```

重新采集必须使用新的输出目录，不覆盖本快照：

```bash
.venv/bin/python review/youcai-rule-repair-2026-09-07/capture_fan_calc.py --out artifacts/probes/fan-calc-new
```

采集串行请求，间隔至少0.22秒，低于官方每IP每秒10次；仅此官方内网客户端关闭证书校验，不使用Token。输入和响应JSON保持严格可解析。响应分数中dealer_hu/nondealer_hu的lose为三家支付额，测试再映射到本地固定座位0—3积分向量。
