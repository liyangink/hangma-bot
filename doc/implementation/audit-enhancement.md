# 审计增强实施方案

> 2026-09-05 修订；实施基线 `c17ce06`。新增部分尚未实现。
> 本版取代此前拟议的审计信封 v2：复用已合入的原文留存和 SSE，保留信封 v1，以 `capture_profile=audit-plus-v1` 声明增强覆盖。
> 共同数据口径以[并行开发契约](./parallel-contracts.md)为准；分支与文件认领见[施工导航](./parallel-workstreams.md)。

## 1. 目标和现状

本线交付三个能力：保存可恢复的真实决策输入；把证据转换为能力明确的统一牌谱；提供只读实时查看。优先级依次为数据可靠、赛后定位、赛中体验。

当前已实现 `RAW_PROTOCOL_STATE` 原文留存、独立 raw 文件、可选 gzip 分段、原文对账和部分 `observation_snapshot`，见[留存笔记](./notes/audit-raw-retention.md)。本线补全内容和离线工具，不重写已经验收的协议状态机。

| 来源 | 现有证据与本线处理 |
| --- | --- |
| 测试房间 | v14/2026-09-05 的三个真实下载样本；合并同一单局的多个 block，保留四家起点和已发生轨迹。缺牌墙只能是 full_history |
| 测试赛事 | 实时接收的原文、观察和结果；没有可依赖的全量下载接口。只导出有证据的数据 |
| 自由赛 | 用户确认是 v15 `/api/match` 自动匹配；先记录运行事实，下载能力未确认。接入由自由赛线负责 |

数据缺失必须可识别。没有隐藏信息时不能保证导出可任意分叉的 `WorldState`；没有完整请求时不能假造可重算的策略输入。

## 2. 模块边界与交付顺序

记录器只接收事实，转换器只在离线运行，监控只读取同一份文件。

| 层 | 负责 | 不承担 |
| --- | --- | --- |
| application | 完整请求、实际计划、复核及终结原因；审计构造失败隔离 | 不导入 recording，不重做规则 |
| adapters/official | 复用 raw builder；测试房间下载与官方格式解析 | 不重写状态恢复，不运行训练或评估 |
| adapters/recording | 编码、队列、落盘、读取、完整性检查、打包 | 不判胡、不生成牌谱规则状态 |
| offline/replay.py | 证据关联、身份映射、统一牌谱导出和命令编排 | 不推测牌墙，不调用线上闭环 |
| bootstrap.py | 统一注入记录器、版本和下载客户端 | 由集成负责人合入组合根变更 |

按 A1 完整决策记录 → A2 读取/归档/转换 → A3 inspect/watch 实施。A2 的官方分块转换可以和 A1 独立推进；不能让 A3 的界面工作阻塞前两项。首版不增加数据库、服务端看板、事件总线或新订阅端口。

## 3. 记录接口与字段

### 3.1 保留 v1 信封和已实现原文

`AuditSink.emit/aclose`、`AuditRecord`、`AuditReceipt`、`AuditSummary` 的类型签名不变；原审计 `schema_version=1`，raw 的 `payload_schema_version=1` 不变。不再新增 `PROTOCOL_MESSAGE`，不再把独有 raw 定义成冗余快照。

增强生产者在新 payload 增加 `capture_profile="audit-plus-v1"`、`audit_producer="application"/"official"`。后者避免与 raw 已有的 `source=state_response/action_submit_response/sse_frame` 冲突。manifest 声明启用的 profile 和来源覆盖；旧数据继续按原校验规则读，不因缺少新字段失败。

本版不增加信封序号。持久化引用使用包内相对文件名和从 1 开始的行号，提交关联使用既有关联键；不能用文件行序跨进程排序。`request_no` 仍是场次会话局部计数，重建可重置，不升级成全运行游标。需要跨会话区分请求时由官方线加可选 `session_instance_id`，不修改原计数含义。

`RAW_PROTOCOL_STATE` 继续低优先级，背压丢弃计数并降级原文覆盖；规范权威状态和决策记录维持高优先级。采用现有失败策略，不能为保存 100% 原文阻塞出牌。完整测试房间下载可补充历史覆盖，不能抹去原运行的丢失事实。

### 3.2 增强词表

新增三种决策记录，其余复用已有种类。由审计线一次性更新 `application/contracts.py` 的 AuditKind、schema、生产者及相关契约测试，其他线不编辑该枚举。

| kind | 必需内容与时点 |
| --- | --- |
| RUN_MANIFEST | profile、source_namespace、环境、commit/dirty、实际源文件哈希、Python/依赖、策略版本及完整权重、指南版本/原文引用、脱敏配置。初始化未知字段可空并说明 |
| AUTHORITATIVE_STATE | 保留现有字段；增补完整可见 observation 供查看。赛事事实只保存真实收到的内容和时间。它不替代下面的 request |
| **DECISION_INPUT** | 分析完成、策略调用前：plan_revision、完整 request、原 budget、窗口接收单调秒、规则耗时毫秒。刷新另存新 revision，截止时间不变 |
| DECISION_PLANNED | 保留现有字段；增加 returned_plan、effective_candidates、过滤/保底原因及策略耗时毫秒。原计划异常时可空，不覆盖实际采用候选 |
| **CANDIDATE_VALIDATED** | 每次最终复核：plan_revision、完整 action/action_key、legal、reason、elapsed_ms；抛错时 legal=null，不冒充规则否定 |
| SUBMISSION_INTENT / OUTCOME | 保留现有完整动作和七类结果；补 profile/producer。取消复用既有取消常量，不伪造已经发送或明确执行 |
| **DECISION_ENDED** | 决策循环 finally：最后 plan_revision、end_reason、attempt_count；即使零提交、取消或错误也尽力记录。原因词表见统一契约 |
| LIFECYCLE_CHANGED | 复用现有 kind，area=audit 的 producer_failure / producer_summary 保存构造失败与关闭证据；area=auto_match 由自由赛线使用 |
| GAME_FINISHED / PARTICIPANT_FINISHED | 权威结果、来源与确认状态。缺结果为 null；作废与正常结束区别保存 |

同一决策记录按 `run_id/decision_id/plan_revision` 关联，提交按 `run_id/decision_id/attempt_no/audit_producer` 关联。应用层与官方层各一份不算重复；同一来源重复需逐条说明，不能普遍容忍任意次数。

### 3.3 复用值对象，避免重复模型

新增 `application/audit_codec.py`，显式映射生产类型。以下函数均为纯函数：输入为生产类型或 JSON 对象，输出为独立值；缺字段、错误类型、不兼容主版本或非有限浮点抛 ValueError，不读文件、时钟或网络。

```python
def decision_request_to_json(request: DecisionRequest) -> dict[str, object]:
    """编码完整当时输入；保留玩家观察权限、手牌顺序、规则候选和拒绝历史。"""
    ...

def decision_request_from_json(data: Mapping[str, object]) -> DecisionRequest:
    """解码并检查类型；不以当前规则补算缺失的历史规则事实。"""
    ...

def decision_budget_to_json(budget: DecisionBudget) -> dict[str, object]:
    """保存三个原单调时钟秒值；跨机器重算前必须平移，不能当 Unix 时间。"""
    ...

def decision_budget_from_json(data: Mapping[str, object]) -> DecisionBudget:
    """恢复原预算值并检查先后关系；不自动延长截止时间。"""
    ...

def decision_plan_to_json(plan: DecisionPlan) -> dict[str, object]:
    """保存完整候选顺序、策略评分分项和原因；评分不是桌内积分。"""
    ...

def decision_plan_from_json(data: Mapping[str, object]) -> DecisionPlan:
    """恢复计划，检查动作键与名次；不决定哪个动作实际提交。"""
    ...
```

每个顶层 JSON 带 `codec_version=1`，其他字段名与当前 dataclass 字段一一对应，嵌套 enum 取 `.value`、tuple 转数组；Action/WindowKey/PlayerObservation/CompetitionContext 直接复用 kernel 公共 codec，保留其 schema_version。RuleAnalysis、CandidateFacts 等按公开 dataclass 逐字段映射，包含 `None`、issues、emergency_candidate。未知可选扩展容忍，必需字段不自动补默认。编码新规范的唯一实现归本文件；评估读取器直接调用，避免另一套 request 模型。

`returned_plan` 无法编码时单独记失败，仍尝试保存有效计划。原始 `my_hand/drawn_tile` 形态保持现状；兼容规则见[契约 §3](./parallel-contracts.md#3-现有类型口径冻结语义不复制同名模型)。

### 3.4 故障持久化与发送截止时间

构造失败也必须出现在迁移后的报告里；只设置内存 `audit_degraded` 不够。这解决[前次审查 S1](../../review/audit-enhancement/review-summary.md)。

`AuditTrail` 增加内部安全构造入口，捕获 codec 异常后累计生产端失败计数，尝试发送不引用失败对象的最小 `LIFECYCLE_CHANGED(area=audit,event=producer_failure)`：含原 kind、九个关联键、失败阶段、脱敏错误类型。关闭前发送 `producer_summary`，包含生产尝试数、构造失败数、失败记录未入队数；记录器生成 summary 时与自身队列/写盘计数合并。`aclose` 返回的现有 audit_degraded 也必须反映生产端失败。

profile 运行缺 producer_summary、关闭写盘失败或进程被强杀时，验证器标记尾部完整性未知；不能从文件没有报错推断完整。最小失败记录也写不下时依靠失败计数和缺失关闭证明报告不完整，不添加阻塞备用磁盘通道。计数区分“构造前失败”和“sink 拒收”，同一次失败不能双计为两条缺失。

发送前新增同步工作必须在最终截止检查前完成，或在同步审计后、调用 HTTP 前再检查原 `latest_send_at_monotonic`。越界时 POST 调用为 0，并返回现有 SubmitNotSent。这解决[前次审查 S2](../../review/audit-enhancement/review-summary.md)，不改变线上预算和重复提交修复。

继续有界队列和后台写盘；必要时增加字节上限，超限整条计数拒收，不截断 request 后称为完整。基准测最长公共历史/候选、目标 M 下审计开关差异；同步记录耗时 P99≤10ms 是初始工程目标，不能替代每次发送截止检查。压缩、哈希、转换和界面都不在动作路径。

## 4. 产物、管理和跨节点转移

原运行目录沿用现有布局；新增数据各自封存，不重排四个进程的原文。

```text
audit-root/
  runs/{run_id}/                    # 现有 manifest、lifecycle、participants、raw、summary
  bundles/{bundle_id}/
    bundle.json                    # 本包版本、来源、闭合状态和文件哈希
    runs/{run_id}/...               # 原目录独立复制，含 raw/*.jsonl 或 gzip 分段
    official/{download_id}/
      source.json                  # room/batch/game_id、指南版本、采集 Unix 毫秒时间
      games.json                   # 场次列表原响应，凭证脱敏
      events.json                  # 分块事件完整原响应，成功验证后原子改名
    validation.json
  derived/{dataset_id}/             # 可再生，固定内容后不原地修改
    manifest.json
    index.jsonl                    # 跨进程单局身份及划分映射
    decisions.jsonl
    hands.jsonl
    validation.json
  exports/{bundle_id}.tar.gz
  exports/{bundle_id}.tar.gz.sha256
```

`bundle.json` 固定字段：`bundle_schema_version=1`、`bundle_id`、`created_at_unix_ms`、`run_ids`、`parent_bundle_ids`、`closed_cleanly_by_run`、`source_notes`、`files`。files 为 `{path,bytes,sha256}` 数组，路径相对于包根、bytes 为字节数、SHA-256 为全长小写十六进制，清单自身除外。bundle_id 为创建时生成的 UUID，和内容哈希分工不同。所有注释写在文档，JSON 文件保持严格 JSON。

1. 关闭运行目录后检查、复制；活动目录只允许只读查看或明确标注 `partial` 的快照，不能声称已完整封存。
2. 下载先写 `.partial`，记录原样响应与来源。成功校验再原子改名；失败保留诊断，不伪造空牌谱。
3. 打包覆盖相对文件和哈希，封存后不可追加；补采生成新 bundle 并填 parent_bundle_ids。大文件不进 Git。
4. 使用已有 scp/rsync 转移包与 `.sha256`；目标先核验归档哈希，再安全展开到临时目录并核对内部清单。拒绝绝对路径、路径穿越、链接及同名覆盖。
5. 同 run_id/相对路径/哈希相同视为重复，内容不同报冲突；同 hand_id 多视角合并索引，不覆盖原记录。不同源文件路径不能成为新的牌局身份。

源代码通过正常 Git 提交传递；包保存 commit、dirty、实际源文件内容哈希和完整策略权重，不复制私有运行配置。哈希相同不等于目标机器已经有对应代码，导入报告分别检查。

## 5. 统一牌谱 v1

字节字段、hand_id 算法、跨进程映射、缺失等级与训练权限只在[共同契约 §4—5](./parallel-contracts.md#4-数据身份来源及版本)维护，审计线是读写器所有者。本版补上[前次审查 R1](../../review/audit-enhancement/review-summary.md)：四个不同 stage_attempt UUID 和重启后的第五个 run 通过完整官方场次键合并为一个 hand_id，共用 split_group_id。

首批转换用仓库三个 archived-rooms 原文件验收。按完整返回 game_id 和 round_no 归组，按 seq 合并 block；后续空 start_hands 不清空手牌。起手 14 张但没有额外牌身份时不猜 drawn_tile。必须保留官方未知字段及原文引用，不把只面向公共历史的 PublicEvent 强行当作全信息事件格式。

`replay-check` 只调用 HangmaRules 和模拟线公开的历史核对能力；模拟线未交付时结构检查可 passed，规则检查必须 not_checked。即使某条历史未选择胡牌，也不能给规则分析贴“不可胡”的负标签。

## 6. 命令与只读监控

新增 `scripts/audit_tool.py`，只解析参数并调用组合根装配的实际用例。以下是拟交付命令，当前尚不可执行：

```text
python scripts/audit_tool.py validate PATH
python scripts/audit_tool.py inspect PATH --game GAME_ID
python scripts/audit_tool.py watch RUNS_ROOT --json --interval 1
python scripts/audit_tool.py collect-test-room --runtime-config CONFIG --room ROOM --batch BATCH --out DIR
python scripts/audit_tool.py convert BUNDLE --out DATASET
python scripts/audit_tool.py pack BUNDLE --out ARCHIVE
```

公共读取器在 `adapters/recording/reader.py`：`read_records(path)` 按实际文件返回记录及相对路径/行号；`read_bundle_manifest(path)` 校验清单。格式损坏提供位置，不悄悄丢掉行。运行中 JSONL 的最后半行暂缓读取，封存后半行就是损坏；支持现有 gzip 分段。压缩尾段正在写入时标记未闭合，不反复从头扫描全部牌谱。

watch 默认只输出状态变化；人工模式是终端表格，`--json` 是相同数据的逐行 JSON。显示 game_id/单局/座位、阶段和 seq、本人手牌、公开副露/牌河、候选前几项及理由、最近提交、恢复/超时/审计缺失与数据更新时间。显示的是已写入事实，延迟和过期明显标出；不在线重判胡，不获取他家隐藏手牌，不新增平台请求。已有 `scripts/monitor_run.py` 保持可用，必要接入通过集成人提供，首版不要求重写。

## 7. 文件和测试

| 操作 | 路径 | 边界 |
| --- | --- | --- |
| 新增 | application/audit_codec.py；adapters/recording/reader.py、bundle.py；adapters/official/replay.py；offline/replay.py；scripts/audit_tool.py | 均为实际功能，路径相对 src/hangma_bot 的除 scripts 外 |
| 修改 | application/audit.py、decision_loop.py；application/contracts.py 的 AuditKind 区域 | 完整决策采集和故障隔离，不修改决策/提交控制语义 |
| 修改 | adapters/recording/jsonl_sink.py、schema.py、summary.py、validator.py、raw_events.py | 保持 v1 与既有 raw 布局兼容；给自由赛登记 match_response builder |
| 由主审集成 | bootstrap.py、公共 __init__.py、官方既有发送路径必要打点 | 其他线不复制组合根，也不争抢 game.py/transport.py |
| 新增测试 | tests/offline/test_replay_*.py、tests/adapters/recording/test_audit_plus_*.py、tests/contracts/test_audit_plus.py | 可引用 shared vectors，不修改另一线测试 |

## 8. 实施顺序与退出标准

| 阶段 | 必须交付的可验证结果 |
| --- | --- |
| A1 | codec 完整往返；胡/吃/碰/杠/过候选均完整；同窗重规划与七类提交关联；零提交也终结；codec 故障迁移后可见；慢审计越截止无 POST |
| A2 | 四身份加重启稳定身份合并；真实分块样本正确评级；legacy 可读但不伪造输入；未知版本拒绝；打包转到新路径仍可读取并核验所有哈希 |
| A3 | watch 与 inspect 使用同一读取器；可退出不影响 Bot；监控进程停止、慢盘、队列满、尾部半行均不影响合法动作闭环 |
| 集成 | 目标 M 的审计开销与可靠性对照；既有 rules/adapter/SSE 回归；真实采集样本完成后由评估线读取同一产物 |

交付报告列出通过、未通过、未验证，保留测试命令及结果。没有执行的目标 M 全程比赛、自由赛牌谱下载或模拟导入不能写为通过。实施交接模板见[施工导航](./parallel-workstreams.md)。
