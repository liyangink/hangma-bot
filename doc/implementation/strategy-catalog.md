# 主线可用策略枚举

常用自由赛模板显式选择 `weighted_heuristic_v2`。省略 `strategy` 时，代码默认仍为 `weighted_heuristic`（V0），不会自动选择最新策略。

| 枚举值 | 支持的运行模式 | 说明 |
| --- | --- | --- |
| `weighted_heuristic` | 全部 | 冻结V0，省略配置时的默认值 |
| `weighted_heuristic_v1` | 全部 | 冻结V1，历史对照 |
| `weighted_heuristic_v2` | 全部 | 当前稳定选用值，常用模板显式指定 |
| `weighted_heuristic_v2_white_guard` | 全部 | V2普通弃财保护变体；尚未证明整体净分更高 |
| `v2_hu_upgrade_v1` | **自由赛 `auto_match`、测试房 `test_room`** | V2有界等胡实验候选，须显式选择；未替换默认，正式/测试赛事仍不接受 |
| `v2_balanced_shadow_v1` | **仅研究/影子运行** | 复用 `v2_hu_upgrade_v1` 保底并记录多路线前沿，不改变动作顺序；未通过完整桌赛门禁前不得用于线上提交 |
| `safe_fallback` | 全部 | 规则紧急动作，保底/诊断用途 |
| `claim_if_legal` | 解析器接受全部，用途限测试 | 主动鸣牌探针，不推荐自由赛策略比较 |
| `catch_play_probe` | 仅测试房 | 抓打圈取证探针，可将弃白排在胡前，不用于争取积分 |

`v2_hu_upgrade_v1`的增强范围为底分1、`YouCaiBiKao=false`、规则版本`hangma-mvp-v10-public-counts`。自由赛实际规则不适用时完整退回V2并审计，继续完成已入席房间；测试房仍拒绝不适用配置。风险参数来自V2模拟对手池，不代表真实对手风险已校准。配置、生效核验、条件事实和验证结果见[接入说明](v2-hu-upgrade-experimental.md)。

直接修改既有私有配置的策略项即可，下次进程启动生效：

```json
{"strategy": "v2_hu_upgrade_v1"}
```

`one_draw_value_v1`、`hu_upgrade_v1`、`v2_claim_piao_v1`、`v2_seven_pairs_wait_v1`等研究枚举没有在本次主线接入中开放。主线虽然包含等胡实现依赖的分值工具类，但不能因此把类名当成可配置策略。

`c_grouped`/`python_grouped`是规则数学后端，`YouCaiBiKao`是平台规则配置，均不是策略枚举。
