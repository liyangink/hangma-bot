# 审计工作线交接报告（audit-plus-v1）

- 工作线：audit
- contract_id：parallel-v1
- contract_commit：2539573（并行开发契约、施工导航与 contract-vectors.json 所在提交）
- code_commit：f129fba6672254ede43b1d62efd21834a21dc2ac（feature_more_audit 分支工作区，改动未提交；交付时由主审在 C1 后合入）
- 基线：源码基线 c17ce0618d17476526bfe8b2f69a19f11b19fb82（parallel-contracts.md 声明的实施基线）
- Python：3.11.15（仓库 .venv）；依赖：pytest 9.1.1、httpx 0.28.1（未新增任何依赖）

## 1. 完成阶段及支持范围

A1（完整决策记录）、A2（读取/归档/官方分块转换）、A3（inspect/watch 工具）均已实现并通过本线测试；组合根（bootstrap）装配与官方既有发送路径打点未动（按施工导航归主审）。

| 阶段 | 交付 | 状态 |
| --- | --- | --- |
| A1 | DECISION_INPUT / CANDIDATE_VALIDATED / DECISION_ENDED 采集；RUN_MANIFEST 增强；生产端失败持久化（producer_failure/producer_summary）；发送前越截止重检零 POST | 已实现 + 测试通过 |
| A2 | 共用读取器、bundle 打包/核验/安全展开、官方分块转换、统一牌谱 hand_id 跨进程合并 | 已实现 + 三个真实样本验收 |
| A3 | scripts/audit_tool.py 的 validate/inspect/watch/convert/pack/collect-test-room | 已实现 + CLI 冒烟 |

未验证事项（不写为通过）：

- 目标 M 的审计开销基准（P99≤10ms 是工程目标，非门禁）：未做目标 M 全程比赛，未做审计开关对照基准；
- 自由赛牌谱下载能力：官方自动匹配的赛后下载端点未确认，convert 对 auto_match 运行只输出决策行（身份来自运行上下文），官方单局行需等自由赛线确认下载接口后补充；
- 规则一致性（replay-check）：模拟线 offline/replay_check.py 未交付，validation 的 rule_consistency 固定为 not_checked；
- 世界可导入性：真实样本无未来牌墙，from_replay 必须拒绝导入（world_importability 为 not_checked 并注明 wall=null）；full_world 路径待模拟线导出后另测；
- collect-test-room 实测：命令已实现（免认证端点、先 .partial 后原子改名），但未在真实内网环境执行下载（无网络权限的评审环境）；三个 archived-rooms 夹具即该接口的真实产物，转换已按夹具验收。

## 2. 实际改动文件及公开导出

新增：

- src/hangma_bot/application/audit_codec.py —— 决策 codec 唯一实现。公开导出：
  decision_request_to_json/from_json、decision_budget_to_json/from_json、
  decision_plan_to_json/from_json、rule_analysis_to_json/from_json、
  rule_candidate_to_json/from_json、candidate_facts_to_json/from_json、
  translate_monotonic_deadlines（跨机预算平移）、DECISION_CODEC_VERSION=1、
  CAPTURE_PROFILE_AUDIT_PLUS_V1="audit-plus-v1"、AUDIT_PRODUCER_APPLICATION/_OFFICIAL。
- src/hangma_bot/adapters/recording/reader.py —— 共用读取器。公开导出：read_records、
  iter_records、ReadRecord/ReadResult/ReadIssue、read_bundle_manifest、
  BundleManifest/BundleFileEntry、BUNDLE_SCHEMA_VERSION=1。
- src/hangma_bot/adapters/recording/bundle.py —— 证据包。公开导出：create_bundle、
  verify_bundle、pack_bundle、extract_bundle、sha256_file/sha256_hex。
- src/hangma_bot/adapters/official/replay.py —— 官方分块转换。公开导出：
  parse_room_document、merge_round_events、round_data、coverage_grade、
  OfficialRoomDocument/OfficialBlock/OfficialRoundResult。
- src/hangma_bot/offline/__init__.py、src/hangma_bot/offline/replay.py —— 统一牌谱。
  公开导出：hand_id、split_group_id、build_dataset、load_hand_rows、
  REPLAY_SCHEMA_VERSION=1、MANIFEST_SCHEMA_VERSION=1、CONTRACT_ID="parallel-v1"。
- scripts/audit_tool.py —— 六命令 CLI。

修改（均为审计线认领文件）：

- application/contracts.py：AuditKind 增加 DECISION_INPUT/CANDIDATE_VALIDATED/
  DECISION_ENDED（方案 §3.2 的审计区域；其余区域为自由赛线并行改动）。
- application/audit.py：AuditTrail.emit_safe(kind, payload_factory, *, stage, ...) 安全
  构造入口；producer_failure/producer_summary 持久化；aclose 合并生产端缺失并反映降级。
- application/decision_loop.py：三新种类采集、DECISION_ENDED finally、发送前越截止
  重检（deadline_passed_after_audit）、INTENT/OUTCOME 增补 capture_profile/audit_producer。
- application/participant_runtime.py：RUN_MANIFEST 增强（capture_profile/audit_producer/
  source_namespace/python_version 等；新增可选参数 source_namespace、manifest_extra）。
- adapters/recording/schema.py：无改动（新种类自动纳入高优先级与 payload 版本表）。
- adapters/recording/raw_events.py：新增 RAW_SOURCE_MATCH_RESPONSE="match_response" 与
  build_match_response_payload(endpoint, http_status, raw, attempt=None)（自由赛线 C1 使用）。
- adapters/recording/validator.py：check_audit_plus() —— profile 开启时校验
  producer_summary 关闭证据、producer_failure 事实、决策输入/终结配对；报告新增
  audit_plus 小节（legacy 目录结论与升级前完全一致）。
- adapters/recording/__init__.py：导出 match_response 常量与构造器。
- 测试：新增 tests/contracts/test_audit_plus.py（9 例）、tests/unit/application/
  test_audit_codec.py（11）、test_audit_trail_plus.py（3）、test_decision_loop_audit_plus.py
  （7）、tests/adapters/recording/test_reader.py（8）、test_bundle.py（8）、
  test_audit_plus_validator.py（4）、tests/offline/test_replay_identity.py、
  test_replay_dataset.py（合计 15）。
- 既有测试同步（本线语义变化的最小更新）：tests/unit/application/test_audit_chain.py
  末条记录断言改为 producer_summary 收尾；tests/adapters/recording/test_integration_wiring.py
  written 24→25；tests/adapters/recording/test_raw_events.py 冻结词表加入 match_response。

## 3. 测试命令、退出状态与结果摘要

命令（仓库根，.venv）：

    .venv/bin/python -m pytest tests/ -q

结果（2026-09-05，与自由赛线并行编辑的同一工作区，最终一轮）：

    1402 passed in 20.92s

本线新增/修改测试单独运行：

    .venv/bin/python -m pytest tests/contracts/test_audit_plus.py tests/unit/application/test_audit_codec.py tests/unit/application/test_audit_trail_plus.py tests/unit/application/test_decision_loop_audit_plus.py tests/adapters/recording/test_reader.py tests/adapters/recording/test_bundle.py tests/adapters/recording/test_audit_plus_validator.py tests/offline/ -q
    # 65 passed

关键向量验收证据：

- 身份算法：contract-vectors.json 四个 identity_cases 与四个 invalid_identity_cases 全部通过（tests/contracts/test_audit_plus.py）；编码口径锁定 ensure_ascii=False / separators=(",", ":") / allow_nan=False。
- 跨进程合并：multi_process_merge 向量（四进程不同 attempt + 重启第五视角）→ 1 个 hand_id、5 个 view、1 个 split_group_id、attempt_status=unknown。
- 真实分块样本：三个 archived-rooms 夹具按向量值逐项验收（块数、seq 范围、事件数、首块起手 14/13/13/13、后续块 [null×4] 不重复起点、coverage=full_history、wall=null、draw_identity_known=false）；夹具 SHA-256 与向量一致。
- S1（codec 构造失败持久化）：producer_failure 带九个关联键与脱敏错误、producer_summary 计数、合并汇总 missing_high_priority=1 且 audit_degraded=true；验证器跨目录读取报告 producer_failure_records=1 且 audit_complete=false。
- S2（发送前越截止重检）：INTENT 审计推进假时钟越过 latest_send_at_monotonic → session.submit 调用为 0、outcome=SubmitNotSent(deadline_passed_after_audit)、原预算对象不变。
- codec-fails-before-emit 行为向量：monkeypatch codec 抛异常 → 保底提交仍发出、producer_failure 落盘、DECISION_ENDED 仍记录、effective_candidates 不丢失。
- unknown-replay-major 行为向量：hands.jsonl 的 replay_schema_version=99 → ValueError 且原文件字节不变；bundle_schema_version=2 同理拒绝。

## 4. 样例产物路径、SHA-256、来源与缺失

一次性样例（生成于临时目录，未入库；输入为三个真实归档房间夹具 + 一个合成决策运行）：

| 产物 | SHA-256（全长小写十六进制） |
| --- | --- |
| sample-bundle.tar.gz | 471146a3c3bbb77b80816c48c36ab44ec74200283ff5dadf567a726bebfa13dc |
| derived/0705b6c8.../manifest.json | 5b07ebbab25a9265fa0909278e26ee8e765492ee36d38b7692cac45e611ebeed |
| derived/0705b6c8.../index.jsonl | b5b0a8db717f02083c915c3df491b90ed61b807e6c6f6dad0eb7132091365e37 |
| derived/0705b6c8.../decisions.jsonl | d73d40f696ae5d7c964ea637f8f61fd0b43831e41b60387f024ad4ca1eaded90 |
| derived/0705b6c8.../hands.jsonl | 92f46e1a8c39616feb55af0215c21c7ad9b4bd558e9cbebf54669548471f8b4a |
| derived/0705b6c8.../validation.json | d9fcb2b9777975b44e21aad339e0987c840bd65abc36349a9e454fa2f4c9bd90 |

样例覆盖：3 个单局行（t_6c121bfda7e8/t_714a42392cba/t_cee1db65a074，来源指南 v14、2026-09-05 抓取）、1 条决策行（decision_complete=true）、1 条 index 行（3 official_refs）。缺失：wall（三样本均无未来牌墙）、draw_identity、合成决策运行不是真实比赛数据。

## 5. 需要主审集成的共享文件差异

1. bootstrap.py：RUN_MANIFEST 增强字段（source_namespace、git_commit/dirty、source_file_hashes、policy_version/weights）可由组合根经 ParticipantRuntime(source_namespace=..., manifest_extra=...) 注入；当前两个参数缺省 null，生产装配点未改动（bootstrap 由主审集成，见施工导航文件所有权）。
2. 官方既有发送路径打点：adapters/official/game.py 的 SUBMISSION_INTENT/OUTCOME 尚未补 capture_profile/audit_producer（官方层不落增强字段不影响应用层采集；适配器已有 POST 前 deadline 重检，S2 不变量在两层同时成立）。
3. adapters/recording/__init__.py 的 match_response 导出已随本线提交（C1 的一部分）；自由赛线应改用 hangma_bot.adapters.recording.build_match_response_payload。
4. application/contracts.py 的 AuditKind 区域由本线一次性更新（方案 §3.2）；AUTO_MATCH 区域属自由赛线并行改动，请主审合并时核对两个区域互不重叠。

## 6. 受控变更请求

无破坏性变更。兼容性说明：

- 信封 schema_version 与 raw payload_schema_version 保持 1；增强只新增可选 payload 字段（capture_profile/audit_producer）与三个新 AuditKind；旧目录按 legacy 读取，验证结论与升级前一致（回归锚点 test_legacy_run_without_profile_unchanged）。
- AuditTrail.aclose 现在会在关闭前发射一条 LIFECYCLE_CHANGED (area=audit, event=producer_summary)：消费最后一笔记录类型的既有断言需按 producer_summary 收尾更新（已同步本线两处既有测试）。
- 决策循环新增同步 codec 编码与发送前重检：不改变提交控制语义与预算复用；SubmitNotSent(deadline_passed_after_audit) 属于既有七类结果词表。

## 7. 轮次 2 返工（challenger 意见处理，key d3-5fb117）

两处审计证据完整性缺陷已最小修复：

1. 官方分块转换 event json_pointer 跨局文档错位：merge_round_events 曾用
   "按 round_no 过滤后重新排序的局部块下标"生成 /blocks/{i}/events/{j}，
   多局文档（rounds>1）中第二局的下标会错位指向第一局的块。修复：指针
   改用**原文档 blocks 数组下标**（按 (doc_index, block) 成对过滤排序）。
   回归：tests/offline/test_official_block_merge.py（3 例，含单局下标不回
   归断言与多局端到端 hands.jsonl 指针对齐）。
2. 官方下载损坏被静默丢弃：_official_downloads 曾对 source.json/events.json
   缺失、JSON 损坏、形态非法一律 continue 跳过——损坏的封存下载在数据集
   中凭空消失，history_coverage 无从报失败。修复：全部转为携带 error 的
   条目（incomplete_download / corrupt_source_json / corrupt_events_json /
   invalid_download_shape），由 build_hand_rows_and_index 记入
   history_issues → history_coverage 判 failed，不伪造空牌谱，运行侧决策
   行不受影响。回归：tests/offline/test_replay_dataset.py 新增 3 例
   （corrupt/incomplete/multi-round 端到端）。

修复后测试：offline 21 例全绿；全量套件重跑 1406+ passed（见下轮结果）。

## 8. 收尾清理（Challenger 复审轻微项 F3-F6，交付后顺手清理）

- F3：round_data 的 first_block 改为按最小 seq_start 取块（块乱序文档潜伏问题）；
- F4：_view_for_decision_input docstring 修正为实际返回（只返回 seat，可空）；
- F5：scripts/audit_tool.py 删除死变量 latest_wall_ms；collect-test-room 的
  source.json 与 games/events 一致走 .partial + 原子改名；
- F6：participant_runtime.py 五处 **_audit_plus_manifest_fields 缩进与后续键对齐（纯格式）。

回归结果（2026-09-05）：审计线相关测试 48 passed（tests/contracts/test_audit_plus.py +
tests/offline/ + tests/unit/application/test_audit_codec.py + test_decision_loop_audit_plus.py）；
全量 pytest 1416 passed。改动仅限本线可写路径，未触碰自由赛线文件。
