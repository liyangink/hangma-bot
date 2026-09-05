# 返工记录（d3-e30211 / wv3）——wv1 意见修复清单

> 任务：review-four-workstreams｜阶段：code-review｜轮次：2｜波：wv3
> 日期：2026-09-05
> 依据：Challenger rework 意见（W2-1 / F-01 / F-10 / P2-N1 / N-1 / N-2 / F-02 / F-15 /
> P3-01 / W2-3 / F-13 / P2-N3 / P2-N4 / F-05 / F-16 / F-08 / F-11 及 nit 群）
> 验收证据：全套件 **1262 passed**（本轮起始 1219 → +43 新增用例，零失败）。

## 0. 修复总览

| Challenger 项 | 定级 | 处置 | 代码落点 | 回归测试 |
| --- | --- | --- | --- | --- |
| W2-1 非有限 Retry-After 冻结 Token | blocker | **修复（双层）** | transport.py:212-226（isfinite+非负解析）；scheduler.py:199-206（note_rate_limited isfinite 防御） | test_transport.py 参数化 5 形态（1e999/nan/-3/2.5/非法）；test_scheduler.py::test_non_finite_retry_after_never_freezes_token |
| F-01 Token 落盘防线无测试 + 二层盲区 | blocker | **修复（3 件套）** | redact.py：_BEARER_RE 扩冒号形态、新增 _LONG_SECRET_RE（写侧与离线扫描同源，validator 复用）；测试补传输级 raw_text 断言与真实链路 | test_transport.py::TestRawTextSanitization（4 形态参数化 + 429）；test_raw_wiring.py::TestRealChainToDisk（真实 OfficialTransport→真实 session→真实 JsonlAuditSink→磁盘扫描 + validate_run 双断言） |
| F-10 截断 gzip EOFError 崩溃 | risk | **修复** | validator.py:240-246 → except (OSError, EOFError)（实证 EOFError ∉ OSError） | test_raw_retention.py::test_truncated_gzip_tail_reported_not_crash |
| P2-N1 归一化异常静默回到幻影口径 | risk | **修复** | engine.py：新增 _concealed_missing_drawn_instance，analyze 产 RuleIssue（engine.context / DEGRADED） | test_hu_gate_and_double_count.py::TestNormalizationAnomaly（4 例：异常/官方正常/契约正常/无 drawn） |
| N-1 policy 评分上下文双计 | risk | **修复（复刻引擎口径）** | policy/evaluation.py：build_context 改走 _hand_codes_without_double_count（14−3×副露数长度判据） | tests/unit/policy/test_evaluation_context_normalization.py（新文件 5 例：契约/官方/带副露/无 drawn 同构） |
| N-2 增量观察 hand_counts/墙余不自洽 | risk | **修复** | sync_state.py::incremental_draw_observation：base 无 drawn 时本人手数 +1、墙余 −1（防御：base 已是摸牌形态则不变） | test_sync_state.py 新增 2 例（含防御分支） |
| F-02 增量窗口 409 身份恒等无回归 | risk | **修复（对称分支 + 双变体回归）** | game.py::_handle_conflict：快照路径不匹配时补增量窗口回退（与 _submit_locked 同构） | test_cursor_discipline.py：seq==draw seq → Retryable；窗口迁移 → Closed（且同窗零追加） |
| F-15 pending+gap 退避分支 | risk | **修复（语义裁定 + 测试锁定）** | game.py：pending+gap 分支删除不可达的退避睡眠（连续无进度由 rebuild_streak>2 保护性上交），注释说明与 snapshot-gap 分支的分工 | test_cursor_discipline.py：3 连发 pending+gap → GameFailed(recoverable, rebuild_loop) 零睡眠；进度变体恢复增量 |
| P3-01 exactly-once 双路径 | risk | **修复（测试锁定）** | 无需改码（机制已正确） | test_cursor_discipline.py::test_delivered_window_never_delivered_twice_across_paths（增量投递后同窗快照重送不二投、零重建） |
| W2-3 毒化帧 RecursionError/超长行 | risk | **修复** | notify.py：_MAX_FRAME_DATA_BYTES=64KB 上限；parse 捕 RecursionError → DtoError(recoverable) | test_notify.py::TestPoisonFrame（超长/深嵌套单元 + run 级重连） |
| F-13 notify 矩阵缺行 | risk | **修复（补齐五行）** | 无需改码 | test_notify.py：5xx 重连、退避封顶 2.0 序列、流中途读超时（fail_with=httpx.ReadTimeout）、观察者异常只计数、预算等待超时 → BUDGET_UNAVAILABLE |
| P2-N3 已学习未知事件不刷新 | risk | **修复** | sync_state.py::events_need_authoritative_refresh：learned_event_types 命中一律 True（保守刷新，非重建） | test_sync_state.py::test_learned_unknown_event_type_requires_authoritative_refresh |
| P2-N4 边界退避封顶侵蚀窗口 | risk | **修复（封顶降 1.0s）** | game.py：_BOUNDARY_STALL_BACKOFF_SEC=(0.5, 1.0)（注释记录发现时延论证；SSE 唤醒待接入） | test_cursor_discipline.py 既有用例更新为 (0.5,1.0,1.0,1.0)=3.5s 精确断言 |
| F-05 E1 宽口径 vs 实现 | risk | **修复（补发射，代码对齐文档宽口径）** | game.py：_get_state 各非 2xx except 分支补 _emit_raw_state_error（http_status/原文/request_no 不递增） | test_raw_wiring.py::test_failed_state_response_body_is_recorded（429 拒绝体落审计 + 计数语义） |
| F-16 差分重放下界过低 | risk | **修复（下界对齐实测）** | 无 | test_hu_differential_replay.py：checked_draws≥120（实测≈180）、meld_windows≥4（实测 4） |
| F-08 E5 gzip 配置不可达 | risk | **修复（全链透传）** | bootstrap.py：RuntimeConfig + audit_raw_gzip/audit_raw_rotate_bytes（校验/repr/_CONFIG_FIELDS/mapping 解析）+ build_runtime 透传 JsonlAuditSink | tests/integration/test_bootstrap_assembly.py：配置解析 4 例 + 组合根落盘行为 2 例（gz 段 vs 普通 jsonl） |
| nit 顺手项 | — | F-17 删私有断言行；F-23 删 _apply_snapshot 死代码并把 observe_authoritative_window 接入 _apply_or_fail；F-18 门禁早退注释；F-22 target_discard 注释改口径；N-4 errors 模块 docstring 补 raw_text 例外 | 见各文件 | 全套件绿（action_gate 既有 observe 单测现在有真实调用方） |
| F-19 无单链端到端 | nit | **修复**（与 F-01 ②合并实现） | — | test_raw_wiring.py::TestRealChainToDisk 即真实 adapter→sink→磁盘→validator 单链 |

## 1. 维持 open / 需主会话处理（可写范围外或需官方样本）

- **F-03（杠窗口官方样本）**：机制经 wv1 §3.1 物理张数裁定成立；本轮 P2-N1 为"长度命中但无同码实例"异常加了可审计标记（防御兜底）。仍需下次官方测试房抓取"自家杠后补牌窗口 /state"原文，并把 parity 金例扩到含杠副露（现 3 归档场 gang=0）。
- **F-11（interface-contracts.md §10.1 句与 projector/engine 落点矛盾）**：该文件不在本派单可写范围。建议主会话落笔（建议文本）：
  > §10.1 "内部统一语义：PlayerObservation.my_hand **不包含**单列的 drawn_tile……由适配器统一规范化" 改为：
  > "2026-09-05 起：官方快照实测形态（my_hand 含刚摸牌）与契约形态（不含）并存，适配器投影保留官方原样（紧急'最右一张'依赖官方顺序）；双计归一化由 hangma 引擎（engine._concealed_without_drawn，长度判据 14−3×副露数）与 policy 评分上下文（evaluation._hand_codes_without_double_count）按同口径防御性执行；适配器侧统一规范化列为后续工作线（rules-hu-gate-and-win-detection.md §6.1）。"
- **F-20（recording.md / official-adapter.md 模块文档过时）**：doc/implementation/modules/** 不在可写范围，需主会话同步（recording.md RAW 语义段、official-adapter.md 的 E1-E3/增量窗口/退避节）。
- **F-08/F-09 的笔记文本（doc/implementation/notes/** 不可写）**：代码已按 E5/E4 语义实现或就绪；笔记行文（bootstrap 示例已过时 / E4 符号 NotifyFrameProcessor→_SseEventAccumulator）建议由主会话或下一实现轮修订。
- **F-12（无窗场 raw_state_stream_empty 证据盲区）**：留 open——修复需在 game.py 每次 /state 成功首见 game 时发射场次层标记（payload 词表扩展），会影响既有"精确 kinds 序列"断言与审计体积，建议并入审计词表变更评审。
- **F-04 / F-06（notify 接入前项）**：F-06 根因已由 W2-1 在传输层消除；F-04（非 2xx 分支取消漏 aclose）仍 open，notify 未接入前无运行影响。
- **F-07 / F-09 / F-12 / F-14 / F-21 / W2-4 / W2-5 / P3-02..05 / N-3**：维持 open（低风险/需接入期或审计词表决策），明细见 wv1 报告 §2。
- **O-1..O-4**：维持 open（官方样本/接入期实测），验证方法见 wv1 报告 §4。

## 2. 复核声明

- 全部修复均先复现/理解 challenger 触发条件，再以最小改动落地；每个修复配套至少一条可独立失败的回归用例（反向验证：移除修复逻辑用例必红）。
- 关键裁决补充：F-15 复核发现 pending+gap 分支的退避睡眠在 rebuild_streak>2 保护下不可达（第 3 次 pending+gap 即上交），属"重复实现 + 死代码"，故删除而非补测；真实 v10 边界的无进度退避走 snapshot+gap 分支（封顶已降 1.0s，P2-N4）。该改动不改变任何对外行为（原分支睡眠本就不可达）。
- 全套件 1262 通过；1219 起始基线 → 无既有用例被改弱（唯一断言更新：P2-N4 封顶后精确时钟期望 3.5s，属修复语义的自然更新）。
- 本轮修改文件（均在可写范围）：src/hangma_bot/{adapters/official/{transport,scheduler,game,sync_state,notify,errors}.py, adapters/recording/{redact,validator}.py, bootstrap.py, hangma/{engine,action_families}.py, policy/evaluation.py, application/decision_loop.py}；tests/** 对应回归；本记录文件。
