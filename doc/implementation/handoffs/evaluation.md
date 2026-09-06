# 评估线交付报告（handoffs/evaluation.md）

> 工作线：evaluation（评估线，包 evaluation）｜contract_id：parallel-v1
> 契约基线（C0）：cb1f0b759fcf0202bc34760f66858adc026eca1f（已含契约文档/向量提交 2539573；c17ce06 不含本批文档，未被当作基线）
> 完成阶段：E1（结果文件校验、汇总、固定决策比较、人工可读差异）+ E2（最小 Fake 引擎验证完整桌赛驱动循环编排）；E3/E4 依赖见 §6。

## 1. 开工记录

| 项 | 值 |
| --- | --- |
| 本线名称 | evaluation |
| contract_id | parallel-v1 |
| contract_commit | cb1f0b759fcf0202bc34760f66858adc026eca1f |
| 开工 git rev-parse HEAD | cb1f0b759fcf0202bc34760f66858adc026eca1f |
| 开工时本地 dirty | 否（git status --short 为空） |
| 交付时本地 dirty | 是（仅本线新增文件未提交；按共享 checkout 纪律不创建分支、不 commit/add/push，由主审集成） |
| Python 版本 | 3.11.15（uv 安装到 .uv-python/；系统默认 3.9.6 不满足 requires-python>=3.11） |
| 测试工具 | pytest 9.1.1 + pytest-asyncio 1.4.0（uv sync --dev 装入 .venv/） |
| 环境缓存 | .venv/、.uv-python/、.uv-cache/ 均在 .gitignore 内，不进入交付 |

## 2. 完成阶段及支持范围

- **E1 已交付**：MatchResult 结果行与 results.jsonl 读写校验、complete 一致性校验、
  状态/来源/排除汇总、固定决策比较（recorded_request 与 recomputed_rules 分离归因）、
  人工可读差异报告（report.json + report.md）、产物 manifest。
- **E2 已交付**：完整桌赛驱动 drive_match 只调用 SimulationEngine 公开方法
  （start/frame/advance），按帧全窗口先准备紧急动作再请求策略、复核后一次性
  advance；用最小 Fake 引擎（tests/offline/support.py）验证编排。结果行
  source_kind 为显式参数：真实 SimulationEngine 驱动路径才传 simulation，
  E2 编排验证（Fake 引擎）一律传 mock，mock 永不进入强度结论
  （修订轮修复项 7；evaluation-start §6）。
- **E3 仅等主审组合根装配**：模拟线已交付（simulation/engine.py 的
  SimulationEngine 与 simulation/interface.py 的冻结值对象落盘，见
  handoffs/simulation.md）。本线驱动与实验循环代码已按冻结公开方法写好，并已
  核对 SimulationFrame（revision/decisions/completed_hands/final_scores/
  blocked_reason）、SimulationDecision（window_key/observation/timeout_seconds）、
  MatchSpec 与 SimulationChoice 与本线驱动消费字段一致，无需改逻辑；剩余工作
  只是主审在组合根提供 bootstrap.build_evaluation_runtime("matches") 传真实
  engine/spec_factory/choice_factory 后复跑 matches 实验。
- **E4 未做（依赖真实运行数据）**：测试房间/自动匹配的汇总消费，走同一个
  summarize 入口。

## 3. 实际改动文件与公开导出

全部为本线认领文件（新增），未修改任何既有文件（含既有测试、kernel/hangma/
policy/application/adapters）：

| 文件 | 说明 |
| --- | --- |
| src/hangma_bot/offline/evaluate.py | 固定决策比较 + 完整桌赛驱动 + 实验配置 |
| src/hangma_bot/offline/evaluation_results.py | MatchResult、results.jsonl 读写校验、manifest、身份哈希、报告渲染 |
| src/hangma_bot/offline/evaluation_statistics.py | scenario 聚类配对、配对差、聚类 Bootstrap 置信区间、汇总报告 |
| scripts/evaluate.py | CLI：decisions / matches / summarize |
| tests/offline/ | conftest.py、support.py、make_evidence.py、test_*.py（6 个测试模块）+ evidence/ |

公开导出（评估线内部，跨线只消费文件）：

- evaluate.py：EXPERIMENT_SCHEMA_VERSION、DecisionExperiment、MatchExperiment、
  load_experiment、translate_budget、DecisionComparisonRow、compare_decision_row、
  run_decisions_comparison、build_decision_report、write_decision_rows、
  read_decision_rows、MatchDriverConfig、MatchDecisionRecord、MatchRunOutcome、
  drive_match、seat_policies_from、policy_ids_by_seat_from、build_match_result、
  run_match_experiment、write_report_files、BOOTSTRAP_RUNTIME_HOOK、
  BOOTSTRAP_CODEC_HOOK。
- evaluation_results.py：EVALUATION_SCHEMA_VERSION、MANIFEST_SCHEMA_VERSION、
  CONTRACT_ID、SIMULATION_SOURCE_NAMESPACE、SOURCE_KINDS、RESULT_STATUSES、
  hand_id、split_group_id、identity_digest、compute_rules_hash、GameKey、
  RuntimeCounts、MatchResult、match_result_from_json、check_complete_consistency、
  write_results_jsonl、read_results_jsonl、group_by_scenario、count_by_status、
  count_by_source_kind、filter_complete、excluded_summary、ManifestInput、
  EvaluationManifest、new_evaluation_manifest、write_manifest、render_report_md。
- evaluation_statistics.py：METRIC_TABLE_SCORE_DELTA、METRIC_TABLE_FIRST_RATE、
  TIE_METHODS、STRENGTH_SOURCE_KINDS、policy_seat、table_score_delta、
  table_first_indicator、metric_fn_for、PairedMatch、PairingOutcome、
  pair_matches、BootstrapResult、clustered_bootstrap_ci、summarize_results。

## 4. 测试命令、退出状态与证据

全部测试实际运行，未运行的项不标通过；mock 结果未冒充真实结论。

| 命令（仓库根） | 结果 | 退出码 |
| --- | --- | --- |
| uv run python -m pytest tests/offline -q | 74 passed（修订轮后复跑） | 0 |
| uv run python -m pytest tests/offline tests/unit/policy tests/contracts tests/unit/kernel tests/unit/hangma -q | 827 passed（修订轮后；含共享 checkout 中其他线在途新增测试，本线未改动那些文件） | 0 |
| PYTHONPATH=src:tests/offline uv run python tests/offline/make_evidence.py | 样例产物生成成功 | 0 |

证据路径：tests/offline/evidence/test-run.txt（tests/offline 运行记录，74 passed）、
tests/offline/evidence/sample-results/（summarize 真实运行产物，mock 口径演示来源隔离）、
tests/offline/evidence/sample-decisions/（decisions 比较真实运行产物）。
聚类 Bootstrap 置信区间的数值行为（正方向/负方向/跨 0 与确定性）由
tests/offline/test_evaluation_statistics.py 覆盖；样例产物不伪造 simulation 证据。

验收覆盖（evaluation-start §6）：相同 request 重跑稳定（test_same_request_rerun_is_stable）；
规则重算分离（test_recomputed_rules_separated_from_policy_diff）；异常/超时保底计数
（decisions 与 matches 两侧）；缺 request 排除计数；不完整桌赛/作废/未知分数不进
complete（check_complete_consistency + status 映射测试）；座位换算方向（permutation 测试）；
同一 scenario 不当作独立样本（test_bootstrap_is_scenario_unit_not_pair_unit）；
mock 不升级成真实指标（test_summarize_isolates_mock_from_conclusions）。
契约向量消费：identity_cases / invalid_identity_cases / archived_room_cases 的
hand_id 与 split_group_id 派生、budget_translation（tests/offline/test_contract_vectors.py）。

## 5. 样例产物路径、SHA-256 与来源

生成命令见 §4；目录 tests/offline/evidence/（数据为 fixture 构造，只用于
格式与编排验证，报告内已声明统计纪律）：

| SHA-256 | 相对路径 |
| --- | --- |
| cea4f8559590bf9a8436607faa04e5a871960d8aa9bec3e6f659c971361ae02f | tests/offline/evidence/sample-results/results.jsonl |
| 45d8d7861c852c2df92bcd2f492d0cead501d9ca1af7f7c41656f0906f1b377e | tests/offline/evidence/sample-results/report.json |
| 12830b58f5b5e235128ca71651e939103ad760777c92c5591c7fc6c26090b94d | tests/offline/evidence/sample-results/report.md |
| 075c2f860c0d929ba502d7820f24ac6ae5b5bcf19d526640cc758c979350f490 | tests/offline/evidence/sample-decisions/decisions.jsonl |
| a0cd2306616e5b75dd68e614eee670a6aa82a174a5a2e59df5b43ed59068c911 | tests/offline/evidence/sample-decisions/report.json |
| 1969516787241237f86986ad748506ecbd20e91aa43809a04fae84572906234e | tests/offline/evidence/sample-decisions/report.md |
| 1f007bc0fbe68257528bd43e6a8a8be57ab7a00ec1296dbf666ba71869153c3b | tests/offline/evidence/sample-decisions/manifest.json |
| 949dc181f034ff8bb6079def1a1bd1b108a91b2c8ff0b162117af3e6e2553fd1 | tests/offline/evidence/sample-decisions/dataset/decisions.jsonl |
| 97e8c6b5e691bfb9d003f4ef99f3223909f5268a17e5552dbff4fa42923123ba | tests/offline/evidence/test-run.txt |

E3 真实引擎冒烟实验（主审集成后实测，目录
`tests/offline/evidence/e3-smoke-2026-09-05/`；复现命令：
`.venv/bin/python scripts/evaluate.py matches --experiment <目录>/experiment.json --out <新目录>`）：

| SHA-256 | 相对路径 | 说明 |
| --- | --- | --- |
| 1f97618a4214fbcc572450e6e938c2dd3eef627221de37498f7bbd56bded0749 | .../e3-smoke-2026-09-05/experiment.json | 实验配置：weighted_heuristic 对 weighted_heuristic_v1，2 牌山 × 4 换座 × 8 局 |
| cb907b9dde677a6126db729b434c5e501b5e7677363d83de736969bf8f8b28a2 | .../e3-smoke-2026-09-05/manifest.json | 产物 manifest（rules_hash 与模拟行同源） |
| b439625d72359a9e7f9307968ad54e3a86351b84ef0b71bd6e72c95e65cb77a7 | .../e3-smoke-2026-09-05/report.json | 汇总报告（结构） |
| 3b4a4cbf3449ce408a8258887e0084b38f699fc50612b0fa073cbd7a357e3bbd | .../e3-smoke-2026-09-05/report.md | 汇总报告（人读）；16 桌赛 0 排除，V1 方向为负，不声称改进 |
| f59b910ff0fade2c1e47c90b2b293bf5cadfd5229f83c0d2c40b30e933f0512b | .../e3-smoke-2026-09-05/results.jsonl | 16 行 MatchResult（source_kind=simulation） |

缺失声明：样例数据的 guide_version/guide_captured_at、rules_hash、真实
producer_commit/dirty 在 manifest 中为 null 或 missing_fields（fixture 运行无
真实提交证据；真实实验由 CLI 的 _git_state() 填 git rev-parse HEAD 与 dirty，
guide 字段当前无来源、恒写入 missing_fields——修订轮修复项 10）。

## 6. 未通过或未验证事项（含环境/资料限制）

- **E3 组合根已装配（主审集成 2026-09-05）**：bootstrap.py 已提供
  build_evaluation_runtime(kind="matches")（真实 SimulationEngine +
  MatchSpec/SimulationChoice 工厂）与 build_decision_codec()（审计 C1 codec
  注入）；真实 matches 实验经 scripts/evaluate.py 复跑验证（见主审集成记录）。
  钩子缺失时的明确报错路径保留不变（不伪造引擎）。
- **decisions CLI 生产路径依赖审计 codec（C1）**：本线只定义注入接缝
  decode_request/decode_budget，生产解码器由组合根 build_decision_codec() 提供；
  测试使用公开类型构造的 fixture codec（tests/offline/support.py），fixture 不是
  生产 codec，也未声称审计格式已验收。
- **耗时结论**：clock_mode=logical 的实验 elapsed_ms 为 null，不证明 1 秒窗口
  性能；真实耗时须另跑 clock_mode=real。
- **赛事晋级指标未实现**：契约 §7 要求完整阶段/赛事样本或确认的阶段模拟齐备后
  再输出；当前 summarize 只输出桌内积分差与桌赛第一率（本地分数口径，另标方法）。
- **未跑与本线无关的既有测试**（tests/adapters、tests/integration 等）：未运行
  不代表通过或失败；本线证据口径为 tests/offline 74 passed，连同 unit/policy、
  contracts、unit/kernel、unit/hangma 的汇总命令为 827 passed（该汇总数包含
  共享 checkout 中其他线在途新增测试，与 §4/§10 一致）。
- **mock/Fake 数据纪律**：tests/offline/evidence 与全部测试的合成数据只用于
  编排与格式验证；summarize_results 对 mock 来源隔离且结论只写「未证明改进」。

## 6.1 主审集成完成记录（2026-09-05）

- 组合根钩子已落地：bootstrap.build_decision_codec()（审计 C1 codec）与
  bootstrap.build_evaluation_runtime(kind="matches")（真实引擎 + 工厂）
  均已提供；decisions/matches 生产路径不再依赖脚本内置回退。
- CLI 测试同步更新：钩子缺失的防御分支改为进程内测试（monkeypatch），
  新增「真实 codec 下坏行排除计数」与「真实引擎完整桌赛实验跑通」两条
  集成测试；scripts/evaluate.py 的 build_policy 补 weighted_heuristic_v1
  装配（E3 可用稳定版对比 V1 候选）。
- 身份哈希与 rules_hash 唯一落点见 §7.3（已裁定）。tests/offline 97 passed，
  全套 1648 passed, 1 skipped。

## 7. 需要主审集成的共享文件差异（具体符号/调用点）

本线未编辑任何共享文件；以下为集成时需要的改动，请主审统一落盘：

1. **src/hangma_bot/offline/__init__.py（共享父目录 __init__.py，主审）**
   当前目录内无 __init__.py（Python 3.11 命名空间包可导入，测试已运行通过）。
   审计/模拟/评估三线共用 offline 包，建议主审创建该文件（docstring + 各线
   公共版本常量 re-export）。不影响本线测试；wheel 打包前必须有该文件。

2. **bootstrap.py（主审，两个可选钩子）**
   本线脚本以 getattr 探测，缺失时 decisions 退回脚本内置显式装配、matches
   明确报错。集成时建议提供：
   - build_evaluation_runtime(kind: str, experiment) -> dict | None
     - kind="matches" 必须返回 {"engine": SimulationEngine,
       "spec_factory": Callable[..., MatchSpec],
       "choice_factory": Callable[[WindowKey, Action], SimulationChoice],
       "policies_by_id"?: Mapping[str, BotPolicy]}；
     - kind="decisions" 可选返回 {"baseline_policy": BotPolicy,
       "challenger_policy": BotPolicy}。
   - build_decision_codec() -> dict | None：返回
     {"decode_request": Callable[[Mapping], DecisionRequest],
     "decode_budget": Callable[[Mapping, float], DecisionBudget]}，内部委托
     审计线 C1 交付的 audit codec。

3. **身份哈希与 rules_hash 落点（契约 §4.1/§4.2，主审已裁定并落盘 2026-09-05）**
   - hand_id / split_group_id / identity_digest 唯一实现已提升到
     kernel.identity（无文件/业务依赖）；本模块与 simulation.identity、
     offline.replay 均已改为 re-export，三线同值（集成冒烟实测一致）。
   - compute_rules_hash 唯一实现位于 simulation.artifacts，口径为契约字面的
     「仓库相对 POSIX 路径」（旧双实现分别产出 d008d0a9…/78d9ac7e…，已收敛为
     后者 78d9ac7e…）；本模块改 re-export，与模拟导出行的 rules_hash 同源同值。

4. **策略版本标识**：scripts/evaluate.py 的 build_policy 在策略实例上设置
   policy_id 属性（仅诊断标识，不参与评分）。主审若希望统一策略版本口径
   （如组合根注入带 policy_id 的包装），可直接替换该函数；本线不依赖该属性的
   评分行为。

5. **pyproject.toml**：无需改动；hatchling packages=["src/hangma_bot"] 已覆盖
   新子包，但 wheel 收录依赖 offline/__init__.py（见第 1 条）。

6. 未请求对 kernel/*、hangma/*、policy/*、application/* 的任何改动。

## 8. 受控变更请求

无。本线未修改任何受控契约字段、单位、信息权限或标识算法。

## 9. 设计要点（供主审评审）

- **统计单位纪律**：聚类 Bootstrap 以 scenario 为抽样单位（scenario 均值再重采样）；
  配对只发生在同一 pair_id 内且逐座配置一致；mock 永不进入强度结论；
  数据不足输出「未证明改进（不等同于无差异）」。
- **MatchResult status 映射**：驱动 blocked/error → completed_hands>0 记 partial，
  否则 error；绝不把未完成记 complete、不合成流局。
- **驱动信息权限**：不读 WorldState 字段；engine/spec 结构访问；SimulationChoice
  由注入 choice_factory 构造（C0 无 simulation 模块，避免本线定义同名冻结类型）。
- **决策行消费**：按契约 §5.1 必需字段校验；缺 request 排除计数；recorded_request
  保留原 request.rules，recomputed_rules 用同一 observation 重算并单列旧/新规则差。
- **预算平移**：复现 contract-vectors budget_translation；三段间距不变，跨进程
  单调时钟不相减；逻辑时钟实验不产耗时结论。

## 10. 修订轮修复记录（key d4-81abf5，挑战者组合评审）

评审三项修复 + 一项保留：

- **修复项 6（decision_id 唯一性）**：drive_match 的窗口决策标识原先由
  match_id/game_id/round_no/trigger_seq/phase 组成，同帧多窗口（如三家碰响应）
  会共享同一 decision_id，违反 AGENTS.md §8 唯一决策标识链路。现已追加座位
  成分（decision_id 后缀 :seat{座位}），并让 MatchDecisionRecord 携带
  decision_id 落审计事实；新增回归测试
  test_same_frame_windows_have_unique_decision_ids（同帧四窗口唯一性 + 座位
  后缀断言）。
- **修复项 7（source_kind 显式化）**：build_match_result 原硬编码
  source_kind=simulation，Fake 引擎（E2）产物与真实强度证据不可区分。现改为
  显式参数（默认 simulation 仅代表真实驱动路径），run_match_experiment 透传；
  E2 编排测试一律传 mock 并新增
  test_run_match_experiment_mock_labeled_and_excluded_from_strength（mock 行
  被 pair_matches 排除、summarize 结论为数据不足），保留
  test_run_match_experiment_simulation_labeled_pairs 显式验证真实驱动路径的
  配对管道。样例产物 sample-results 同步改为 mock 口径（不伪造 simulation 证据）。
- **修复项 10（manifest missing_fields 诚实）**：CLI 生成 manifest 时
  guide_version/guide_captured_at 恒 null 但未登记。现 null 字段（guide 两字段、
  config、producer_commit、dirty、input_sha256）一律写入 missing_fields；
  新增 CLI 测试断言。make_evidence 的 fixture manifest 同步补 rules_hash 等
  缺失登记。
- **保留项（发现 4 双算法）**：rules_hash/身份哈希的跨线唯一落点由主审集成时
  统一裁定；本线保留 §7.3 原登记，未自行修改 simulation 侧任何文件。

修复后证据：tests/offline 74 passed（退出码 0，证据 tests/offline/evidence/
test-run.txt）；连同 unit/policy、contracts、unit/kernel、unit/hangma 共
827 passed（该数包含共享 checkout 中其他线在途新增测试，本线未改动其文件）。
样例产物哈希已在本文件 §5 更新。

## 11. E3 工厂修复与重新验收（2026-09-06）

首次 E3 的 −75 来自 V1 时钟未注入、全程异常保底，不能作为 V1 正常策略强度证据。原产物保留；工厂补齐时钟与权重后原配置复跑为 16 完整桌赛、0 排除、0 保底、配对积分差 0。策略主动超时分类与报告运行故障计数同步补齐，288 项相关回归通过。详情与可复现证据见 [E3 诊断记录](../reviews/e3-clock-diagnosis-2026-09-06.md)。
