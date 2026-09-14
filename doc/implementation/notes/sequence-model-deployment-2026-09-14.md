# 序列策略网络候选接入主线（2026-09-14）

**三个序列策略网络候选已接入主线的 `choose` 接缝，可按运行策略名在正式赛、自由房与测试房中显式启用；默认策略不变。**本文记录接入范围、已完成的验证、启用方式与残留风险。**候选尚未证明优于或不劣于稳定版本 V2**，本次接入是为了在真实环境取数，不是已验收的强度提升。

## 1. 接入内容

| 位置 | 内容 | 性质 |
| --- | --- | --- |
| `src/hangma_bot/learning/encoding.py`、`key_encoding.py`、`sequence_encoding.py`、`sequence_policy.py` | 训练与推理共用的观察编码、动作编码与网络定义 | 从训练分支原样取用，未改写 |
| `src/hangma_bot/learning/sequence_model_artifact.py` | 部署包装载与身份复核 | 新增 |
| `src/hangma_bot/policy/sequence_model_policy.py` | 唯一线上决策接缝的模型包装 | 新增 |
| `src/hangma_bot/bootstrap.py` | 三个策略名、部署包目录配置、组合根装配、条件分值规则增强的范围判定 | 新增接线 |
| `prebuilt/sequence-policy-models/<候选>/{manifest.json,model.pt}` | 自包含部署包，合计约 2.1 MB | 新增制品 |
| `scripts/export_sequence_model.py` | 训练终点 → 部署包的导出与复核 | 新增 |
| `tests/unit/policy/test_sequence_model_policy.py` | 11 项装载、排序与全路径降级用例 | 新增 |
| `pyproject.toml` | 新增可选依赖 `model = ["torch>=2.4,<3"]` | 默认安装不引入 torch |

未改动 `policy/interface.py`、`kernel/`、`hangma/interface.py` 与既有策略实现；`OnlineDecisionPlan` 结构与审计格式不变。

## 2. 三个候选

| 策略名 | 部署包 | 训练牌山 | 参数身份（前 16 位） | 候选 − V2（三家 V2 池 / 混合池） |
| --- | --- | ---: | --- | --- |
| `sequence_model_2048_projected_v1` | `2048-projected` | 2048 | `bf7df4182f2677db` | +3.33 / +1.28 |
| `sequence_model_4096_direct_v1` | `4096-direct` | 4096 | `bdc508a94eea56d8` | +2.35 / +2.63 |
| `sequence_model_4096_projected_v1` | `4096-projected` | 4096 | `8245f3bd1258e4ec` | +2.37 / +2.86 |

数值为 256 个开发牌山、四换座、5376 桌的完整桌赛本人积分差点估计；**八项主要比较的同时 95% 区间全部跨零**，两个池的普通边际区间除 2048 投影的三家 V2 池外也全部跨零。各候选的基线固定为完整 V2（与训练时的对手同源），因此与 V2 的差别只来自网络排序。

## 3. 如何启用

在运行配置里显式写策略名；不写则仍是 `DEFAULT_STRATEGY`（V0）。

```jsonc
// 非官方说明性示例，不能直接发送给平台
{
  "mode": "test_room",              // 或 test_tournament / official_tournament / auto_match
  "strategy": "sequence_model_4096_projected_v1",
  "sequence_model_dir": null        // 省略时取仓库内 prebuilt/sequence-policy-models
}
```

**部署机必须额外安装模型依赖**：`pip install -e ".[model]"`。未选择模型策略时线上不导入 torch。

**规则范围硬约束**：三个策略都要求 `ruleset_version=hangma-mvp-v10-public-counts`、`base_score=1`、`you_cai_bi_kao=false`，且必须启用条件分值增强（`ValueAnalysisLimits` 默认 `max_expansions=2048`、`max_routes_per_candidate=128`）。范围不符时**启动即拒绝**（`_test_room_upgrade_rules` 的既有校验），不会带错配静默上线。自由房模式还要求运行时规则配置与校准范围一致；不一致时按既有逻辑关闭条件分值，模型随之整体降级为 V2。

## 4. 安全设计

决策顺序固定为：**紧急保底 → 完整 V2 基线 → 模型重排**。

| 情形 | 行为 | 审计原因 |
| --- | --- | --- |
| 增强截止时间已过 | 返回保底计划，不运行网络 | `sequence_model:budget_exhausted` |
| 基线超时或异常 | 返回保底计划 | `baseline_timeout` / `baseline_error` |
| 基线未覆盖全部合法候选 | 返回保底计划 | `baseline_invalid` |
| 规则不完整、规则版本不符或制品规则配置不符 | 恢复基线顺序 | `model_or_rules_unavailable` |
| 正常快照起步或跨单局，原事件归档未覆盖此前全部记录 | 正常编码并使用模型，保留真实记录覆盖标志 | 无（正常路径） |
| 存在未解决的观察问题 | 恢复基线顺序 | `observation_issues` |
| 唯一合法候选（强制动作） | 不运行网络，不改变评分 | 无（正常路径） |
| 网络异常或输出非法 | 恢复基线顺序 | `model_error` / `invalid_logits` |
| 模型运行后预算已耗尽 | 恢复基线顺序 | `budget_exhausted` |

模型不参与合法动作生成；紧急候选、已拒绝动作过滤仍由基线与应用层保持。失败只写稳定原因字符串，不写异常原文。

## 5. 已完成的验证

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 编码在线可复现 | 用主线规则解码训练请求并重新编码，**300/300 窗口逐位一致**（334 维上下文、公开历史、候选特征、动作键） | 本次接入核查 |
| 决策时延 | 编码中位 0.25 ms、最大 0.44 ms；前向真实窗口中位 0.35 ms；最坏窗口（512 行历史 × 128 候选）10.0 ms 单线程、3.9 ms 四线程；10 场并发批真实 13.7 ms 单线程 | 本机 M4 Pro 实测 |
| 网络规模 | 175554 参数，与训练统计一致 | 装载期断言 |
| 部署包自洽 | 三个包均重新装载并通过参数量、参数身份与有限性校验 | 单元测试 |
| 篡改与越界拒绝 | 权重字节改动、出现未声明成员均被拒绝 | 单元测试 |
| 全路径降级 | 预算耗尽、规则降级、版本不符、缺史、单候选、网络异常六类回退 | 单元测试 |
| 回归 | 主线全量测试 4558 passed、25 skipped | `pytest tests` |

## 6. 残留风险与未验收项

1. **强度未证明**：八项同时区间跨零；接入用于真实环境取数。正式赛使用属于用户明确决定的实测，不是统计门禁通过后的发布。
2. **真实时限未端到端验收**：以上时延是本机单进程基准，未覆盖正式赛多场并发、磁盘/日志竞争与官方 1 秒/3 秒窗口下的整体链路。建议先在测试房与自由房观察 p99 与降级计数，再决定正式赛范围。
3. **训练与主线规则源码指纹不同**：训练 `rules_hash=295744c7…`，主线 `42e10127…`。两者差异来自 `hangma/engine.py` 的离线缓存（默认关闭）与 `hand_analysis.py` 中代数等价的七对公式重写，编码等价性已用 300 个真实窗口逐位核对。部署包记录两个指纹，便于追溯。
4. **条件分值分布差异**：训练窗口全部带完整条件分值；线上若出现 `partial/unavailable`，编码仍可生成但属于未见分布，当前不额外降级。
5. **未同步的文档**：`doc/architecture.md` 与 `doc/implementation/interface-contracts.md` 尚未加入本策略枚举与新制品类型；模块接口未变，但流程图与策略目录需要补一次同步。

## 7. 回退方式

把运行配置的 `strategy` 改回 `v2_hu_upgrade_v1`（或留空取默认）即可，无需回滚代码或删除权重。模型运行中的任何失败也会自动回到同一条 V2 路径。

## 官方快照输入适配补充（2026-09-14）

原序列入口的全单局原事件归档要求已移除，按官方快照及后续连续增量构造模型输入。特征数值、维度及三个部署包字节不变，新增输入准入版本`official-snapshot-events-v1`写入评分理由。此修复解决正常输入被拒绝的问题，强度判断另行评估。当前生产基线为`V2HuUpgradePolicy`，本文早期“完整V2”说明不替代实际组合根。验证及原测试赛复查见[修复报告](../../../review/model-fallback-2026-09-14/README.md)。
