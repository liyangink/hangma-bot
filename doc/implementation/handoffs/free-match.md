# 自由赛线交付 handoff：自动匹配 AUTO_MATCH v1（free-match）

> 工作线：自由赛（auto-match-v1）｜contract_id：parallel-v1
> contract_commit：契约文档基线随 HEAD；受控 C1 类型扩展（RuntimeMode.AUTO_MATCH /
> MATCHING_UNAVAILABLE / CAPACITY_LIMIT / AUTO_MATCH 空目标豁免）由主审先行合入
> 工作树（未提交，本线直接 import 使用，未在任何本地文件复刻同名常量）
> code_commit：HEAD ``f129fba6672254ede43b1d62efd21834a21dc2ac``
> 本地 dirty：是（§1 清单：主审/审计线 C1 并发改动 + 本线 8 个新增文件；未执行 git commit）
> 环境：Python 3.11.15（.venv）｜uv 0.12.2｜pytest 9.1.1（asyncio_mode=auto）
> 契约基线：parallel-contracts.md（C0 文档契约）＋doc/implementation/contracts/parallel-v1.json
> 本线产物目录：free-match-start.md 规定的 7 个文件（见 §2），全部为**新增文件**，
> 未修改任何既有文件。

## 1. 交付结论

AUTO_MATCH 自动匹配工作线 v1（Fake/fixture 验收级）已完成：新增
``OfficialAutoMatchSession``（TournamentSessionPort 第二真实实现，register/ready
本地拒绝、HTTP=0）、``AutoMatchRuntime``（自动房专用生命周期：等待→运行→
终局宽限收尾）、``run_auto_match.py`` 入口与 ``auto-match.example.json`` 配置样例，
以及 49 个新增行为测试（全绿）。**真实自动房（M=10）验收未执行**：无授权全局
Token 与官方内网连接；所需协议事实已在 §6 标注为未验证项，不能把 Fake 级
验收写成已通过集成门禁。

工作树（2026-09-06）同时含主审/审计线的**受控 C1 集成改动**（未提交）：
contracts.py / bootstrap.py / audit.py / decision_loop.py / participant_runtime.py /
recording(raw_events,__init__,bundle,reader) / interface-contracts.md 与新增
audit_codec.py 等。这些文件不在本线可写范围，本线未触碰；**审计线已闭环**，
最终全量 1406 passed / 0 failed（含审计线新增用例），不再有跨线红项。

**返工记录（轮次 2，challenger 三点）**：
1. handoff 证据不一致（SHA/用例数/全量结果）→ 本版已按交付时刻文件重算并
   统一口径：§2 SHA-256 = 文件字节哈希（交付时刻计算）；deliver 登记 digest
   为 runtime digestValue 算法（口径不同，登记值以 deliver 报告为准）；
   用例数/全量结果以本版 §2/§4 为准（49 用例；全量 1406 passed）。
2. "10 场并发 Fake 验收未实测却标已覆盖" → 新增
   test_ten_game_concurrency_at_config_m（config.M=10 一次开满 10 场、
   10 场 GAME_FINISHED）；验收表该行已改述为实测覆盖，不再用 M=2 双场代替。
3. "match 配额间隔可被配置击穿" → 配额语义常量钉死（60s 窗口 ≤10 次实际
   POST + 相邻间隔下限 6.0s），构造校验拒绝低于下限的配置（只能上调）；
   新增防击穿与滑动窗口用例（test_match_interval_below_official_minimum_rejected /
   test_match_quota_sliding_window_caps_ten_per_minute）。详见 §3 配额行。

## 2. 实际改动文件（全部新增）与公开导出

| 文件 | 角色 | 公开导出/要点 |
| --- | --- | --- |
| ``src/hangma_bot/adapters/official/auto_match.py`` | 适配器 | ``OfficialAutoMatchSession``、``SERVER_DEFAULT_MAX_GAMES/ROUNDS``、match 默认参数常量；内部 _MatchResult/_Registration 不导出 |
| ``src/hangma_bot/application/auto_match_runtime.py`` | 应用层 | ``AutoMatchRuntime``、``AutoMatchSettings``（frozen，含 source_namespace/声明上限/match 重试/收尾宽限配置） |
| ``scripts/run_auto_match.py`` | 启动脚本 | 只解析配置并调用组合根 ``build_auto_match_runtime``（主审集成后存在，见 §5.3）；自带退出码表与 RESULT 行 |
| ``configs/auto-match.example.json`` | 配置样例 | mode/base_url/expected_tournament_id(null=发现)/known_guide_version/token_kind/token_env/audit_root/strategy/insecure_hosts/sse_enabled/source_namespace/auto_match{…} |
| ``tests/adapters/official/test_auto_match_adapter.py`` | 会话测试 | 32 用例 |
| ``tests/unit/application/test_auto_match_runtime.py`` | 运行时测试 | 9 用例 |
| ``tests/unit/application/test_auto_match_script.py`` | 入口测试 | 8 用例 |

文件 SHA-256 = **文件字节哈希**（交付时刻计算，供跨机器核对；deliver 登记的
digest 为 runtime digestValue 算法，两者口径不同，登记值以 deliver 报告为准）：

- auto_match.py ``b28861b76941677135fbebeb5a220d0c085a1940a493a173743c19305ff376d6``
- auto_match_runtime.py ``5696587f0963b294ae757565e3aff252c63ff4c55b967e7e28aed667a48b4d2d``
- run_auto_match.py ``ce33265dc8a0e320d11cf8f3e71f5e940b73eafb097aecfcff166661abf6e2f4``
- auto-match.example.json ``aaca025aaf75aee0f0aec95f702b781d55ff38ef122d70abbd57cc87dc69fe62``
- test_auto_match_adapter.py ``ac92e59bdeba3a9b0b8297ee91d91b61a7e2fad36e2565d53f0c1c0a287b7594``
- test_auto_match_runtime.py ``c797be4542811584dc019675b01e5e504dd4aaf1f77a9acd1f176c4fa78b5da4``
- test_auto_match_script.py ``e4bb75b04682d0b737c00ec4bb4a0340332c210758c0b7d19f998efb04e2eca6``

## 3. 设计决策摘要（实现口径，先读代码 docstring）

| 决策 | 口径与依据 |
| --- | --- |
| 一次 match 的边界 | 会话实例只完成一次自动房操作；``initialize`` 只允许一次（防副作用入口重入）。空目标且 ``/api/me`` 无活动场次才 POST match；**恢复非空目标零 match**；``next_update`` 永不调用 match（幂等语义归协议，不靠重复 POST 保活） |
| 无归属证据即停 | 官方没有 game→room 映射端点：空目标＋已有 active_games ⇒ MATCHING_UNAVAILABLE（禁止凭 game_id 猜房再 match 占第二间房） |
| 声明上限预检 | 客户端先于任何 POST 拦截声明 < 服务默认（M=10/Rounds=8，v15）⇒ CAPACITY_LIMIT；到达适配器的 404 NO_ROOM_AVAILABLE 按瞬态建房后入席失败**有界重试**（重试耗尽 ⇒ MATCHING_UNAVAILABLE） |
| match 配额（常量钉死，防配置击穿） | 官方 10 次/分 → QUOTA_WINDOW_SEC=60s 内实际 POST ≤ QUOTA_MAX_CALLS=10 次（满窗等到窗口最早一次 +60s），相邻间隔 ≥ MIN_MATCH_INTERVAL_SEC=6.0s；``match_min_interval_sec`` 构造校验不得低于 6.0（默认 6.5 留余量，配置只能上调）；60s 窗口与下限均为常量，无任何配置可放宽 |
| MATCH_BUSY/限速重试 | 同一次匹配有界重试：每次等待 ≤ ``match_busy_wait_cap_sec``，遵守 Retry-After（调度器全局冷却）；429 记入调度器冷却，重试仍受配额约束 |
| POST 结果不确定 | 超时/断连/5xx **不盲目重发**：核验 ``/api/me`` 一次（401⇒AUTH）后按 MATCHING_UNAVAILABLE 停止并保留恢复信息（下次以已知 room_id 恢复） |
| 全局隔离 | 快照 active_games = me.active_games ∩ 房间 my_games；交集外场次不进入本房快照（PROTOCOL_RECOVERED 显式诊断） |
| kind=auto 核对 | 房间详情携带 kind 且 ≠ auto ⇒ TARGET_MISMATCH；kind 缺失 ⇒ 记录未确认证据后继续（全局 Token 只能经 match 入席，详情可达已限定自动房） |
| 终态判定归属 | 适配器对 finished/closed/void 一律返回普通变化快照；终态化只在 AutoMatchRuntime。finished 后 404 是官方关停正常形态：适配器**用本地已确认 finished 证据合成 closed 变化快照**（不终态化、不伪造）；无 finished 证据的 404 ⇒ MATCHING_UNAVAILABLE |
| 终局收尾 | 运行期离开 active 的场次任务被关闭；房间 finished 后进入 draining：为 my_games 中无终局记录的场次补开会话（官方宽限内 /state 仍返回终局），默认 45s 宽限预算（官方约 60s）；宽限耗尽或房间 closed ⇒ 记录缺失（drain_missing_finals），**不伪造终局/零分**；结果缺失不影响按 finished 证据正常退出（detail 与审计明示） |
| 资源上限 | 运行期按 config.M 截断 active 并显式诊断（active_exceeds_config_m）；房间返回 > M 时适配器/运行时双层防御 |
| 审计词表 | LIFECYCLE_CHANGED area=auto_match：matching_started/matched/waiting/running/draining/finished/matching_stopped ＋ 场次级 game_opened/game_closed/game_ended；PROTOCOL_RECOVERED area=auto_match 见 §5.6 |
| raw 原文 | POST /api/match 每次实际请求留原文（source=match_response，payload v1）：成功/409/404/429/5xx/不确定（空原文），attempt 为本地尝试号；builder 由审计线提供（本树已见 ``build_match_response_payload``），适配器接线已完成 |

## 4. 测试命令、结果与证据

全部命令用 ``.venv/bin/python -m pytest``（本仓库 .venv：Python 3.11.15 / pytest 9.1.1 / asyncio_mode=auto）。环境限制：本机沙箱无法写 ``~/.cache/uv``（``uv run pytest`` 报 Failed to initialize cache），故不使用 uv 前缀；等价命令为直接调用仓库 .venv（见 §6 环境项）：

- ``.venv/bin/python -m pytest tests/adapters/official/test_auto_match_adapter.py -q`` → 32 passed（含 gap→seq=0 重建场次路径、SSE 降级贯通、配额防击穿与 60s 窗口、contract-vectors 两个 auto 行为向量消费测试；raw 断言用例在审计线注册缺失时 skip）
- ``.venv/bin/python -m pytest tests/unit/application/test_auto_match_runtime.py -q`` → 9 passed（含 config.M=10 真实十场并发）
- ``.venv/bin/python -m pytest tests/unit/application/test_auto_match_script.py -q`` → 8 passed
- 开工基线全量：1292 passed（本线改动前，工作树含主审 C1 首批改动）。
- 最终全量（审计线 C1 已闭环）：**1406 passed / 0 failed**。过程记录：本线
  文件加入后曾出现 tests/adapters/recording 2 failed（审计线 C1 中间态：
  production 已扩、其测试未同步，与本线无关，已隔离复证）；审计线提交闭环
  后消失。本线用例中唯一依赖审计线注册的
  （test_match_raw_recorded_when_builder_registered）在注册缺失时 skip。

验收对照（free-match-start.md §5 Fake/夹具清单）：

| 验收项 | 覆盖 |
| --- | --- |
| Token 范围错误 | adapter：scoped 拒绝（TARGET_MISMATCH，零 match） |
| 等待幂等（不反复 POST match） | adapter：恢复模式零 match；next_update 轮询零 match |
| 超时归属恢复 | adapter：match 不确定 ⇒ 核验 ⇒ MATCHING_UNAVAILABLE＋恢复证据审计；restore 404 ⇒ MATCHING_UNAVAILABLE |
| 永久容量不符 | adapter：声明 < 默认 ⇒ CAPACITY_LIMIT（POST=0）；MATCH_LIMIT_REACHED ⇒ CAPACITY_LIMIT |
| 忙/限流 | adapter：MATCH_BUSY/NO_ROOM_AVAILABLE(瞬态) 有界重试、429 冷却（调度器全局冷却） |
| match 配额（10 次/分，防击穿） | adapter：常量钉死 60s 窗口 ≤10 次实际 POST + 相邻间隔下限 6.0s（配置只能上调）；用例：test_match_interval_below_official_minimum_rejected、test_match_quota_sliding_window_caps_ten_per_minute（12 连发时刻分布：第 11 次 ≥ 首 POST+60s） |
| 全局其他赛事隔离 | adapter：foreign active 不进快照＋诊断 |
| 10 场并发（能力内 M） | runtime：**config.M=10 实测开满 10 场**（test_ten_game_concurrency_at_config_m：running 期一次 game_opens=10、10 场 GAME_FINISHED、终态 finished、无缺失诊断）；另有 M=2 双场快回归与 active>M 截断＋诊断用例 |
| 乱序/缺口/SSE 降级 | adapter：open_game 场次路径实测 state 缺口 → seq=0 权威重建 → finished 终局；SSE 降级**贯通实测**：通知流不可用时自动降级长轮询并记 trigger=sse_degraded（test_open_game_sse_stream_unavailable_degrades_to_long_poll），窗口照常交付 |
| finished 后 404 | adapter：finished 证据 ⇒ 合成 closed 变化快照 |
| 未取终局先 404 | adapter ⇒ MATCHING_UNAVAILABLE；runtime 透传＋cancelled 出口 |
| 宽限收尾/缺失 | runtime：draining 补抓晚期场次、宽限耗尽记录缺失不伪造终局 |
| 取消及慢审计 | runtime：取消清理、audit_degraded 不阻塞终态 |
| register/ready HTTP=0 | adapter：本地 RuntimeError＋零 HTTP 断言；runtime：零调用断言 |
| 身份/归属漂移 | adapter：next_update 中 tournament_id 漂移 ⇒ TARGET_MISMATCH |
| 向量 auto-resume-known-room | adapter：恢复已知房 POST match=0 且 register/ready=0（本地拒绝、零 HTTP） |
| 向量 auto-404-without-finish-evidence | adapter/runtime：停止并明示缺失（MATCHING_UNAVAILABLE、部分/未知），零 GAME_FINISHED、无 finished 事件、不记零分 complete |

## 5. 需要主审集成的共享文件差异（按 C1→模块→组合根顺序）

### 5.1 ``errors.py``（KNOWN_OFFICIAL_CODES 白名单扩展）

新增三个自动匹配端点专用官方码（v13 起；MATCH_LIMIT_REACHED/TOKEN_NOT_SCOPED
已在白名单）：

```python
KNOWN_OFFICIAL_CODES = frozenset({
    ...  # 既有
    "NO_ROOM_AVAILABLE",  # 自动匹配：声明低于默认=永久 / 建房后入席失败=瞬态
    "AUTO_MATCH_ONLY",  # 对自动房 register/ready 直连
    "MATCH_BUSY",  # 自动匹配忙（只挡建房）
})
```

调用点：``auto_match._match_error_code`` 优先读 ``exc.official_code``，白名单
落地后不再依赖 detail 正文扫描兜底（扫描逻辑保留为防御）。适配器测试直接
构造异常断言分类，白名单化不改变行为。

### 5.2 ``adapters/official/__init__.py`` 与 ``application/__init__.py`` 导出

- official：``__all__`` 增加 ``"OfficialAutoMatchSession"``（跟随
  OfficialTournamentSession 先例，bootstrap 需要导入）。
- application：``__all__`` 增加 ``"AutoMatchRuntime"``、``"AutoMatchSettings"``
  （跟随 ParticipantRuntime 先例）。

### 5.3 ``bootstrap.py``：``build_auto_match_runtime`` 组合入口

新增函数与装配对象（全部照抄 build_runtime 的既有内部顺序，唯一新增是对
会话注入自动匹配参数、运行时注入 settings；不要复制 ActionGate/序号恢复/
SSE 状态机——它们仍归 OfficialGameSession）：

```python
@dataclass
class AssembledAutoMatchRuntime:
    """自动匹配装配结果（字段语义与 AssembledRuntime 一致）。"""

    config: RuntimeConfig
    settings: AutoMatchSettings
    run_id: str
    sink: JsonlAuditSink
    session: TournamentSessionPort
    policy: BotPolicy
    runtime: AutoMatchRuntime

    async def run(self) -> None:
        await self.runtime.run()
    # audit_degraded / last_audit_summary / participant_id 委托 runtime（同 AssembledRuntime）
```

```python
def build_auto_match_runtime(
    config: RuntimeConfig,
    settings: AutoMatchSettings,
    *,
    session_factory: Optional[Callable[[], TournamentSessionPort]] = None,
    policy_factory: Optional[Callable[[], BotPolicy]] = None,
) -> AssembledAutoMatchRuntime:
    """装配一次 AUTO_MATCH 自动房运行（一个进程一个全局 Token，默认单会话）。

    注入顺序同 build_runtime：固定 run_id（_FixedRunIds）→ JsonlAuditSink →
    _AuditContextProvider（身份发现前占位、initialize 成功后由 _IdentityAwareSession
    回填 user_id/room_id）→ OfficialAutoMatchSession(...)（transport 复用
    TransportConfig、scheduler、sse_enabled/StreamBudget；settings 提供
    declared_max_games/declared_rounds 与 match 重试参数/room_poll_interval_sec）
    → 策略工厂（_STRATEGY_FACTORIES）→ AutoMatchRuntime(target=RuntimeTarget(
    mode=AUTO_MATCH, expected_tournament_id=config.expected_tournament_id,
    known_guide_version=config.known_guide_version), settings=settings, ...)。
    """
```

注意点：RuntimeConfig 的 AUTO_MATCH 支持（空 expected 豁免、token_kind 交叉
核对）主审已在工作树合入（bootstrap.py 现有 diff）；本线不需要新字段进
RuntimeConfig——自动匹配专用字段全部收在 ``AutoMatchSettings``（application/
auto_match_runtime.py 定义），脚本层先拆出 ``source_namespace``/``auto_match``
再调 ``runtime_config_from_mapping``。run_auto_match.py 通过
``getattr(bootstrap, "build_auto_match_runtime", None)`` 延迟解析，集成后可
把该兼容分支收编为普通调用（已注释指引）。

### 5.4 ``run_participant.py`` 退出码表（参考性，不需改）

run_auto_match.py 自带退出码表并新增 ``matching_unavailable/capacity_limit ⇒ 10``
（永久停止、守护不重启）。若将来统一由 run_participant 守护自动房，需把这两
个原因加入其 ``_TERMINAL_EXIT_CODES``（一行差异，见脚本 docstring）。

### 5.5 审计词表登记（validator/文档侧）

LIFECYCLE_CHANGED 增补 ``area=auto_match`` 事件词表（payload 均含 area 键）：
matching_started（declared_*）/matched（room_id, match_round_no）/
waiting/running/draining（room_status, drain_grace_seconds）/finished（reason）/
matching_stopped（reason）；同 area 的场次级事件 game_opened/game_closed/
game_ended 复用现有 event 键与 game_id 关联键。PROTOCOL_RECOVERED
``area=auto_match`` reason 集合：match_retry/match_busy_retry/no_room_retry/
match_rate_limited_retry/match_uncertain_evidence/match_uncertain_verify_failed/
room_kind_unconfirmed/room_config_mismatch/foreign_active_games_ignored/
active_exceeds_config_m/game_reopen_scheduled/game_reopen_budget_exhausted/
game_reopen_beyond_drain_deadline/drain_missing_finals/
room_void_no_final_collection/next_update 异常/监督循环异常退出等（未知字段
room_id/official_code/wait_seconds 记空串，见 free-match-start.md §4）。
PARTICIPANT_FINISHED reason 值扩展（matching_unavailable/capacity_limit）
已随 contracts.py 主审扩展存在。

### 5.6 raw 接线状态（依赖审计线注册；本线不写第二套 raw 代码）

source=match_response 的 builder/validator 注册属审计线交付（parallel-v1
§3.3，可能尚未合入）：本线适配器**只消费审计线 builder**，不实现第二套 raw
代码。注册合入后行为：每次实际 match POST 一条 RAW_PROTOCOL_STATE（成功/
409/404/429/5xx/不确定空原文，attempt=本地尝试号），路由 raw/global.jsonl
（match 无 game_id）；验证器按 source 统计、无 request_no 连续性语义。

为兼容"注册尚未合入"的评审环境，适配器**不在模块级 import** recording：
发射点在 ``_emit_raw_match`` 内 try-import，缺失时静默跳过发射（协议路径
不受影响）；对应测试用例（test_match_raw_recorded_when_builder_registered）
在注册缺失时 skip。审计线词汇测试更新后该用例自动生效，无代码改动。

## 6. 未验证/未决事项（诚实记录，禁止写成已通过）

1. **真实自动房协议事实**：房间详情 kind 字段真实形态（缺失分支按"未确认
   证据"继续并留审计）；ranking/my_games 对自动房的真实返回；rules 端点
   （/api/tournaments/{room_id}/rules）对全局 Token 的实际可达性——若 403/
   404 需调整核验链（推断可访问，无 fixture）。
2. 自动房状态时间线：等待期 status 取值、finished→closed→404 实际窗口、
   等待房长期不满是否 void/解散（当前等待期无限轮询，取消即止）。
3. **真实 M=10 并发节奏与 1s/3s 窗口压力**：现有测试房间 M=2 验收不能替代
   （free-match §5 明确）。SSE closed:true 真实终态样本仍缺，继续沿用既有
   降级路径与记录。
4. match 响应 config/round_no 真实样例留存 fixture（当前按最小解析：只要求
   room_id；round_no 原文留审计不当单局号）。
5. 官方 404 NO_ROOM_AVAILABLE 瞬态分支的 message 内容未实测：当前按"声明已
   本地拦截 ⇒ 到达适配器的 404 一律按瞬态有界重试"处理，活场首验确认。
6. 多进程/多节点部署约束（同 Token 单进程独占）写入运行说明：
   configs/auto-match.example.json 与 run_auto_match.py docstring 已声明；
   建议主审在 doc/architecture.md 或运行说明补充条目。
7. 结果缺失的运行"正常退出（0）＋detail 明示"口径：TOURNAMENT_FINISHED/
   CLOSED 语义下缺失记录不伪造终局（审计 drain_missing_finals + detail
   后缀），如需"退出码区分"可后续在 run_auto_match 增加（现未加，避免
   与既有 0=正常终态契约冲突）。
8. **环境限制（本机沙箱）**：无法写 ~/.cache/uv——``uv run pytest`` 报
   "Failed to initialize cache"，不可用；本线全部测试命令为
   ``.venv/bin/python -m pytest tests/<路径>``（直接使用仓库 .venv，与 uv
   同环境等价）。该限制只影响命令前缀，不影响产物与测试有效性。

## 7. 集成顺序建议

1. 审计线提交闭环（词汇/集成测试随其 C1 完成）→ 全量绿；
2. 合入 §5.1/5.2/5.3 差异（errors 白名单、导出、build_auto_match_runtime）；
3. interface-contracts.md §6 如需补一句"AUTO_MATCH 会话在已确认 finished 后
   对房间 404 合成 closed 变化快照（仍非终态化）"（可选，模块 docstring 已述）；
4. 真实自动房验收（授权全局 Token）：留存 match 原文 fixture、房间全流程
   快照与关闭报告，再更新本 handoff 的 §6；
5. 双份对照：契约提交 SHA 与集成分支 SHA 由集成人回填。

— 自由赛线（auto-match-v1）``2026-09-06``
