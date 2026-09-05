# 四工作线交叉审查报告（S1–S4 + 主会话集成接线）

> 任务：review-four-workstreams｜阶段：code-review｜轮次：1｜波：wv1
> 日期：2026-09-05
> 审查形态：全视角·轻量（4 视角包并行独立 findings + challenger 组合评审汇总）
> 视角包：P1 缺陷与安全 / P2 逻辑推演 / P3 测试覆盖 / P4 影响范围（只读，互相不知晓）
> 审查对象（工作树当前实现，全套件 1218 例收集确认全绿）：
> S1 SSE notify 客户端（notify.py 新增）、S2 /state 游标纪律、S3 规则层修复（hu 门禁 + 防双计归一化）、
> S4 审计全量保留（raw_events/validator/jsonl_sink/schema/summary + decision_loop 观察快照）、
> 主会话集成接线（E1/E2/E3 + projector），对应测试与 doc/implementation/notes/* 四篇交付笔记。
> 不在范围：runs/ 运行产物；v14 指南同步产物（dto.py/KNOWN_GUIDE_VERSION/快照/脚本）除非被四线代码依赖。
> 基线事实：改动相对 HEAD 581eaf9 全部暂存未提交；冻结契约（WindowKey/ObservedActionWindow/
> TournamentSessionPort/GameSessionPort/BotPolicy/AuditSink 五签名）零改动（git diff 核实）；
> 官方依据：doc/references/official-guide-v14-content.txt（v14 全文，2026-09-05 抓取）与
> official-guide-version-v14.json（变更日志）；实测背景：2026-09-04 测试赛
> run-29a71a10ad12441eb15e0ac4cfb55c1d（3063 次重建、97 次 hu 409、836 次重复 pass）。

## 0. 汇总结论（先读这段）

**总评：四线 + 集成接线的实现质量高、与交付笔记高度一致，未发现 blocker 级缺陷；发现 1 条
major（测试缺口，红线护栏无端到端测试）、16 条 minor、6 条 nit（详见 §2）；另有 5 条待确认
风险（§4）。冻结契约零改动，向后兼容面（errors/TransportConfig/recording 信封）核实无损。**

| 线 | 结论 | 依据要点 | 主要发现 |
| --- | --- | --- | --- |
| S1 SSE notify 客户端 | 通过（保持未接线交付） | 生命周期状态机完整：预算槽全出口归还、分类/重连矩阵与错误体系一致、脱敏双层、取消穿透、时间全注入；与笔记"可用但不接入、零运行影响"声明一致（运行链路零引用已 grep 核实） | F-13 行为矩阵测试缺行（5xx/反向退避/封顶/静默读超时/观察者异常/预算等待超时）；F-06 Retry-After 非有限值悬挂；F-04 错误分支取消漏 aclose；F-14 nit |
| S2 /state 游标纪律 | 通过 | 游标=本地已消费 seq 不变量在增量消费/快照吸收/取消重连/POST 后/跨局边界全路径成立；增量直达摸牌窗口的"事件流末条=本人 tile_drawn"判定与触发制刷新集闭合性经事件序列推演成立；exactly-once（_delivered_windows + ActionGate）双路径无冲突；边界退避算术（2 次原速 + 0.5/1.0/2.0 封顶）与笔记一致 | F-02 增量窗口 409 身份隐含恒等缺回归测试；F-23 死代码 observe_authoritative_window 未接线（存量）；F-15 pending+gap 退避分支零测试；F-17 nit（私有状态断言） |
| S3 规则层修复 | 通过 | 门禁判据（drawn_tile 非空）与官方变更日志 v1/API §2.4 一致，杠上摸/庄家直抽放行口径正确；防双计归一化长度判据 14−3×副露数经 challenger 物理张数复核（含杠/补杠窗口，见 §4 裁定）数学成立；弃牌候选走 context.full_hand() 不受归一化影响；金例/归档重放/fan-calc 600 例证据链强 | F-03（证据真空：杠窗口无官方样本与金例，机制本身经裁定成立）；F-16 重放下限低 + 夹具缺失静默 skip；F-18 nit（门禁早退顺序未锁定） |
| S4 审计全量保留 | 通过 | RAW_PROTOCOL_STATE 路由/gzip 分段/auto-evidence 门控/优先级与"计数丢弃不伪装降级"语义与契约一致；百万级非阻塞证据真实（恒等式 + <50ms）；验证器三条严格检查与 E1/E3 发射点逐点对账（含取消例外）；旧目录 legacy 回归锚定 | F-01 major 测试缺口（E2 raw_text 无端到端脱敏测试 + 第二层盲区）；F-05 GET 非 2xx 原文不入审计；F-07 raw 单条无上限；F-08 E5 gzip 配置未接线；F-10 截断 gzip 段 EOFError 崩溃（已实证）；F-11 contracts §10.1 与归一化落点矛盾；F-12 无窗场证据盲区；F-19 无 adapter→sink→validator 单链测试；F-20 模块文档未同步；F-21/22 nit |
| 集成接线 E1/E2/E3/projector | 通过 | E1（game.py _get_state 每次 HTTP 成功发射原文含坏报文）、E2（errors.raw_text 携带已脱敏原文、构造点全兼容）、E3（_submit_locked 全部分支发射与验证器例外逐字吻合）接线完整且与接口契约登记一致；projector.py 改动为注释修订（9 行，无行为变化） | F-01/F-05/F-07/F-09（E4 预留接缝文档符号漂移） |

## 1. 方法与复核范围

- 视角包各自独立通读 4 篇交付笔记 → 对应源码全文 → 对应测试 → 交叉 grep 调用方；
  每条 finding 必须带 file:line 与代码原文证据；无法实证的只许记 [open]。
- Challenger（本报告）在四包结果之外独立重读了全部核心文件（notify.py 750 行、game.py 1103 行、
  sync_state.py、engine.py、action_families.py、raw_events.py、jsonl_sink.py、validator.py 新增段、
  decision_loop.py 改动段、transport/errors/projector 全 diff、关键测试），
  对每条合并 finding 做了代码级复核；对四包互相冲突或高风险主张做了独立裁决（§4）。
- 实证执行：pytest --collect-only 确认 1218 例；截断 gzip 异常类型实测；夹具事件统计脚本；
  物理张数推演（杠窗口长度判据）。

## 2. 合并 findings（已去重、归因、定级；定级经 challenger 复核）

### F-01 [major] E2 首层脱敏进 raw_text 无端到端测试，且该形态恰是记录端第二层/离线扫描盲区
- 归因：P3 F3-8 + P1 F1-6 合并。
- 位置：transport.py:203-223（replace 后 raise raw_text=text）、errors.py:81-84（raw_text 刻意不过
  sanitize）、redact.py:31-37 与 validator 离线扫描（unredacted_secret_matches，同三组形态正则）、
  tests/adapters/official/test_raw_wiring.py:148-151（手工构造 ConflictError 绕过传输层）。
- 证据：raw_text 链路的唯一实质防线是 transport 的"精确替换后进异常"（已核对：request() 与
  open_sse_stream 错误分支均在分类前完成 token→"***" 替换，代码正确）；但没有任何测试断言
  exc.raw_text 已脱敏且完整（既有脱敏测试只断言 detail/str/repr）；记录端第二层与离线验证器只有
  Bearer/JWT/key=value 三组形态，对"非 Bearer 前缀回显的裸长串"（40+ 字符）不命中——
  errors.sanitize 的 _LONG_SECRET_PATTERN 恰好未在 redact 侧复刻。
- 触发条件：传输层替换逻辑回归（顺序/分支遗漏），或官方错误体回显非我方 Token 形态的长凭证串。
- 影响：红线"日志/审计必须删除 Authorization 与 Token 原文"在 raw 落盘链路无测试护栏；一旦第一层
  回归，409/429 拒绝体原文（含凭证）可随审计落盘而全套件仍绿。
- 最小修复：① 传输级用例：409/429 响应体以裸 token 形态回显 → 断言 exc.raw_text 不含 token 且
  其余原文保留；② 加一条真实 session → 真实 sink → 落盘文本不含 token 的用例；③ redact.py 与
  验证器补 _LONG_SECRET_PATTERN 同款长串形态（写侧与离线侧同源）。

### F-02 [minor] 增量摸牌窗口的 409 恢复路径依赖跨模块"水位==摸牌事件 seq"隐含恒等，且零回归测试
- 归因：P1 F1-1（P2 复核点 2 同向）。
- 位置：game.py:1021-1047（_handle_conflict 只走快照路径 current_window() 比较键）、
  projector.py:405（draw 分支 trigger_seq=snapshot.seq）、sync_state.py:244（增量 key=摸牌事件 seq）、
  test_cursor_discipline.py（无任何 409/ConflictError 用例，grep 证实）。
- challenger 推演：按官方语义"本人摸牌窗口期间无任何其他事件"，快照水位恒等于摸牌事件 seq，
  恒等成立（我方窗口开启期间他家 pass 不可能产生——响应窗口先于我摸牌全部结束），因此当前
  409 同窗判定正确。风险是**隐性脆弱**：该恒等无测试锁定，且增量窗口 409 恰是 S3 修复后
  hu 误报场景的必经路径（先 409 再同窗弃牌），未来官方加发事件或 detect_window 改动即静默
  降级 SubmitRejectedClosed（方向保守：丢预算不产非法动作）。
- 最小修复：_handle_conflict 增加增量窗口键比较分支（与 _submit_locked:786-794 同款防御），
  或对 snapshot.seq != 摸牌事件 seq 记审计；补"增量窗口 409 后刷新 seq==/!= draw seq"两变体回归。

### F-03 [minor] 杠（暗杠/补杠）窗口的防双计归一化只有数学无样本：机制裁定成立，证据真空待补
- 归因：P1 F1-2 + P2 F2-1 + P3 F3-6（三包同题）；两包原判 [major]，challenger 按 §4.1 物理
  张数复核**驳回机制缺陷主张、保留证据缺口**（见 §4.1 裁定全文）。
- 位置：engine.py:423-425；tests/fixtures/hangma/**（3 归档场 gang 事件数 = 0、金例 4 条含副露仅 1
  条 peng，脚本实测）；test_hu_gate_and_double_count.py:107-114。
- 影响：官方在杠后补牌窗口的 my_hand 长度约定（是否并入补牌、长度几何）无任何官方样本或夹具
  锚定；若官方约定偏离"含摸牌形态长度 = 14 − 3×副露数"，归一化判定可能失配（两种形态都靠
  该长度区分）。属证据真空而非已证缺陷。
- 最小修复：下次官方测试房在自家杠后补牌窗口抓一条 /state 原文核对长度与末张；本地补
  "含杠副露 × 两种形态 parity + 杠上自摸真胡/假胡金例" 单测。

### F-04 [minor] notify open_sse_stream 非 2xx 错误分支：取消路径跳过 response.aclose()
- 归因：P1 F1-4。
- 位置：transport.py:268-274（错误体读取的 try/except 不含 CancelledError，274 行 aclose 无
  finally 兜底；成功路径 288-289 有 finally）。
- 触发条件：notify 接入后 aclose 强制取消恰逢"非 2xx + 慢响应体读取"。
- 影响：httpx 响应未关闭，连接回池延迟/句柄悬挂（池上限 40）；当前模块未接入运行链路，影响面
  为零，属接入前待办。
- 最小修复：错误分支改 try/finally 保证 aclose。

### F-05 [minor] E1 只保留 GET 2xx（含坏报文）原文：429/401/403/404/5xx 响应体全部丢弃
- 归因：P2 F2-3（P4 open 风险 2 同向）。
- 位置：game.py:724-732（_emit_raw_state 仅成功路径）与 game.py:734-767（各 except 只 note/pass，
  不发射）；transport.py:203-223 已把脱敏原文放进 exc.raw_text。
- 证据：接口契约登记文（interface-contracts.md:176-178"adapter 层全部 /state 响应…含全量快照原文、
  坏报文"）与 raw_events 词表 http_status 字段注释隐含非 2xx 在覆盖范围内；S4 笔记 E1 口径
  "每次 HTTP 成功恰好一条"与词表宽口径存在边界差异。验证器不误报（request_no 只随成功递增）。
- 影响：限速（429 Retry-After 语义原文）与认证故障（401）的诊断原文缺失，与"收发原文全量保留"
  承诺的宽口径不符。
- 最小修复（二选一）：在 _get_state 各 except 分支补 _emit_raw_state(..., http_status=exc.http_status,
  raw=exc.raw_text or "")（request_no 不递增）；或在 interface-contracts/笔记中显式收窄 E1 范围为
  "2xx 与解析失败响应"。

### F-06 [minor] notify 对非有限 Retry-After 无钳制：run() 可永久悬挂
- 归因：P1 F1-3。
- 位置：transport.py:213-219（float(header) 只捕 ValueError）→ notify.py:543-548（max(退避,
  retry_after)）→ notify.py:563（await sleep(delay)）。
- 触发条件：服务端/代理返回 Retry-After: 1e999（float=inf，已实证 asyncio.sleep(inf) 永久挂起）
  或超大有限值；nan 形态亦未显式拒绝。
- 影响：违反"有界重连、绝不裸抛、run() 返回封闭结果"承诺；只能靠 aclose/外部取消打断。
- 最小修复：解析处 math.isfinite 校验（非有限按 None 走指数退避），或对 delay 施加有限封顶。

### F-07 [minor] raw 原文无单条大小上限：emit 同步成本与队列驻留随响应体线性放大
- 归因：P1 F1-5。
- 位置：raw_events.py:55-74（无截断）、jsonl_sink.py:219-221（redact_value + json.dumps 在调用
  线程同步执行）、jsonl_sink.py:251-256（队列按条数 16384 计）。
- 触发条件：官方/代理故障返回超大 /state 或错误体（正常体积约 0.25–1.5KB 无虞）。
- 影响：异常体量下 1s/3s 窗口阻塞风险与驻留内存放大（防御性缺口；S4 笔记 §3.4 只声明
  "不按体积抽样/丢弃"，未声明单条上限）。
- 最小修复：transport 层设响应体读取上限（如 1MB）并分类为协议异常；或 raw 落盘前保守截断并
  在 payload 记 truncated 标记（截断需与"原文完整保留"语义协商，建议取前者）。

### F-08 [minor] E5（组合根）未接通 raw_gzip/raw_rotate_bytes 配置，gzip 运维选项真实运行不可达
- 归因：P4 F4-1。
- 位置：bootstrap.py:435（JsonlAuditSink(config.audit_root, run_id)）；全仓无 audit_raw_gzip /
  audit_raw_rotate_bytes 配置键（grep 核实）。
- 影响：全量保留按默认参数生效（auto-evidence 门控自动启用严格检查），但笔记 E5 承诺的
  "盘位紧张开 gzip"只能改代码实现；属文档/接线缺口而非功能缺陷。
- 最小修复：RuntimeConfig 增加可选 audit_raw_gzip/audit_raw_rotate_bytes 并透传；或修订笔记 E5
  为"当前按默认值运行，gzip 需代码开启"。

### F-09 [minor] S4 笔记 E4 引用的 notify 接线符号不存在，且累加器不保留原始行文本
- 归因：P4 F4-2。
- 位置：audit-raw-retention.md:297-301（NotifyFrameProcessor.feed ~133）；notify.py 实际为私有
  _SseEventAccumulator.feed（:122，data 行解析 :133-138）；notify.py:31 声明"绝不携带原始行文本"。
- 影响：未来接线者按文档找不到符号；E4 若要 raw=帧原文需改造累加器（现只保留 data 载荷），
  文档未提示该配合改造。
- 最小修复：修订 E4 为实际符号 _SseEventAccumulator 并注明私有 + 需"保留 data 原文回传"配合改造，
  或标记接缝待 notify 线配合（与 notify 的脱敏边界声明一并修订：原文只进审计不进异常/日志）。

### F-10 [minor] 验证器对截断 gzip 段崩溃（EOFError 漏捕获），与"损坏段报 unreadable_audit_file"承诺不符
- 归因：P4 F4-3（challenger 已实证：截断段读取抛 EOFError，isinstance(e, OSError)=False）。
- 位置：validator.py:213-246（except OSError 在 240-246）；测试只覆盖坏 header（BadGzipFile ⊂
  OSError），未覆盖截断尾部（test_raw_retention.py:144-156）。
- 触发条件：raw_gzip=True 且进程被 kill（段无 gzip trailer）→ 下次离线验证 validate_run 裸抛。
- 影响：默认 gzip 关闭时零影响；开启后"必踩"（运维工具崩溃而非报告 violation）。
- 最小修复：except (OSError, EOFError)；补"合法 gzip 段截掉尾部"回归用例。

### F-11 [minor] interface-contracts.md §10.1 与归一化实际落点互相矛盾
- 归因：P4 F4-4。
- 位置：interface-contracts.md:223（"my_hand 不包含单列的 drawn_tile…由适配器统一规范化"——
  本次未改）；projector.py:452-461 注释（"kernel 契约要求 my_hand 保留官方原样（顺序与内容）"）；
  engine.py:400-430（实际唯一归一化点）。
- 证据：projector.observation() 原样透传官方 my_hand（含摸牌形态）；两份权威文本互相矛盾，S3
  笔记 §6.1 已自述按纪律不改适配器，但契约句未标注该裁决。
- 影响：低（引擎长度判定天然兼容两形态）；风险是复盘/策略消费方按契约句误以为
  PlayerObservation.my_hand 恒不含摸牌（见 §5 O-5）。
- 最小修复：contracts.md:223 补注"2026-09-05 起适配器保留官方形态，由 hangma 引擎按长度防御性
  归一化；适配器侧规范化列为后续工作线"。

### F-12 [minor] raw_state_stream_empty 的证据启发式漏检"从未投递过窗口"的场次
- 归因：P2 F2-4。
- 位置：validator.py:694-697（_is_adapter_game_state 只认 window / last_discard_projection_note /
  trigger_seq_projection_note 三键）、validator.py:795-802。
- 触发条件：某场开局后我方从未获得动作窗口（他家速胡/终局直达/阶段中断）→ 无上述形态的
  AUTHORITATIVE_STATE → 该场不进 state_polled，即使其 /state 原文流整段丢失也不报 violation。
- 影响：笔记 §5/§7"接线不完整会被 gap/stream_empty 揪出"的承诺存在盲区（现实频率低：任何场
  至少一次轮询都会产生快照吸收，但吸收本身不带这三键）。
- 最小修复：game.py 对首次 /state 解析成功发射一条不带窗口的场次层标记（如 {"state_polled": true}）
  并纳入证据键集合。

### F-13 [minor] S1 notify 行为矩阵测试缺行：5xx/反向退避/封顶/静默读超时/观察者异常/预算等待超时
- 归因：P3 F3-2 + F3-3 + F3-1 + F3-12 合并。
- 位置：test_notify.py（429 用例只覆盖 Retry-After 占优一侧 :371-397；sse_read_timeout 只断言
  默认值 :727-729；event_hook_errors 只断言为 0 :367/491；预算等待只测"释放后获得槽" :417-434）。
- 影响：S1 核心交付物（可恢复/终态分类矩阵与退避算术）的二分回归无测试兜底；75s keepalive
  假设路径（静默断流唯一防线）零触发。模块未接入运行链路，属接入前待补。
- 最小修复：补 5xx→重连、Retry-After=0.1 且 base=0.5 取 0.5、EOF×N 到 backoff_max 封顶时钟序列、
  小 sse_read_timeout_sec + 慢速流触发读超时、on_event 抛异常只计数、预算等待超时返
  BUDGET_UNAVAILABLE 六类用例。

### F-14 [nit] NotifyRunResult.error 携带完整未截断 raw_text 离开 notify 模块
- 归因：P2 F2-5（challenger 同观察）。
- 位置：notify.py:244-254/694-714（_result 只对 detail 做 sanitize，error 原样透传）；
  errors.py:81-84。
- 影响：无 Token 风险（第一层已精确替换）；模块"原始行文本绝不离开"声明与结果对象实际载体有
  张力，未来按 E4 设想直接落审计时容易误用（未截断错误体越过模块脱敏声明边界）。
- 最小修复：修订 notify 模块/NotifyRunResult docstring，显式说明 error.raw_text 为"已脱敏、未
  截断的 HTTP 错误体，仅限审计落盘使用"；或 notify 路径构造结果时剥离 raw_text。

### F-15 [minor] pending+gap 无进度退避分支零测试，且与 snapshot-gap 分支重复实现
- 归因：P3 F3-5。
- 位置：game.py:243-277（pending+gap 重建分支内含 stalls 计数与 _boundary_stall_sleep）；
  game.py:299-306（snapshot-gap 分支）；测试只驱动 snapshot 形态（test_cursor_discipline.py:224-265）。
- 影响：两分支的退避/清零/封顶写错或分叉（如 pending+gap 分支把窗口投递后的进度误判为停滞）
  全套件仍绿。
- 最小修复：脚本化连续 3-4 次"pending+gap=true 且水位不变"→ 断言 0.5/1.0/2.0 假时钟序列与
  清零；顺带评估两分支收敛为共享 helper（含 pre_seq 取点语义复核）。

### F-16 [minor] S3 差分重放的下界断言偏低，夹具缺失时静默 skip
- 归因：P3 F3-7。
- 位置：test_hu_differential_replay.py:283-285（total_official_wins>=1 / checked_draws>=50 /
  checked_meld_windows>=2）、:215-220/292-294（夹具缺失 pytest.skip）。
- 数据事实（脚本实测）：3 归档场 2 场流局；唯一官方胡 1 例（t_714a42392cba seat2 fan=1）；
  吃/碰后未摸牌窗口共 4 个且全部集中在同一场；杠事件全 0。正例锚定样本仅 1，门禁正例窗口仅 4。
- 影响：夹具日后被截断到下限附近时测试仍绿而覆盖显著缩水；归档数据缺失时差分测试整体静默消失。
- 最小修复：下界提高到与 README 声称量级一致（draws≥100、meld windows≥4）；夹具缺失改 fail 或
  提供显式开关；补充含杠副露归档房间（与 F-03 合并执行）。

### F-17 [nit] test_cursor_discipline.py:183 断言内部私有状态，与文件头自述合规矛盾
- 归因：P3 F3-4。
- 位置：tests/adapters/official/test_cursor_discipline.py:183（assert session._sync.last_seq == 103）。
- 说明：可从同用例 180-182 行 get_calls 序列完全推出，属冗余私有探测；tests/AGENTS.md
  "只通过公开接口验证行为"红线被违反（含一个合格 nit）。
- 最小修复：删除该行，或为 ProtocolSyncState 提供公开只读属性。

### F-18 [nit] hu 门禁早退先于 hand 缺失降级分支，顺序语义变化无测试锁定
- 归因：P3 F3-11。
- 位置：action_families.py:419（drawn_tile is None → _EMPTY）在 :424（hand is None → 记 Issue
  降级）之前；test_action_families.py 改动注释自证（补 drawn_tile 越过新门禁）。
- 说明：drawn 为空 + 手牌分析缺失的窗口不再记录 hu 族 Issue（行为差，方向无害）；修改后的测试
  恰好把旧断言引向带 drawn 路径，掩盖该顺序变化。
- 最小修复：补一条断言锁定意图（drawn=None 且 hand=None → 空且不记 hu 族 Issue），docstring
  注明"门禁早退先于降级簿记"为有意为之。

### F-19 [nit] 无"真实适配器 → 真实 sink → 磁盘 → validate_run"单链端到端测试
- 归因：P3 F3-10。
- 位置：test_raw_wiring.py（内存 FakeAuditSink + 真实 session）；test_integration_wiring.py
  （真实 trail+sink+validator，但记录手工构造）。
- 说明："game.py 发射 → 上下文键 → per-game raw 路由 → 验证器对账键"接缝靠两侧镜像保证，
  无单测贯穿；笔记 §11.3"接线不完整会被首次真实运行揪出"的盲区理论上应在 CI 内闭环。
- 最小修复：冒烟链：真实 game session 跑 1 次 state + 1 次 accept POST → 真实 sink →
  validate_run 断言 audit_complete=True 与 raw_events 计数（与 F-01 ② 合并）。

### F-20 [minor] 模块级文档未同步：recording.md RAW 语义过时、official-adapter.md 未登记新语义
- 归因：P4 F4-5。
- 位置：doc/implementation/modules/recording.md:20-21（RAW 仍描述为"可由权威状态替代的重复原始
  快照"）；official-adapter.md（无 RAW_PROTOCOL_STATE/raw_gzip/增量窗口词）；两文件未在本次改动集。
- 说明：根 AGENTS.md 要求架构/主方案同步（architecture.md/technical-plan/interface-contracts 已
  完成），模块级文档属遗漏；现文与"唯一低优先级存证 + 背压最后一层 + 严格检查门控"新语义矛盾。
- 最小修复：recording.md 优先级段与 sink 段补 2026-09-05 语义；official-adapter.md 补 E1-E3 与
  游标纪律节或链接四篇笔记。

### F-21 [nit] 背压计数丢弃与 audit_complete 判红无互链（归因成本）
- 归因：P4 F4-6。validator.py raw_state_gap/action_missing 报红时报告不展示 summary 的
  raw_retention.dropped/emitted_attempts，操作者难以区分"接线缺失"与"背压丢弃"两种红因。
- 最小修复：violation 报告附注 dropped 计数，或把 dropped>0 写进 violation detail。

### F-22 [nit] 杂项：validator warning 分支（malformed_raw_request_no / unknown_raw_payload_schema）
零直接用例（P3 F3-9）；observation_snapshot.target_discard 对 draw 窗口实为"最近公开弃牌"、
注释声称"触发弃牌"（P2 F2-6，建议注释改口径或 draw 窗口置 None）；test_notify 计数口径
（笔记"48 用例" vs 实际 37 个 test 函数，参数化展开口径，建议注记统一）。

### F-23 [minor] _apply_snapshot 为死代码：ActionGate.observe_authoritative_window 从未被调用
- 归因：P2 F2-2（challenger 复核：HEAD 基线即无调用方，存量死代码，非本批引入）。
- 位置：game.py:455-461（_apply_snapshot 定义与门调用）、action_gate.py:83-91；全仓 grep 仅
  定义处两命中；实际快照归并路径 _apply_or_fail（game.py:463-497）不调用 observe。
- 影响：安全方向不受损——_responded 集合使同窗永不重入（更强保证）；但"直到权威事件证明窗口
  迁移才解除模糊封锁"的注释不变量实际实现为"永不解锁"，_blocked 恒留旧 key（诊断字段），且
  死代码误导维护者以为解锁机制已接线。
- 最小修复：在 _apply_or_fail 成功提交后调用一次 observe_authoritative_window，或删除
  _apply_snapshot 并在 block/注释中如实说明"标记仅诊断、永不解除"。

## 3. 关键争议裁定（challenger 独立推演，含驳回/降级说明）

### 3.1 杠窗口归一化长度判据（P1 F1-2 / P2 F2-1 原判 [major]）→ 降级为证据真空 [minor]
两包主张：杠副露消耗 4 张手牌，杠后补牌窗口官方"含摸牌"形态 my_hand 长度 = 13−4+1 = 10 ≠
14−3×1 = 11 → 归一化跳过 → 双计残留；并称 test_gang_replacement_draw_allows_hu 的输入只能经
幻影双计通过。

challenger 物理张数推演（裁定依据）：
1. 摸牌动作发生在**本人回合**，行动前持牌 = 13−3M(静息) + 1(刚摸) = 14−3M 张，不是 13−3M。
2. 暗杠从本人回合持有量展开：14−3M − 4（暴露）+ 1（杠后补牌）= 11−3M；此时副露数 M+1，
  官方"含摸牌"形态长度 = 14−3(M+1) = 11−3M——两式恒等。补杠同构（碰摊升级为杠摊，M 不变：
  14−3M − 1 + 1 = 14−3M）。明杠（他家弃牌响应）发生在非本人回合，drawn_tile 为空、归一化
  不适用。
3. 静息不变量：杠后玩家持牌总数 = 13+G（G=杠数，杠的补牌补偿第 4 张），暗牌 = 13+G −
  (3M+G) = 13−3M，杠数在相减中消去——"每面子折算 3 张"口径在全仓（hand_analysis.meld_set_count
  吃/碰/杠各计 1、RULES_EVIDENCE、引擎公式）一致成立。
4. 复核测试输入（test_hu_gate_and_double_count.py:107-114）：my_hand=1w..9w+东（10 张，契约
  形态 13−3×1=10 ✓）+ drawn=东 + gang 2b×4 → full_hand=11 张 → win_split(11,1)：3 组顺子
  （1w-9w）+ 将（东东，held东+drawn东）+ 杠摊作第 4 面子 → **真实杠上自摸胡**，非幻影；
  官方形态（11 张含摸牌，末张东）归一化命中 14−3×1=11 → strip 一张东 → full_hand 仍 11 张同
  多重集 → 两种形态判定一致。测试正确，两包的"仅能经幻影通过/无将"主张不成立。
5. 结论：公式对杠窗口成立；两包推演的 10 张口径漏算了"本人回合行动前已持 14−3M（含刚摸）"
  这一前提（错把静息 13 张当行动前持有量）。保留的有效内核 = 杠窗口无官方样本/夹具锚定
  （3 归档场 gang 事件 0、金例无杠），降级为 F-03 [minor]，并建议官方测试房抓取"自家杠后补牌
  窗口 /state"原文与本地 parity 单测固化。

### 3.2 增量窗口 409 身份恒等（P1 F1-1 / P2 复核点 2）→ 维持 [minor]
推演确认：官方语义下本人摸牌窗口期间不存在他家 pass/事件（响应窗口先于我摸牌全部结束），
快照水位恒等于摸牌事件 seq，恒等成立；P2 构造的"他家 pass 推进快照 seq 使 409 误判 closed"
反例序列在该前提下不可达。保留 [minor] 定级：恒等无测试锁定、跨模块隐含（projector.py:405
与 sync_state.py:244 两处独立推导），属脆弱性加固项（F-02）。

### 3.3 其余裁定
- P1"核查清单无问题项"与 P2"无问题不变量"清单经 challenger 复核均与代码一致（预算槽归还、
  取消不写游标、退避 sleep 注入点、_delivered_windows+ActionGate exactly-once、refresh 不延长
  预算、raw_text 唯一消费方为审计等），不再单列。
- F-03/F-16/F-10 等"开启后必踩/接入前必踩"类定级已按当前运行影响（默认关/未接线）校准。

## 4. 待确认风险（[open]，附验证方法）

- O-1（并入 F-03）：官方杠后补牌窗口 my_hand 长度约定未实测。验证：官方测试房间自家杠后补牌时
  抓 /state 原文；或检索 runs/** 旧审计带 gang 副露的 state_response。
- O-2（P4 open 1）：跨局边界退避（封顶 2.0s）对"局首他家弃牌开启的响应窗口"发现时延的影响：
  庄家思考 >2.5s 且落在退避睡眠内时可能错过局首 peng/chi（均为可选动作，服务端自动过，无红线
  影响，属机会损失）。验证：下次真实 run 统计每局首个 tile_discarded 与窗口投递时差；或 fake
  注入庄家思考 1.2s/2.5s 两档断言窗口仍投递。
- O-3（S1 笔记 §7 已自列）：SSE 帧字节形态（空行分隔假设）、closed 后重连实际响应（404 预期）、
  75s 读超时 keepalive 假设——接入前需官方环境实测。
- O-4（P1 open 4）：notify 未来接入时连接池容量（httpx max_connections=40）对"16 场 SSE 常驻 +
  16 长轮询 + 动作 POST"的建模缺失（StreamBudget 只覆盖并发连接数，不覆盖池容量）。
- O-5（F-11 关联）：PlayerObservation.my_hand 官方形态（含摸牌）与契约句（不含）并存，策略/牌效
  特征与复盘消费方若直接 my_hand+drawn_tile 计数会双计。验证：grep policy/特征构造是否独立读取
  my_hand 与 drawn_tile；建议下一轮把适配器侧归一化（S3 笔记 §6.1 遗留）落实并在 projector 加
  投影测试。

## 5. 分线验收建议与后续待办（供总体评审裁决）

- S1：**接受**（未接线交付符合派单边界）；接入运行链路前必须关闭 F-13（矩阵测试）、F-06、
  F-04、F-09（与 S4 接缝文档协同），并实测 O-3/O-4。
- S2：**接受**；建议下一迭代落实 F-02（409 恒等加固 + 回归）、F-15（pending+gap 退避测试/
  收敛）与 F-23（死代码清理或接线）。
- S3：**接受**；建议落实 F-03（官方杠窗口样本 + parity 金例）与 F-16（重放下限/夹具缺失策略），
  并把 contracts §10.1（F-11）修订与适配器侧归一化排入后续工作线。
- S4 + E1-E3：**接受**；建议优先处理 F-01（红线护栏测试，major）、F-10（一行修复 + 回归）、
  F-05（E1 口径决策：收窄文档或补发射）、F-08（E5 配置或文档）。
- 杂项：F-20/F-11 文档同步、F-02/F-03 测试补齐按现有工作线节奏排期；cursor 笔记 §8 的审计
  埋点重分类建议（预期内边界 gap 快照改记 AUTHORITATIVE_STATE）属审计契约变更，留总体评审。

## 6. 复核声明（对照派单完成标准）

- 交叉审查覆盖：S1（notify.py 全文 750 行 + transport 流路径）、S2（sync_state.py 全文 +
  game.py 轮询/投递/提交全路径）、S3（engine/action_families 全文 + 证据链）、S4+E（raw_events/
  jsonl_sink/schema/summary/validator 新增 + game/errors/transport 接线 + decision_loop 快照），
  对应测试与 4 篇交付笔记均已逐条对照；四视角并行独立 + challenger 组合去重归因定级；
- 每条 finding 均有位置/触发条件/影响/最小修复；无法实证的已记 [open] 并附验证方法；
- 本人对合并 findings 的裁决依据（代码原文引用与物理推演）记录于 §3，可复核；
- 冻结契约零改动、运行行为零回归预期（除 S2/S4 有意行为变化且测试覆盖）经 git diff 与测试
  收集（1218 例）核实。
