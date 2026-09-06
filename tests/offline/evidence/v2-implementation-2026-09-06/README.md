# V2 实现与工程验收（2026-09-06）

**V2 候选已实现，代码与运行检查通过；尚未证明策略效果提高，线上默认仍为 V0。**两牌山冒烟中 V2−V1 桌内积分差 −19.5，不能作为发布依据，也不能据此调参后重复挑选这批样本。

## 实现范围

- V1 验收已提交为 `7c6581c`；S2 过牌事实与旧版兼容提交为 `3ee9eef`。S3 新增 `ComparableHeuristicPolicyV2`，通过 `weighted_heuristic_v2` 配置选择，线上/测试房/离线入口共用原策略接口。
- 规则只增加响应过牌当前等待 `HAND_PROGRESS`，复用原向听和有效牌数学；校验响应手牌形状，失败保留合法紧急过牌。本地语义名为 `hangma-mvp-v2-pass-progress`，不是官方规则变更。
- V0/V1 源码与权重保持冻结。V0/claim_if_legal 显式使用 `legacy_pass.py`；V1 保持正常新过牌事实的中性偏好，异常事实继续按旧可靠性语义处理。
- V2 复用 V1 的非 Pass 评分和 `HeuristicWeightsV1`，只将过牌等待基线与吃碰统一比较。不同时调参，不加入搜索或隐藏信息。
- 缺可比等待基线时，未拒合法 Hu 优先，其次是未拒合法 Pass；剩余候选沿用 V1 排序。拒绝/重复/错误动作键过滤在前，不补造动作。原始规则事实保留，计划解释排序与兼容视图。

## 检查证据

| 检查 | 结果 |
| --- | --- |
| 全套测试 | `1714 passed, 1 skipped`，见 `regression.xml`；跳过项因原审计基线运行目录不存在 |
| 审查后加强断言 | 真实规则应过案例要求完整等待事实、无退路降级、分项匹配；claim_if_legal 要求实际兼容类。相关 61 项通过 |
| 自动冻结契约 | 新增 V0 五文件/V1 三文件哈希检查，8 项通过；后续更改旧策略源码会直接使回归失败 |
| 同输入解释案例 | 4 个构造观察经唯一规则引擎生成事实，原评估 CLI 比较 4 行、0 排除、0 保底；有两例由过转吃碰，也有两例由吃碰转过，见 [比较报告](./decision-comparison/report.md) |
| 实时预算基准 | V2 八项通过，固定/不同手牌、冷/热、M=1/10；数据见 `benchmark.json` |
| 完整桌赛冒烟 | 2 个新根组 × 四换座 × 两策略 = 16 个桌赛，各 8 单局；全部 simulation，0 排除，全部运行故障计数为 0 |

本地预算测量包含 emergency → analyze → choose → validate，从同一窗口接收时刻计时。M=10 固定响应最差约 21.5 ms；新进程十组不同响应手牌最差约 46.3 ms；新进程十组不同出牌手牌最差约 915.6 ms。没有放宽生产预算。样例基准不覆盖最坏牌型、真实 HTTP/SSE/磁盘开销，也不替代部署机器的测试房验收。

两名只读复查者分别检查规则等待口径和策略兼容/降级路径，未发现生产实现阻断项；提出的应过用例与装配断言已补齐。仅同输入案例不代表牌局最优动作。

## 冒烟结果与后续门禁

[原始冒烟报告](./match-smoke/report.md)中的 V2−V1 配对桌内积分差为 **−19.5，95% 聚类区间 [−21, −18]**；桌赛第一率差为 0。只有两个根组，区间不能可靠描述更广泛局面。本批用途为验证实际装配与完整桌赛执行，方向为负如实保留，尚无效果提升证据。

报告中的“稳定版本 weighted_heuristic_v1”是评估器对实验对照的通用文案；V1 是已验收的实验对照，线上默认仍为 `weighted_heuristic`。三个固定对手均为通过旧事实视图装配的 V0。初始庄家为待测逻辑身份；换座不是独立牌山样本。

下一步先对负向样本做决策分歧归因，再冻结独立样本进行受控比较。V2 对 V1 的改善证据不足时不自动进入 V3 调参或切换默认；发布前还需对线上 V0 的比较、实际部署 M 的测试房验收和目标赛事格式验证。

## 复现与跨机器迁移

使用包含本目录的 S3 提交，按 `source-freeze.json` 核对源码、完整权重与配置哈希。实际实验执行在 `3ee9eef` 加未提交 S3 实现上，manifest 的 `dirty=true` 如实保留；并行官方适配器审查文件未参与本次提交。

在仓库根目录执行，输出选择新的目录：

```bash
.venv/bin/python scripts/evaluate.py decisions \
  tests/offline/evidence/v2-implementation-2026-09-06/dataset \
  --experiment tests/offline/evidence/v2-implementation-2026-09-06/decision-experiment.json \
  --out NEW_DECISION_OUTPUT

.venv/bin/python scripts/evaluate.py matches \
  --experiment tests/offline/evidence/v2-implementation-2026-09-06/experiment.json \
  --out NEW_MATCH_OUTPUT

.venv/bin/python -m pytest -q tests
.venv/bin/python -m pytest -q -s tests/unit/policy/test_policy_benchmark.py -k v2
```

`dataset/decisions.jsonl` 是明确标注来源的本地构造案例，不是官方牌谱或完整世界训练数据。`decision-comparison/` 保存两版计划比较，`match-smoke/` 保存真实引擎结果与 manifest，`SHA256SUMS` 用于迁移校验。历史 V1 验收产物保持原样；它的旧源码冻结检查应在旧代码基点复现，不能使用 V2 代码冒充原实验。
