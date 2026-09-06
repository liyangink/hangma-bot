# 制品版本信息完备性评审（2026-09-06）

评审对象：统一牌谱（derived dataset 契约字段 + datasets/official-auto-match 原始下载包）、
可审计制品（audit JSONL 的 RUN_MANIFEST 与决策记录）、评估产物（manifest / MatchResult /
实验配置）与模拟牌谱行。评审问题：各制品是否携带足够的版本与来源信息——代码版本、
赛事类型、赛事配置（M/局数/有财必拷响）、赛事时间、策略版本与权重、模型配置。

## 1. 结论

- 评估产物与模拟牌谱行版本信息基本完备（见对照表）；
- **审计 RUN_MANIFEST 的版本事实键（git_commit/git_dirty/policy_version/
  policy_weights）原实现永远为 null**：保留键字典给了 null 默认值，而
  manifest_extra 被禁止覆盖任何保留键，注入通道被自身保护规则封死——本轮已修复；
- 评估 manifest 原只记「声明权重」，声明为空时实际生效的类默认权重不落盘
  （E3 诊断教训），无法事后复现——本轮已修复为记录生效快照；
- 官方原始下载包 manifest（自由赛线自制）缺代码版本与结构化赛事类型字段；
- 模型配置当前正确缺席：LLM 不进线上闭环，各 manifest 不设 model 字段，
  待 learning 阶段按契约 §4.2 versions 扩展。

## 2. 逐项对照

| 需求项 | 统一牌谱（derived） | 审计制品（RUN_MANIFEST） | 评估产物 | 模拟牌谱行 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 代码版本（git commit） | producer_commit + dirty（契约字段；audit_tool 需显式传参） | git_commit/git_dirty（本轮修复注入） | producer_commit + dirty | rules_hash + 契约版本（非 commit） | 基本完备，遗留见 §4.1 |
| 赛事类型 | source_namespace 约定平台实例 | mode（test_room/official_tournament/auto_match） | source_kind（simulation/test_room/auto_match/...） | origin（official/simulated） | 完备 |
| 赛事配置（M/局数/有财必拷响） | manifest.config（audit_tool 未传入 → 恒缺） | known_guide_version；M/局数未记 | config 全字段（max_games/rounds_per_game/rules/timing） | rule_config（ruleset_version/base_score/you_cai_bi_kao） | 官方侧缺失，遗留见 §4.2 |
| 赛事时间 | created_at_unix_ms | run 时间戳 + 事件 ts | created_at_unix_ms | 事件 ts（模拟为 null，逻辑时间） | 完备 |
| 策略版本和权重 | 不适用 | policy_version/policy_weights（本轮修复注入生效权重） | scoring_policies 的 policy_id/name/声明权重 + effective_weights（本轮修复） | 不适用 | 完备（修复后） |
| 模型配置 | 无 | 无 | 无 | 无 | 正确缺席 |

## 3. 本轮修复（已提交）

1. application/participant_runtime.py：_audit_plus_manifest_fields 把版本事实键
   （git_commit/git_dirty/source_file_hashes/policy_version/policy_weights）改为
   允许组合根注入；身份/安全键（capture_profile/audit_producer/source_namespace/
   python_version/redaction_configured）仍禁止覆盖。
2. bootstrap.py：RuntimeConfig 增加 source_namespace（默认 hangma-official）；
   build_runtime 与 build_auto_match_runtime 组装期注入 git_commit/git_dirty
   （取不到为 null，不冒充已提交代码）、policy_version（策略名）、
   policy_weights（生效权重快照）、ruleset_version；AutoMatchRuntime 增加
   manifest_extra 参数并贯穿三个 RUN_MANIFEST 发射点（其 source_namespace
   沿用 AutoMatchSettings 既有口径）。
3. scripts/evaluate.py：manifest 的 scoring_policies 每条增加 effective_weights
   （策略对象生效参数快照）；声明与生效分离落盘。
4. 回归：注入键语义 2 例、source_namespace 配置 3 例、版本事实助手 1 例；
   相关套件 502 passed；评估 manifest 冒烟确认生效权重落盘。

## 4. 遗留建议（他线认领文件，未擅改）

1. scripts/audit_tool.py（审计线）：convert 的 producer_commit/rules_hash 目前
   需显式传参；建议缺省自动取 git rev-parse HEAD（与 evaluate.py 同口径），
   并支持 --config 传入本地运行配置进 manifest.config，缺失登记 missing_fields。
2. datasets/official-auto-match/manifest.json（自由赛线）：补 producer_commit/
   dirty、结构化 mode=auto_match 与 rules_hash；房间级记录 rounds/批次事实。
3. 官方牌谱行 rule_config 恒 null 是契约允许（平台配置不在下载内容里）；平台
   真实 M/局数建议从官方下载（games.json/events 的房间事实）抽取进 hands 行
   或 validation（审计线）。
4. 模型配置：learning 阶段开始后按契约 §4.2 扩展 versions（模型产物版本、
   编码/网络/校准标识），并在本评审对照表基础上复核。
