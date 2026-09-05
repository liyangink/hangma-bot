# 审计增强：adapter 层原始事件全量保留 + 决策观察快照

> 状态：交付笔记（任务 4/4）  
> 日期：2026-09-05  
> 事实基础：2026-09-04 官方测试赛 t_dee58824c308（M=10、Rounds=16、160 局打满）
> 完整审计 runs/runs/run-29a71a10ad12441eb15e0ac4cfb55c1d/（70,720 条、53MB、dropped=0）
> 官方依据：指南/API v8 快照（doc/official-platform-api-v2.md，抓取 2026-09-03）；
> v10 跨局 gap=true、v12 SSE 帧协议、v14 指南全文（doc/references/）

## 1. 结论（先读这段）

1. **原始事件全量保留**：RAW_PROTOCOL_STATE 不再只是“冗余快照”——它现在承载
   adapter 层收发原文（/state 响应、动作提交响应含 409 拒绝体、SSE 帧预留接缝），
   路由到独立 participants/{pid}/raw/{game}.jsonl，可选 gzip 分轮转（只分段不丢弃）。
   设计上无抽样、无体积裁剪；唯一丢失路径是记录器既有的有界队列背压
   （低优先级计数丢弃 + audit_degraded 可见，见 §3.4 的取舍说明）。
2. **决策观察快照**：DECISION_PLANNED 增加 observation_snapshot（my_hand 官方
   原始顺序、drawn_tile、phase、responding 上下文、目标弃牌 seat+tile+seq、
   规则状态与本人副露）与完整候选动作列表（kernel 稳定序列化）。
   2026-09-04 测试赛 97 次胡牌被拒无法本地复盘的问题从此闭环。
3. **验证器增强**：识别新字段与新记录类型（含 .jsonl.gz 段透明解压），
   脱敏扫描覆盖新增记录；新增完整性检查（状态请求原文缺口、场次原文流缺失、
   已发 POST 缺响应原文），由 summary.json 的 raw_retention 声明门控
   （auto-evidence：记录器收到过新形态原始事件才声明）——
   **旧目录结论与升级前完全一致**（真实 run 目录回归通过，见 §7）。
4. **非阻塞规模证据**：百万级记录模拟 54.8s 完成、审计恒等式成立（§6）。
5. 本任务**不改 adapters/official 代码**；逐文件埋点见 §8 接线清单，由主会话统一集成。

## 2. 背景与痛点

- 2026-09-04 测试赛审计只有“我们做了什么”：16,926 条 AUTHORITATIVE_STATE、
  10,549 条 DECISION_PLANNED、9,735 次动作尝试——但没有任何一条官方协议原文，
  也没有决策时的手牌。
- 已知痛点：decision_planned 未记手牌，97 次胡牌被拒无法本地复盘
  （只能靠外部牌谱对照）。
- 冻结契约约束：RAW_PROTOCOL_STATE 是唯一低优先级种类（接口协议 §7），
  本任务“基于它扩展，不另起炉灶”——因此原始事件沿用该种类，用 payload
  子结构（payload_schema_version + source 词表）区分来源，**不改契约签名**。

## 3. 原始事件全量保留设计

### 3.1 payload 词表（recording/raw_events.py）

所有原始事件都是 RAW_PROTOCOL_STATE 记录，payload 公共字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| payload_schema_version | int | 子结构版本（当前 1），与信封 schema_version 解耦，见 §5 |
| source | str | state_response / action_submit_response / sse_frame（封闭词表 RAW_EVENT_SOURCES） |
| endpoint | str | 官方端点原样（如 GET /api/games/{gid}/state） |
| http_status | int 或缺失 | SSE 帧与“响应未到达”时无此字段 |
| raw | str | **协议原文**（Token 已由传输层精确替换；记录器再做第二道防御性脱敏） |

来源特有字段：

- state_response：seq_requested（0=全量快照，API §2.3）、seq_observed（响应顶层权威
  水位，pending/错误体可缺）、request_no（**本场次内** state 请求单调计数，从 1 起）；
- action_submit_response：decision_id + attempt_no（与 intent/outcome 同键）；
- sse_frame：seq（水位）、closed（场终标记）；帧只含 seq（指南 v12，API §2.3）。

### 3.2 路由：按 kind/按场分文件

```
runs/{run_id}/participants/{pid}/
  decisions.jsonl          # 决策与提交流（不变）
  games/{game_id}.jsonl    # 场内关键事实（不变）
  raw/{game_id}.jsonl      # 原始事件（新增，RAW_PROTOCOL_STATE 专属）
  raw/global.jsonl         # 无场次原始事件回退（新增）
```

为什么单独分文件：原始事件全量保留后体量最大（每场万级记录、增长最快），
与关键事实流分离才能按场 gzip 轮转、按需备份/清理而不动审计主干。
路由变更只影响新记录；旧目录（原始事件散在 games/ 或不存在）仍被验证器
整体递归扫描，向后兼容。路由实现：schema.relative_path_for。

### 3.3 gzip 轮转（可选，默认关闭）

JsonlAuditSink(..., raw_gzip=True, raw_rotate_bytes=32MB) 开启后，原始事件按
raw/{game}.NNNNN.jsonl.gz 分段（五位数补零、字典序），单段超过上限只开新段，
**轮转是分段而非丢弃**。验证器按 .jsonl.gz 后缀透明解压扫描；损坏段报
unreadable_audit_file violation 而不是崩溃。默认关闭的理由：普通盘位无需
压缩、保持可读；长期运行建议开启（体量测算见 §4）。

### 3.4 优先级与“不丢弃”的取舍（明确声明）

- 冻结契约（接口协议 §7、recording 模块规范）：RAW_PROTOCOL_STATE 是唯一
  低优先级种类，“队列满时优先移除低优先级记录”、“不要为 100% 不丢阻塞 1 秒
  动作窗口”。本任务**不推翻该契约**——原始事件保持低优先级。
- “不允许因体积丢弃”的落实：记录器**没有**抽样、截断、按体积淘汰任何代码路径；
  原始事件不设大小上限（raw 多长都整条落盘）。唯一丢失路径是既有的有界队列
  背压（磁盘长时间跟不上时逐条淘汰最旧低优先级记录），每次淘汰进入
  dropped_low_priority 计数并在 summary.json 可见；高优先级记录缺失照旧
  置 audit_degraded=true（高优先级缺失语义保持）。
- 为了把背压丢弃压到极端场景，默认队列从 4096 提升到 16384（约 16MB 驻留上限）；
  队列尺寸仍是构造参数，主会话可按盘速调大（规模测试证明 2 万条突发零丢弃，
  见 §6）。
- 若未来要求“任何情况下 0 丢弃”，只能选择阻塞动作路径（违反 1s/3s 窗口纪律）
  或无限队列（磁盘悬挂时内存无界），两者都被 AGENTS 红线排除——此取舍留给
  总体评审裁决，本任务保持“诚实计数”。

### 3.5 脱敏（沿用现有机制，两层防线）

1. 第一层（生产方）：OfficialTransport.request 对响应体做 token → “***”
   精确替换后才返回 result.text；接线清单要求所有 raw 字段都取自该文本；
2. 第二层（记录器）：入队前 redact_value + redact_json_line 做敏感键与
   凭证形态扫描（Bearer/JWT/key=value），验证器离线再扫一遍（_walk_secrets
   递归覆盖新增记录类型）。新增测试证明写入侧替换后落盘文本不含原文、
   绕过写入侧的旧记录会被验证器拦截（tests/adapters/recording/test_raw_validator.py）。

## 4. 体量测算（对照今晚基线外推）

基线事实（run-29a71a10ad12441eb15e0ac4cfb55c1d）：

| 项 | 数值 |
| --- | --- |
| 总记录 | 70,720 条 / 53MB（约 750B/条） |
| decisions.jsonl | 50,680 行 / 36MB |
| games/*.jsonl | 约 19,000 行 / 16MB |
| 动作尝试 | 9,735 次（2,682 次被明确拒绝） |
| DECISION_PLANNED | 10,549 条 |

原始响应体积（实测 fixture，tests/fixtures/official/v8/）：全量快照 1.1–1.5KB、
增量事件 0.5KB、pending 0.25KB、终局 0.8KB；实测 gzip：快照约 2–3×、
100 条事件批量约 9.4×、混合约 2× 起。

全量保留外推（每参赛身份、一场完整测试赛）：

| 数据流 | 条数估计 | 未压缩 | gzip 后 |
| --- | --- | --- | --- |
| /state 响应原文 | 30k–45k（≥2×9,735 窗口投递 + 边界定时刷新 + 2,682 次 409 刷新 + 重建） | 21–32MB | 5–8MB |
| 动作提交响应原文 | 9,735（含 409/429 拒绝体） | 约 1.2MB | 约 0.6MB |
| SSE 帧（预留，未采纳） | 0 | 0 | 0 |
| 决策观察快照（decision_planned 增量） | 10,549 × 约 600B | 约 6MB | 不单独压缩 |
| **合计增量** | — | **约 +28–39MB** | **约 +11–14MB** |
| 相对基线 53MB | — | +53%–74% | +21%–26% |

结论：全量保留把单身份运行目录从 53MB 推到 81–92MB（未压缩）或 64–67MB
（raw 开 gzip）；**无 gzip 也完全可接受**，gzip 是给长期/多赛事运营的选项。
判断依据是估算，接入后首次真实运行用 validator 的 raw_events.raw_bytes_total
复核即可。

## 5. schema_version 升级策略与旧目录向后兼容

- **信封 schema_version 保持 1**：新增字段全部是可选/增量（旧读取器忽略），
  升信封版本会让 AuditTrail 与 official/game.py 硬编码的 1 全部被拒——属于
  破坏性变更，不需要也不允许。
- **子结构自带版本**：原始事件 payload 带 payload_schema_version=1
  （RAW_PAYLOAD_SCHEMA_VERSION）。未来收紧（如新增必填字段）时递增该常量，
  验证器对新版本按已知结构尽力统计 + warning（unknown_raw_payload_schema），
  不拒绝记录；PAYLOAD_SCHEMA_VERSIONS 登记表保持全 1 直到真正收紧。
- **严格检查门控（auto-evidence）**：验证器的缺口/流缺失/动作响应检查只在
  运行级 summary.json 声明 raw_retention 时启用。声明条件是记录器**收到过
  新形态原始事件**（适配器已接线）或显式开启 raw_gzip——旧目录与"适配器
  尚未接线"的过渡期运行不声明，严格检查整体跳过、不产生误报；接线不完整
  （部分场/部分来源缺原文）会被 gap/stream_empty/action_missing 揪出。
  真实回归：对 run-29a71a10ad12441eb15e0ac4cfb55c1d 跑新验证器，结论与升级前逐字段一致
  （violation_count=0、audit_complete=true、ok=true、secret_scan_clean=true、
  14 文件 70,719 行，raw_events.retention_mode=legacy）；回归锚点测试
  tests/adapters/recording/test_baseline_regression.py 锁定该结论。
- **决策观察快照版本**：observation_snapshot.schema_version 与候选
  action.schema_version 复用 kernel 线格式版本（KERNEL_VALUE_SCHEMA_VERSION=1），
  由 kernel 序列化模块统一演进，不在本任务内另立版本。

## 6. 非阻塞规模证据（百万级模拟）

tests/adapters/recording/test_raw_retention.py：

- test_raw_stream_is_nonblocking_at_scale：紧循环发射（人为远超生产速率），
  断言 emit 单条最坏延迟 < 50ms、审计恒等式 written + dropped == 发射数
  成立、低优先级丢弃绝不伪装成降级。默认 6 万条；环境变量
  RECORDING_RAW_SCALE_ITEMS 放大。**实测 1,000,000 条（约 600MB 原文）
  54.8s 通过**——写线程独立推进，动作路径零阻塞。
- test_raw_retention_zero_drop_when_queue_provisioned：2 万条突发在队列按
  规模配置后零丢弃——证明没有“因体积丢弃”的设计路径。
- test_raw_stream_does_not_block_emit_while_writer_stuck：写线程全程阻塞在
  故障注入观察点时，2 万条 emit 秒级完成——非阻塞由架构保证。
- 既有的队列压力/淘汰/关闭超时测试保持全绿（高优先级缺失语义不变）。

## 7. 验证器增强清单（validator.py）

| 检查 | severity | 门控 | 说明 |
| --- | --- | --- | --- |
| .jsonl.gz 透明扫描 | — | 无 | gzip 轮转段与普通 jsonl 同权；损坏段报 unreadable_audit_file |
| 原始事件统计 | — | 无 | raw_events.by_source/by_endpoint/by_http_status/raw_bytes_total/records_legacy |
| 脱敏扫描 | violation | 无 | _walk_secrets 递归覆盖新增记录类型（含 raw 原文） |
| raw_state_stream_empty | violation | summary 声明 raw_retention（auto-evidence） | 有场次层 AUTHORITATIVE_STATE 证据的 (pid, game) 必须有 state_response 原文流 |
| raw_state_gap | violation | 同上 | 同场 request_no 取值集合必须连续（缺中间值 = 该次响应原文丢失）；会话重启从 1 重新计数不会误报（两次 1..N 并集连续） |
| raw_action_missing | violation | 同上 | 每个实际发出的 POST（adapter 层 outcome_type != SubmitNotSent）必须有 action_submit_response 原文；在途取消（submit_cancelled_in_flight）与未发送例外 |
| malformed_raw_request_no | warning | 无 | request_no 缺失或非整数时不参与连续性检查 |
| unknown_raw_payload_schema | warning | 无 | 子结构版本超前时按已知结构尽力检查 |

## 8. 接线清单（主会话按单集成；本任务不改 adapters/official）

记录接口签名（hangma_bot.adapters.recording 公开面）：

```python
from hangma_bot.adapters.recording import (
    build_state_response_payload,   # endpoint/http_status/seq_requested/seq_observed/request_no/raw
    build_action_response_payload,  # endpoint/http_status(可 None)/decision_id/attempt_no/raw
    build_sse_frame_payload,        # endpoint/seq/closed/raw（预留）
)
```

### E1. official/game.py — OfficialGameSession._get_state()：/state 响应原文

- 插入点：result = await self._transport.request("GET", ...) 之后、
  return parse_state_response(_loads(result.text)) 之前（对照时点 2026-09-05：
  game.py:668 行；以函数名 _get_state 为准，行号随并行工作线漂移）。
- 改动（函数级描述）：
  1. __init__ 增加 self._state_request_no = 0；
  2. 每次 transport 成功后：self._state_request_no += 1，先解析出
     parsed = parse_state_response(_loads(result.text)) 取 seq_observed
     （parsed.snapshot.seq，pending/events 无快照时为 None），再发射：
- 调用样例：

```python
self._state_request_no += 1
request_no = self._state_request_no
parsed = parse_state_response(_loads(result.text))
self._emit_audit(
    AuditKind.RAW_PROTOCOL_STATE,
    build_state_response_payload(
        endpoint="GET /api/games/{}/state".format(self.game_id),
        http_status=result.status,
        seq_requested=seq,
        seq_observed=parsed.snapshot.seq if parsed.snapshot else None,
        request_no=request_no,
        raw=result.text,  # transport 已做 token→"***" 精确替换
    ),
    trigger_seq=parsed.snapshot.seq if parsed.snapshot else None,
    round_no=parsed.snapshot.round_no if parsed.snapshot else None,
)
return parsed
```

- 语义：重试循环内每次 HTTP 成功恰好一条（重试只发生在异常路径）；raw
  是未经解析的原文，坏报文照样落盘供赛后诊断。request_no 供验证器做
  缺口对账（跨会话重启归零安全，见 §7）。

### E2. official/errors.py + transport.py — 错误响应原文携带（前置改动）

- 现状：非 2xx 响应原文在 transport 抛异常时只留下 sanitize(text) 的 detail，
  409/429 拒绝体原文丢失。需要在异常族里携带已脱敏原文：
  - errors.OfficialError.__init__ 增加关键字参数 raw_text: Optional[str] = None
    （向后兼容：旧调用不传即 None）；
  - transport.OfficialTransport.request 每个 raise XxxError(...) 处追加
    raw_text=text（text 已完成 token 替换）。UncertainTransportError
    （超时/断连）没有响应体，不传。

### E3. official/game.py — OfficialGameSession._submit_locked()：动作提交响应原文

- 插入点：await self._transport.request("POST", "/api/games/{}/action".format(...), json_body=body)
  改为 result = await self._transport.request(...)（对照时点 2026-09-05：
  game.py:774 行；以函数名 _submit_locked 为准，行号随并行工作线漂移），
  成功路径在 self._gate.mark_accepted(...) 前发射。
- 成功 2xx 样例：

```python
result = await self._transport.request("POST", "/api/games/{}/action".format(self.game_id), json_body=body)
self._emit_audit(
    AuditKind.RAW_PROTOCOL_STATE,
    build_action_response_payload(
        endpoint="POST /api/games/{}/action".format(self.game_id),
        http_status=result.status,
        decision_id=attempt.decision_id,
        attempt_no=attempt.attempt_no,
        raw=result.text,
    ),
    decision_id=attempt.decision_id,
    attempt_no=attempt.attempt_no,
    trigger_seq=attempt.window_key.trigger_seq,
    round_no=attempt.window_key.round_no,
)
```

- 非 2xx 各 except 分支（ConflictError 409、RateLimitedError 429、
  AuthError 401、ForbiddenError 403、BadRequestError 400、NotFoundError 404、
  RecoverableServerError 5xx）：从异常取 exc.raw_text，同一
  build_action_response_payload 发射（409 拒绝体完整保留；409 分支注意在
  lease.release() 之前发射，与 E1 一样绝不阻塞动作路径）。
- except UncertainTransportError（POST 已发出、响应未到达）：发射一条
  http_status=None, raw="" 的记录，证明“该次尝试的响应原文不存在”，
  对账不悬空（验证器按 outcome_type=SubmitAmbiguous 要求该键存在）；
- except asyncio.CancelledError（submit_cancelled_in_flight）：不发射
  （POST 是否发出未知、无响应可录），验证器已按例外排除；
- SubmitNotSent 各路径没有 POST，不发射。
- 对账关系：每条 adapter 层 SUBMISSION_OUTCOME（outcome_type != SubmitNotSent，
  取消例外）必须有同键 action_submit_response 原文，否则验证器报
  raw_action_missing。

### E4. SSE 预留接缝（另一工作线的 notify 客户端，本次不接线）

- 记录接缝已就绪：build_sse_frame_payload(endpoint="GET /api/games/{gid}/notify",
  seq=<帧水位>, closed=<场终标记>, raw=<帧原文>)；帧协议只含 seq（指南 v12/14，
  API §2.3：初始帧 {"seq": N}、变化帧、{"seq":N,"closed":true} 场终、: keepalive）。
- 对接现实现（本任务不拥有、只读对照；**wv6 修订**：notify.py 中不存在
  名为 NotifyFrameProcessor 的符号——实际为私有 _SseEventAccumulator
  （notify.py:111-152，feed 在约 :122，data 行解析在约 :133-138），且
  累加器不保留原始行文本（只留存 data 载荷、注释/空行丢弃）：接线时需先
  在累加器回传 data 原文（或直接在 _deliver_frame 传 raw 空串降级），
  本文档此前引用的符号与"持有原始行文本"的假设均不成立。若选择在
  _deliver_frame（约 notify.py:663）接入则只有 seq/closed、raw 传空串。
  注意 notify.py 现有 docstring 声明"绝不携带 SSE 原始行文本"——接线时
  该约束须修订为"原文只进审计、不进异常与日志"。
- 记录时 game_id 传所在场；验证器按 source 统计、不要求帧完整性（SSE 是
  可选能力，未采纳时不产生记录不算缺失）。

### E5. 组合根（bootstrap.py，主会话）— 记录器构造

```python
sink = JsonlAuditSink(
    audit_root,
    run_id,
    raw_gzip=config.audit_raw_gzip,               # 建议先 False，盘位紧张再开
    raw_rotate_bytes=config.audit_raw_rotate_bytes,  # 默认 32MB
)
```

### 不在本次接线范围（明确声明）

- participant.py 赛事端点（/api/me、tournament detail、register/ready）原文：
  要求只列了 /state 与动作提交；如要覆盖，需先扩充 source 词表
  （如 tournament_response）并同步 raw_events/验证器/本文档——建议与 SSE
  接入一并决策，本次不做。
- architecture.md / interface-contracts.md §7.1 词表登记：本任务不拥有这两个
  文件，由主会话统一集成时登记（本次新增字段全部可选、不破坏既有词表）。

## 9. 决策观察快照（decision_loop.py）

DECISION_PLANNED 的 payload 新增（2026-09-04 增强，均为可选增量字段）：

- observation_snapshot（_observation_snapshot 构造）：schema_version（kernel
  线格式版本）、game_id/seat/round_no/snapshot_seq/phase/turn_seat、
  responding_seats、responding（window_key.seat ∈ responding_seats）、
  my_hand（**官方原始顺序**，kernel 契约：紧急“最右一张”依赖该顺序）、
  drawn_tile（单列，不并入手牌——2026-09-04 kernel 裁决）、
  target_discard{seat,tile,seq}（触发本窗口的弃牌，吃/碰归属复盘必需）、
  my_melds（仅本人副露行）、hand_counts、remaining_tile_count、scores、
  rule_state{wealth_god,baotou,chain_count,catch_play}（胡牌合法性复算输入）。
- candidates 每项从 {action_key, is_emergency} 扩为
  {action_key, is_emergency, rank, action（kernel action_to_json 稳定序列化）, reasons}——
  赛后可用 action_from_json 无损还原并复算规则合法性。
- 信息权限：全部来自 PlayerObservation 口径，不含他家手牌/牌河/事件史/
  未来牌墙；完整原始快照另由 RAW_PROTOCOL_STATE state_response 原文全量保留，
  快照刻意不含公开牌河与事件史以控制体积（每条约 600B，全赛约 +6MB）。
- participant_runtime.py **无需改动**（快照所需事实全部在决策循环内）。

## 10. 测试与验收结果

- tests/adapters/recording/：79 项全过（wv3 增补截断 gzip 回归后；新增 test_raw_events、test_raw_retention、
  test_raw_validator、test_decision_snapshot、test_baseline_regression；
  更新 test_schema/test_jsonl_sink/test_validator/test_integration_wiring/
  test_validator_assembly_rulings 到接线后现实形态）。
- tests/unit/application + tests/adapters：401 项全过（decision_loop 快照为
  纯增量字段，既有断言不受影响）。
- 真实 run 目录回归：新验证器结论与升级前一致（§5/§7）。
- 百万级模拟：1,000,000 条 54.8s、恒等式成立、emit 延迟有界（§6）。

## 11. 遗留风险与待办

1. **背压丢原始事件的取舍**（§3.4）：低优先级计数丢弃是冻结契约，极端磁盘
   悬挂下原始事件会丢（有计数、可复核）；“绝对零丢弃”需总体评审改契约。
2. **request_no 跨会话重启**：重新计数从 1 起，两次 1..N 并集连续不会误报；
   但“整段会话的原始事件全部丢失”（如整场断链）只能靠
   raw_state_stream_empty + dropped 计数兜底，无法区分丢的是哪一段。
3. **接线后首次真实运行的体量**：§4 是估算；用 raw_events.raw_bytes_total
   与 dropped_low_priority 复核，必要时开 gzip 或调大 max_queue。
4. **赛事端点原文**（E5 备注）与 **SSE** 不在本次范围；SSE 接缝已预留。
5. architecture.md / interface-contracts.md §7.1 的登记与官方适配器接线由
   主会话统一完成。auto-evidence 门控保证接线完成前的新运行不误报
   （无新形态原始事件 → legacy）；接线**不完整**（漏了某个 emit 点）会
   被 gap/stream_empty/action_missing 在首次真实运行中揪出——集成完成后
   跑一次真实运行并复看 validator 的 raw_events 报告即可确认转绿。
