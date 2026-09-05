# 返工记录（d6-c3c77a / wv6）——Expert 必修项落实

> 任务：review-four-workstreams｜阶段：code-review｜轮次：3｜波：wv6
> 日期：2026-09-05
> 依据：Expert 裁决（accept 主体 + 1 major 行为缺陷 + 2 次级问题 + 文档失真清单）
> 验收证据：全套件 **1267 passed**（wv3 起始 1262 → +5 新增用例，零失败、零 skip）。

## 0. 修复总览

| Expert 项 | 处置 | 代码/文档落点 | 回归测试 |
| --- | --- | --- | --- |
| 必修 1：跨重建触发记忆缺弃牌者座位校验（major，key 碰撞→整窗零投递） | **修复**：projector._remembered_matches 增加 remembered[3] == snapshot.turn（响应阶段 turn 即弃牌者座位，v8 peng fixture 实证 turn=1 且 last_discard.seat=1）；跨座同码再弃 → 记忆不命中 → 降级 tier-4（快照 seq + trigger_projection_note 审计提示） | projector.py:_remembered_matches（docstring 含判据依据与残余声明） | test_sync_state.py：test_memory_rejected_when_other_seat_discards_same_tile（Expert 序列：seat1 弃 5w@101 → 重建清史 → seat0 弃 5w@130 → 断言 key 不碰撞、trigger=130、tier-4 提示）+ test_memory_still_hits_when_same_seat_discards_same_tile_after_rebuild（R2 主场景不误伤） |
| 必修 2：POST 在途取消零测试 + game/validator 字符串字面量耦合 | **修复**：共享常量 SUBMISSION_CANCELLED_IN_FLIGHT 落在 application/contracts.py（两模块既有依赖、无环），game.py 生产与 validator.py 例外消费统一引用 | contracts.py 新常量；game.py/validator.py 替换字面量 | 新文件 test_submit_cancel_inflight.py：① 挂起 POST → cancel → gate 封锁（同窗重提 SubmitNotSent ambiguous_window_blocked）、SUBMISSION_OUTCOME 以共享常量落审计、零 POST 原文记录；② 真实 sink 链 validate_run 不报 raw_action_missing、action_responses==0 |
| 必修 3：文档失真同步（notes 范围） | cursor-discipline.md：退避常量 (0.5,1.0,2.0)→(0.5,1.0)（wv3 P2-N4 封顶降级）+ pending+gap 分支描述改述（无退避睡眠，rebuild_loop 保护上交，与 F-15 复核结论一致）+ §7 测试清单更新（19 例/1262、退避序列 0.5/1.0/1.0/1.0、wv3 增补项）；rules-hu-gate-and-win-detection.md：§3 补记 policy/evaluation.py N-1 归一化改动（原"改动全部在 hangma 内部"失真）+ §4 计数（13 例/592）+ §6.1 双侧防御说明；audit-raw-retention.md：E4 符号修订（NotifyFrameProcessor 不存在→私有 _SseEventAccumulator + 不保留原文的配合改造说明，即 F-09）+ recording 计数 77→79；sse-notify-client.md：测试计数 48→56、官方适配器 215→268 | 四篇笔记 | 无（文档） |
| 非阻塞跟进（顺手落实） | rebuild_streak 在 pending+gap 有进度重建后清零（防间歇性进展的长边界累积误判 rebuild_loop）；_handle_conflict F-02 回退注释按"实际不可达（apply_full_snapshot 清史）+ 防御对称"如实改写 | game.py | test_pending_gap_progress_restores_incremental 扩展为两轮 pending+gap（第二轮若 streak 未清零即误判 GameFailed，测试红） |
| info 级顺手项 | F-18 意图锁定测试（drawn=None∧hand=None → 空且无 hu 族 Issue）；F-21 validator 三条严格 violation 附 raw_retention.dropped 后缀（接线缺失/背压丢弃可区分）；F-14 NotifyRunResult docstring 注明 error.raw_text 仅限审计落盘 | validator.py/_raw_dropped_suffix；notify.py docstring；test_action_families.py | F-18 用例；test_raw_validator gap 用例断言 dropped 后缀 |
| F-22（wv2 已改注释口径） | 复核确认 | decision_loop.py | — |

## 1. 残余与已知边界（如实声明）

- **同座同码再弃 + 清史重建**（同一弃牌者两轮弃同码、期间发生 409/gap 清史且新弃牌未经事件流可见）：
  纯牌码 last_discard 形态下与"pass 推进水位的同一弃牌"在快照层面信息不可分（官方未提供结构化
  序号；牌河计数判据存在写时 ±1 口径歧义、误杀会把安全方向翻转为双投）。本修复的座位校验
  已消除跨座碰撞（最常见形态）；同座残余方向保守（窗口抑制=欠交付，官方超时自动过兜底，
  绝不双投/重复行动），概率远低于跨座；彻底消除依赖官方 last_discard 携带序号或 SSE 接入。
  已在 projector._remembered_matches docstring 与本节登记。
- **F-12（state_polled 证据键）**：维持 open——需词表扩展并影响既有"精确 kinds 序列"断言与审计
  体积，建议并入审计词表变更评审（wv3 结论不变）。
- **validator request_no 会话分段检查 / monitor_run.py 纳入 raw/ / notify 帧长上限前移读取侧**：
  Expert 非阻塞跟进；monitor_run.py 在 scripts/（本派单可写范围外）。维持 open。
- **architecture.md 依赖边 / UBIQUITOUS_LANGUAGE 词条**（doc 根，本派单可写范围外）——建议补丁文本见下：

architecture.md：模块依赖段 adapters/recording 行补上游边：
  adapters/official → adapters/recording（RAW_PROTOCOL_STATE 原始事件经
  build_state_response_payload/build_action_response_payload 落 audit；
  errors.raw_text 载体语义见 interface-contracts §7.1）。序列图/树图同步。

UBIQUITOUS_LANGUAGE.md 新增词条（建议）：
| **游标纪律（Cursor Discipline）** | /state 轮询的 seq 参数语义="N 之后的事件"；本地游标永远是"已消费 seq"，全量快照的 seq 是包含式水位；取消/重连/POST 不回退游标。 | 轮询水位、增量同步 |
| **原始事件全量保留（Raw Event Retention）** | adapter 层收发原文（/state 响应、动作提交响应含 409/429 拒绝体）以 RAW_PROTOCOL_STATE 落按场 raw/ 文件，供赛后离线复盘与验证器对账。 | 审计存证、协议原文 |

## 2. 复核声明

- 必修 1 修复前先复现机制（代码核读 + fixture turn 语义实证），修复只收紧第三级记忆采用条件，
  不触碰四级解析骨架；两个新测试分别锁"跨座拒绝"与"同座不误伤"。
- 必修 2 常量放在两模块既有共同依赖（application.contracts），game.py/validator.py 引用同一定义；
  取消行为测试覆盖 Expert 点名的全部四个断言（封锁/审计 shape/无 raw/validate_run 不误报）。
- 全套件 1267 通过、零 skip；冻结契约五签名零改动；本轮未改任何可写范围外文件。