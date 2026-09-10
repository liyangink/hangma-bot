# 杭州麻将对战平台 API 与时间模型

> 官方来源：`https://10.240.169.190:18080/portal/#guide-api`
> 最新同步：2026-09-10；官方指南 **v30**，`updated_at=2026-09-10`。原始资料：[版本响应](./references/official-guide-version-v30.json)（v27 快照见 [official-guide-version-v27.json](./references/official-guide-version-v27.json)）、[指南全文](./references/official-guide-v27-content.txt)、[指南响应封套](./references/official-guide-v27.txt)。v8、v15 等历史快照保留。
> 本轮变更：v25 服务端限制最多两摊吃；v26 修复抓打圈圈主响应并公开圈主座位；v27 为门户榜单修订；v28 胡大牌榜排序链去掉「该牌型全史次数」键（纯门户）；**v29（breaking）新增全服功能开关**——管理面可关闭自由匹配与自建测试房，关闭后 `POST /api/match` 新匹配、建测试房、已完结 test 房「重开下一轮」（ready）一律 **403 `FEATURE_DISABLED`**（永久条件；ready 路径此前是 409 房态类）；v30 他人 `name` 全面收口为 AI 昵称、空则空串（消费方按空串回退 `user_id`），本人 `/portal/api/me` 与 `/admin/*` 语义不变。规则/圈主证据边界见[本轮对齐记录](../review/catch-owner-v26-2026-09-09/README.md)。
> 版本接口：`GET /portal/api/guide/version`；全文接口：`GET /portal/api/guide`（v14 起免认证）
> 注意：文件名为兼容既有链接暂保留 `v2`。平台仍在迭代，本文不代替运行时版本自检。
> 相关说明：[官方赛事流程](./official-tournament-flow-2026-09-03.md)、[架构与运行流程](./architecture.md)、[统一术语表](../UBIQUITOUS_LANGUAGE.md)

## 1. 接入边界

平台存在三组接口：

1. **玩家 API**：Bot 的正式比赛接口，使用 Bearer Token。
2. **公共辅助 API**：版本自检、番型计算和测试房间赛后数据，部分免认证。
3. **Portal API**：网页门户自身使用的会话接口。它们可用于人工测试和观战，但不应作为 Bot 的稳定契约。

所有玩家 API 请求都应带：

```http
Authorization: Bearer <参赛令牌>
Content-Type: application/json
```

参赛令牌只显示一次，服务端只保存 SHA-256；丢失后需重新生成。项目采用简化管理：Token 可集中保存在团队认可的私有运行配置中，但不得散落在代码、牌谱或日志里，所有 HTTP 日志必须移除 `Authorization`。

当前部署使用自签名 HTTPS 证书。结合一个月赛期和官方 Demo，本项目明确不建设正式证书申请/分发方案：`OfficialTransport` 允许仅对配置的赛事内网 `base_url` 关闭证书校验。禁止全局关闭 Python 或系统 TLS 校验；启动日志记录 `tls_verify=false` 即可。

## 2. 玩家 API

### 2.1 用户与身份

#### `POST /api/users`

创建用户，返回 `user_id` 和全局 Token。

- 全局 Token 不绑定锦标赛。
- 参与锦标赛时需要显式携带锦标赛 ID。
- 限速：每 IP 10 次/小时。

#### `GET /api/me`

返回当前 Token 对应的信息：

- `user_id`
- `tournament_id`：报名 Token 绑定的锦标赛；全局 Token 为空字符串。
- `active_games`：当前进行中的比赛列表，每项至少包含 `game_id`。

### 2.2 锦标赛

#### `GET /api/tournaments/me/rules`

返回报名 Token 所绑定锦标赛的规则和可变参数，无需传锦标赛 ID。

- 报名 Token：正常返回。
- 全局 Token：`400 TOKEN_NOT_SCOPED`。

示例：

```json
{
  "tournament_id": "t_xxx_b0",
  "name": "测试房间 #1",
  "status": "registering",
  "config": {
    "M": 10,
    "Rounds": 1,
    "BaseScore": 1,
    "YouCaiBiKao": false,
    "PengTimeoutSec": 1,
    "ChiTimeoutSec": 1,
    "DiscardTimeoutSec": 3,
    "StartAt": 1756656000,
    "RegisterDeadlineAt": 0,
    "Description": "本场赛程说明"
  }
}
```

配置字段：

| 字段 | 含义 |
| --- | --- |
| `M` | 该锦标赛内每名参赛者的同时场数/上限；正式赛事和测试房间都必须支持，实际运行集合以 `active_games` 为准 |
| `Rounds` | 每场比赛局数 |
| `BaseScore` | 底分 |
| `YouCaiBiKao` | 有财必拷响开关；指南原文写“必须爆头或杠开”。2026-09-07用户确认及测试房拒胡纠正本地解释：开启时手留财神必须爆头，杠补不独立豁免，见[规则证据§7](../src/hangma_bot/hangma/RULES_EVIDENCE.md#7-有财必拷响youcaibikao赛事可变参数) |
| `PengTimeoutSec` | 碰/明杠响应窗口，默认 1 秒，固定走满 |
| `ChiTimeoutSec` | 吃响应窗口，默认 1 秒，固定走满 |
| `DiscardTimeoutSec` | 出牌窗口，默认 3 秒 |
| `StartAt` | 开赛时间，Unix 秒 |
| `RegisterDeadlineAt` | 报名截止，Unix 秒；0 表示无截止 |
| `Description` | v8 新增的赛程自由文本；可空、多行，只用于展示和记录，不应作为策略结构化输入 |
| `OnlineConfirm` | v13 新增；`true` 表示新建赛事「已确认 ∧ 开赛时刻在线」分桌，缺键或 `false` 表示 2026-09-05 前创建的存量赛（沿用旧分桌）。只影响分桌，不影响动作协议 |

这些配置每个锦标赛都可能不同，严禁在 Bot 中写死。

`M`、Token 和 `Rounds` 是三个不同维度。一个正式参赛 Token 对应一个参赛身份，并按 `/api/me.active_games` 同时维护最多 `M` 个 `GameSession`；每个 `game_id` 再连续运行 `Rounds` 个单局。测试房间为凑齐四个玩家发放 4 个 Token，这 4 个身份共同参与同一批 `M` 个官方场次，不是每场重新发 4 个 Token。

#### `POST /api/tournaments/me/ready`

报名 Token 作用域内直接到位；全局 Token 返回 `400 TOKEN_NOT_SCOPED`。v7 起其语义取决于赛事状态：

- `registering`：海选前到位。
- `stage_open`：晋级者或候补确认下一阶段出席，且每个阶段都要重新确认。
- 名单外：`409 NOT_QUALIFIED`。
- `running / stage_done / finished / void`：`409 TOURNAMENT_STARTED`。
- `closed`：`409 TOURNAMENT_CLOSED`。

#### `POST /api/tournaments/{id}/register`

报名指定锦标赛：

- 开赛前可调用。
- 幂等。
- 校验同时 16 场上限。

#### `POST /api/tournaments/{id}/ready`

指定锦标赛到位，状态语义与 `/api/tournaments/me/ready` 相同：

- 必须先报名。
- 幂等。
- `stage_open` 只允许 `qualified=true` 的晋级者或候补调用。

#### `GET /api/tournaments/{id}`

返回锦标赛详情，包括：

- `status`：v7 起可能为 `registering / running / stage_done / stage_open / finished / closed / void`
- `config`
- 报名与 ready 人数
- `my_games`：跨阶段累计历史，新增场次和决赛加赛会追加
- 实时 `ranking`：含 `user_id / total_score / place_points / god_count / games_played / rank`
- `voided` 原因
- 开赛后阶段字段组：`stage / stage_status / stage_crashed / qualified / qualify_role`

仅该锦标赛参赛者可查询。

v7 阶段字段：

| 字段 | 含义 |
| --- | --- |
| `stage.no` | 当前阶段号 |
| `stage.role` | `qualify` 晋级轮或 `final` 决赛 |
| `stage.total` | 当前推断阶段总数；动态降档后可能缩小 |
| `stage.name` | 当前阶段显示名 |
| `stage_status` | `open / running / done` |
| `stage_crashed` | `true` 表示本阶段中断并等待重赛 |
| `qualified` | 当前 Token 是否具有本阶段确认资格 |
| `qualify_role` | `finalist / backup`，分别表示晋级者和候补；阶段 1 通常为空 |

重要语义：

- `stage_open` 和 `stage_done` 期间 `active_games` 为空是正常状态，不能据此退出。
- `finished / closed / void` 才是赛事终态。
- 阶段 2 起 `ready_users` 固定返回 0，不能推断实时确认人数。
- `games_played` 每个阶段清零，实际按完成的单局数累计；不能把它当整场赛事进度。
- 平台中断时会出现 `stage_done + stage_crashed=true`；本阶段旧成绩作废，同名单重新确认后重赛。
- v13 新建赛事：`ready_users / stage_ready_count` 仍是「已确认累计」，不是分桌预测——分桌另受开赛时刻在线过滤，客户端不得据此推断同桌或晋级概率。
- v13 新建赛事在线要求：空转期（`registering / stage_open / stage_done`）没有 SSE 可挂，必须对 `/api/tournaments/{id}` 等本赛端点保持轮询间隔 ≤90s（建议 ≤60s），否则开赛时刻会被判离线剔除。本 bot 空转期以 2s 间隔轮询，天然满足；多赛并行时按赛核对各 bot 进程存活。

多阶段赛制、排序和决赛加赛的完整事实见[官方赛事流程](./official-tournament-flow-2026-09-03.md)。

### 2.3 对局状态

#### `GET /api/games/{id}/state?seq=N`

长轮询状态及事件流接口。

- `seq=0`：返回权威全量快照。
- `seq=N`：返回序号 N 之后的增量事件。
- 30 秒内没有新事件：返回 `{"pending": true}`。
- 事件自带 `seq`，客户端必须检查连续性。
- 响应含 `gap: true` 或发现序号缺口：立即用 `seq=0` 重建。
- 动作返回 409：也应使用 `seq=0` 重建。
- 快照是规范真相：`客户端状态 = 最近全量快照 + 连续增量事件`。

v2 起快照**不再返回 `allowed_actions`**。客户端必须自己判定动作是否合法。

已确认的关键快照字段：

| 字段 | 含义 |
| --- | --- |
| `seat` | 本人座位 0-3；观赛视角为 -1 |
| `phase` | `deal｜draw｜response_peng｜response_chi｜settled｜finished` |
| `turn` | 当前行动座位 |
| `responding_seats` | 当前响应窗口有权响应的座位集合 |
| `drawn_tile` | 仅本人刚摸到的牌 |
| `my_hand` | 本人手牌 |
| `dealer` | 庄家座位 |
| `round_no` | 当前局号 |
| `wall_remaining` | 牌墙剩余 |
| `scores` | 四家当前积分 |
| `last_discard` | 最近弃牌 |
| `discards` | 四家牌河 |
| `melds` | 四家副露 |
| `hand_counts` | 他家剩余手牌张数 |
| `god.baotou` | 本人是否处于爆头状态 |
| `god.chain_count` | 本人飘/杠动作链次数；断链后清零 |
| `god.catch_play` | 全局是否存在抓打圈，不等于本人受限 |
| `god.god_discarder_seat` | v26 新增，当前圈主座位 0–3；无圈为 -1。仅最新弃白者豁免；旧报文缺字段时按已证明的连续公开事实恢复，不能默认自己豁免 |

已观察到的事件通用结构：

```json
{
  "seq": 123,
  "type": "tile_discarded",
  "seat": 2,
  "tile": "5w",
  "data": {},
  "ts": 1756771200
}
```

官方门户明确处理的事件类型包括：

- `tile_drawn`
- `tile_discarded`
- `chi`
- `peng`
- `gang`，`data.kind` 可区分 `an｜ming｜bu`
- `timeout`，`data.kind` 为 `discard｜response`
- `round_ended`
- `game_ended`

事件枚举可能继续扩充，解析器应允许未知事件透传并记录，不能因为未知 `type` 直接崩溃。

私有信息规则：玩家事件流只包含自己的摸牌，他家手牌不会在实时玩家接口中出现。

#### `GET /api/games/{id}/notify`（v12 起，可选 SSE 通知流）

服务器推送「状态已变化」信号，替代高频轮询 `/state` 来发现他人动作；Bearer 认证，观赛者 403。

- 连接即收初始帧 `{"seq": N}`（N = 当前事件水位，重连对齐点）。
- 此后每次状态变更推 `{"seq": 新水位}`；帧只含 seq，不含牌面/动作内容——牌面仍须按需 `GET /state` 领取。
- 每 30s 一行 `: keepalive`；场终/死场推 `{"seq":N,"closed":true}` 后关流，客户端应重连对齐或拉终态。
- 上限每用户 32 并发连接（超限 429），不占用 `/state` 的 16/s 频率额度。
- 游标纪律：初始帧的 seq 是包含式水位，不可直接当轮询游标；收到帧后若高于本地已消费 seq 且无缺口，用 `GET /state?seq=本地游标` 拉增量；游标未知/落后超 256/跨局用 `seq=0` 拿全量快照。

工程决策（2026-09-06 修订）：生产组合根仅使用 `/state` 长轮询与阶段边界查询，暂不接 SSE；低层通知客户端保留供以后评估。SSE 不是识别无事件阶段切换的充分条件，不能代替边界查询。旧配置请求开启 SSE 时在运行 manifest 标注 requested/effective 差异。

### 2.4 提交动作

#### `POST /api/games/{id}/action`

基本结构：

```json
{
  "action": "discard|chi|peng|gang|hu|pass",
  "tile": "1w"
}
```

吃牌可指定使用的两张手牌：

```json
{
  "action": "chi",
  "tile": "3w",
  "tiles": ["1w", "2w"]
}
```

- `tiles` 乱序容忍、按等价组合匹配。
- 不传 `tiles` 时，服务端选择第一组可行顺子。
- 服务端只负责验证：合法即执行，不合法返回 `409 INVALID_ACTION`。
- 响应窗口的“已经响应”状态需要客户端本地跟踪；重复提交动作或 `pass` 会返回 409。
- 碰、吃、杠后，在下一次摸牌之前提交 `hu` 会返回 409。

v2 动作判定下限：

- `phase=draw && turn=seat`：可以考虑出牌、自摸胡、杠。
- `phase=response_peng && seat∈responding_seats`：可以考虑碰、明杠、`pass`。
- `phase=response_chi && seat∈responding_seats`：可以考虑吃、`pass`。
- `god.catch_play=true` 且 `god.god_discarder_seat!=seat`：本人出牌只能打 `drawn_tile`，不能吃、碰、明杠或补杠，仍可暗杠和自摸胡；圈主不受这项限制。吃碰仍须有当前 `phase/responding_seats` 授权，不能凭圈主身份伪造窗口（v26）。
- 最终合法性仍需本地完整杭麻规则引擎判定，不能只依赖上述阶段判断。

牌码：

```text
1w-9w    万
1b-9b    筒
1t-9t    条
东南西北中发白
```

白板是财神。

### 2.5 测试房间赛后数据

测试房间是 `kind=test` 的四人单阶段环境，可随时创建并配置 `M`、`Rounds`、底分和动作窗口。创建后获得 4 个测试参赛 Token：每个 Token 都应启动一个参赛者运行单元，而每个运行单元再按 `active_games` 并发管理最多 `M` 个场次。房间完成后四个 Token 再次各 `ready` 可开启下一次单阶段运行；这不等同于正式赛事的多阶段晋级。

#### `GET /api/test-rooms/{id}/games`

免认证。返回该测试房间的对局列表，按 `batch` 升序：

```json
[
  {"batch": 1, "game_id": "g_xxx", "status": "finished"}
]
```

#### `GET /api/test-rooms/{id}/games/{batch}/events`

免认证。返回完整赛后数据：

- `blocks`：按块保存的完整事件流，包含四家开局手牌 `start_hands`。
- `rounds`：顶层结果摘要，原文完整保留。本地处理（2026-09-07修正）：不按摘要条数决定单局数量，不直接用同编号摘要覆盖事件块；所有单局取`blocks`中的`round_ended`，摘要比较单独记录。实时快照`scores`为累计积分，`round_ended.data.scores`为单次变化，不能只凭同名字段混用。正式导入和赛后诊断均已修复，见[多来源核对、数据重建与验证](../review/official-deep-diagnosis-2026-09-07/repair-completion.md)。
- 进行中场次：`403 GAME_NOT_FINISHED`。
- 房间或 batch 不存在、房间删除：404。
- 限速：5 次/秒/IP。
- 响应声明 `Cache-Control: no-store`。

房间 ID 相当于赛后数据凭证，不应公开分享。删除房间会级联删除对局与事件数据。

### 2.6 自动匹配（`POST /api/match`，v12 起，v13 全自动语义，v15 默认配置上调）

平台新增自由对战自动匹配池（`kind=auto`）。本端点**仅接受全局 Token**（`POST /api/users` 注册所得；报名 Token → `400 TOKEN_NOT_SCOPED`）。

流程：`POST /api/match` → 服务端从自动匹配池按「就绪席多、开赛早者优先」选房入席，无兼容候选则自动建房并作为首位入席 → 成功返回 `{room_id, config, round_no}` → 之后用同一全局 Token 照常参赛（`GET /api/tournaments/{room_id}` 的 `my_games` 发现 `game_id`、`/state` 轮询、`/action` 出招）。等待期重复调用幂等返回原房，不会双房双席。

关键语义：

- 请求体可选 `{"M":10,"Rounds":8}`（小写键亦收）声明**可承受上限**；缺省/键 ≤0 = 不限。
- v15 起服务默认配置为 **M=10 / Rounds=8**：显式声明上限低于默认（M∈1..9 或 Rounds∈1..7）→ **永久 404 `NO_ROOM_AVAILABLE`**（不重试）；无 body 恒不触发。
- 满 4 人即开 **M=10 场并发对局 × 每场 8 局**（同一 4 人，座次逐场重洗，最晚场终后结算）——单会话样本 80 手/人，需按 10 桌并发核对轮询/动作节奏。
- 整场打完（`finished` 约 60s 宽限）自动房自动关停（`closed`），此后该房玩家 API 一律 404；赛果以最后一次 `/state` 终局快照与门户复盘为准；想再打重新调 `/api/match`（每次新会话新房）。
- 限速 10 次/分/用户；自动房在途上限 50（`409 MATCH_BUSY` 只挡建房、不挡入席）；自动房占 `config.M`（默认 10）格 16 场记账。
- 自动房唯一入席入口是 `/api/match`：对其玩家 API 直连 `register/ready` → `409 AUTO_MATCH_ONLY`（在册参与者重复直连亦 409）。
- 16 场上限：`409 MATCH_LIMIT_REACHED`（register/ready 与 match 同码）。

工程状态与后续决定（2026-09-05）：当前已合入的运行入口仍**不支持全局 Token**（initialize 按 `TARGET_MISMATCH` 拒绝），不调用 `/api/match`。用户已明确委派其接入设计，新增能力按[parallel-v1](./implementation/parallel-contracts.md)和[自由赛开工指南](./implementation/free-match-start.md)开发，尚未实现。旧赛事/测试房间模式保持原作用域和流程；自动匹配的全局身份、入席副作用、每分钟配额及 M=10 容量需单独验收。

## 3. 公共辅助 API

### 3.1 `GET /portal/api/guide/version`

免认证，限速 5 次/秒。返回：

```json
{
  "version": 15,
  "updated_at": "2026-09-05",
  "changes": [
    {
      "version": 15,
      "date": "2026-09-05",
      "type": "breaking|added|changed",
      "summary": "...",
      "detail": "..."
    }
  ]
}
```

启动策略：

1. 代码内声明 `KNOWN_GUIDE_VERSION=30`，但 v15 之后的 breaking 仍按完整条目指纹逐项审查。v25 的两摊吃限制已实现；v24 仅在已审查的赛事令牌与自动匹配路径放行，后者将 `PORTAL_BINDING_REQUIRED` 明确报为身份不匹配；v29 的全服功能开关同样按指纹放行，`auto_match` 与 `ready` 各自把 `FEATURE_DISABLED` 报为"平台已关闭该功能"的永久终态（该码必须在 `KNOWN_OFFICIAL_CODES` 白名单内，否则会被脱敏成 None 而使分支失效）。启动及阶段边界都检查未知条目，同版本改写／新增和未来未知 breaking 仍拒绝，不能只比较顶层数字。
2. Bot 启动、报名/ready 之前调用一次版本接口。
3. 只要出现未审查的 breaking 条目，就禁止进入新赛事并报警，包括同一版本中被新增或改写的条目。
4. 已开始的赛事不要每个动作重复检查版本；在阶段边界重新检查一次，并记录启动与阶段开始时版本，确保阶段尝试可追溯。
5. 保存完整变更响应，便于回放时解释行为差异。

v14 新增姊妹端点 `GET /portal/api/guide`（同样免认证、每 IP 5/s）：返回 `{version, updated_at, format, content}`，`content` 为与门户「接入指南」Tab 同源的完整接入指南正文（对战规则 / API 参考 / 最小 Bot）；`format` 缺省 `html`，`?format=text` 返回剥离标签的纯文本（LLM/终端友好）。本端点用于文档同步与人工核对，运行时版本自检继续使用 `/guide/version`。

### 3.2 `POST /portal/api/tools/fan-calc`

免认证，10 次/秒/IP，纯计算、无状态变更。计算口径与对局一致。

请求：

```json
{
  "hand": ["1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东"],
  "draw": "东",
  "chain": {"count": 0, "piao": 0},
  "base": 1
}
```

约束：

- `hand` 恰好 13 张。
- `draw` 恰好 1 张。
- `chain.count` 为 0-6，每个动作 ×2；这是 v6 起的工具约束。
- `chain.piao <= chain.count`。
- 手牌保留白板数与 `chain.piao` 之和不能超过 4。
- `base` 为 1-10000，默认 1。

响应示例：

```json
{
  "hu": true,
  "baotou": false,
  "fan": 1,
  "detail": ["平胡"],
  "scores": {
    "dealer_hu": {"win": 24, "lose": [8, 8, 8]},
    "nondealer_hu": {"win": 10, "lose": [8, 1, 1]}
  }
}
```

错误：

- `400 INVALID_INPUT`
- `429 RATE_LIMITED`

该接口适合：

- 本地规则引擎的金标准对拍测试。
- 牌谱结算复核。
- 生成规则测试集。

不适合在 1 秒/3 秒实时关键路径上高频依赖；网络异常时必须使用本地规则引擎。

## 4. Portal 会话 API（前端观察所得，非 Bot 稳定契约）

以下接口从官方门户前端源码观察到，使用网页登录会话，不属于 §2 的玩家 API 契约：

| 方法 | 端点 | 用途 |
| --- | --- | --- |
| GET | `/portal/api/me` | 当前门户用户 |
| GET | `/portal/api/tournaments` | 赛事大厅 |
| POST | `/portal/api/tournaments/{id}/register` | 门户报名并显示一次 Token |
| POST | `/portal/api/tournaments/{id}/qualify` | 门户在 `stage_open` 确认晋级/候补资格；玩家 Bot 仍使用 `/ready` |
| POST | `/portal/api/tournaments/{id}/token` | 重新生成参赛 Token，旧 Token 失效 |
| GET | `/portal/api/tournaments/{id}` | 门户锦标赛详情 |
| GET | `/portal/api/tournaments/{id}/ranking` | 实时排名 |
| GET | `/portal/api/games/{id}/snapshot` | 门户观战快照，前端约 1.5 秒轮询 |
| GET | `/portal/api/games/{id}/events` | 门户赛后复盘 |
| GET | `/portal/api/test-rooms` | 测试房间列表 |
| POST | `/portal/api/test-rooms` | 创建测试房间 |
| GET | `/portal/api/test-rooms/{id}` | 测试房间详情/实况 |
| POST | `/portal/api/test-rooms/{id}/rename` | 修改测试玩家名 |
| POST | `/portal/api/test-rooms/{id}/tokens` | 重新生成四个 Token |
| POST | `/portal/api/test-rooms/{id}/close` | 关闭房间 |
| POST | `/portal/api/test-rooms/delete` | 批量删除已终结房间及数据 |

创建测试房间的前端请求字段：

```json
{
  "m": 10,
  "rounds": 1,
  "base_score": 1,
  "you_cai_bi_kao": false,
  "peng_timeout_sec": 1,
  "chi_timeout_sec": 1,
  "discard_timeout_sec": 3,
  "timeout_min": 30
}
```

Portal API 仅用于人工操作或理解平台行为；Bot 不应依赖其 Cookie 会话和未公开响应结构。

v8 起大厅行和门户赛事详情新增 `description`；玩家接口的 `config.Description` 同值。赛事名称和描述可能在任意阶段由管理员修改，客户端必须允许变化。

## 5. 服务端时间模型

### 5.1 三类时钟

需要区分三种完全不同的时间：

1. **动作窗口**：决定是否超时，来自锦标赛 config。
2. **长轮询挂起**：最多 30 秒，只是等待事件，不是思考时间。
3. **客户端内部预算**：必须小于剩余动作窗口，包含网络、排队、推理、验证和提交。

不能把 HTTP 请求的 35 秒客户端超时误认为动作允许思考 35 秒。

### 5.2 摸牌与出牌

```text
服务端进入 draw，turn=本座位
    │
    ├─ 可自摸胡：客户端可 hu，也可弃胡继续行动
    ├─ 可杠：客户端可 gang
    └─ 必须在 DiscardTimeoutSec 内完成行动
            ├─ 正常提交：执行动作
            ├─ 超时且可胡：服务端自动 hu
            └─ 超时且不可胡：服务端自动打最右一张牌
```

默认 3 秒不等于可靠可用 3 秒：客户端可能在窗口开始后才收到状态。2026-09-05 测试房间已观察到 `window_deadline_ms`（Unix 毫秒），2026-09-06 修复将它用于应用层预算，替代原先仅按接收时刻给完整时长的近似。

官方截止转换为本机单调截止，同窗刷新只能收紧；缺字段/增量未携截止时明确标记估计，不复用旧阶段截止。内部预算包含排队、计算、复核和发送余量。部署主机时钟偏差以及请求尾延迟仍需实际运行验证，单调时钟只能避免本地后续墙钟调整延长期限。

### 5.3 弃牌后的响应窗口

官方优先级：碰（含明杠）窗口先于吃窗口。

```text
tile_discarded
    ↓
response_peng，持续 PengTimeoutSec，固定走满
    ├─ 有效碰/明杠：按规则进入动作后的流程
    └─ 无人执行
          ↓
response_chi，持续 ChiTimeoutSec，固定走满
    ├─ 有效吃：吃牌玩家进入出牌流程
    └─ 无人执行：下家摸牌
```

“固定走满”是平台防时间侧信道设计。即使玩家很早 `pass`，服务端也不会通过提前切换阶段暴露其决策。事件中的 `timeout(kind="response")` 表示“窗口走满”，不是玩家失联；不要计入模型超时率。

吃/碰默认只有 1 秒，不能在窗口打开后才启动多 Agent 讨论。策略应在其他玩家行动期间预计算；窗口到达后只做合法性复核、缓存查找和串行动作尝试。通常一次成功即结束；只有官方明确拒绝且刷新确认同窗仍开放时，才按原预算换下一候选。

### 5.4 抓打圈

财神可主动打出。打出财神所触发的抓打圈中：

- 最新弃白者为圈主，可手切、吃、碰、明杠、补杠；吃仅限上家，仍最多两摊。
- 其余玩家只能摸切，不能吃、碰、明杠、补杠；仍可暗杠和自摸胡。
- 白板本身不能被吃、碰、杠。任何人再弃白（包括被迫摸切白）都原子接管圈；原圈主随即失去豁免。
- 圈主吃碰保留当前链；满足既有财飘条件时再打白续飘。圈主打非白结束圈并断链；他人打非白、摸牌或杠补不提前结束圈。

以上为 v27 全文 §1、§2.1 的 v26 修订。v24 曾出现圈主也不开窗的平台行为，已由官方修复；旧轨迹只说明历史版本。圈主权限与当前动作窗口须同时成立，`god.catch_play` 不能单独决定本人限制。

### 5.5 长轮询与并发

- 单次 `state` 长轮询无事件时最多挂起 30 秒。
- `/state` 频率上限：16 次/秒/用户，跨场次共享；长轮询请求同样计次。此处按 2026-09-06 抓取的指南 v18 更新（v11 已从 8/s 放宽），见[本地原文](../review/official-adapter/chain-rate-alignment/guide.txt)。SSE 不占此额度，动作 POST 不使用这项 state 专属额度。
- 同一用户并发挂起轮询：最多 32 个。
- 每个用户同时参赛场数：最多 16；实际还受锦标赛 `M` 限制。

正确并发模型是“每场一个异步任务和一个独立 seq”，而不是按 `active_games` 逐场打完：

```text
Supervisor
  ├─ GameTask(g1): long-poll → reduce → decide → act
  ├─ GameTask(g2): long-poll → reduce → decide → act
  └─ ... 最多 M/16 场
```

每场适配器必须独立保存：

- `last_seq`
- 全量快照和本地衍生状态
- 当前 phase/turn/responding_seats
- 当前动作窗口、在途提交和模糊结果封锁状态
- 当前决策任务及内部截止时间
- API/指南版本

### 5.6 409 与竞态恢复

409 不一定是规则代码错误，也可能是窗口刚关闭或其他玩家动作改变状态：

```text
POST action → 409 INVALID_ACTION
    ↓
停止重放原动作
    ↓
GET state?seq=0
    ↓
替换本地状态
    ↓
若同一 WindowKey 仍要求本人行动，排除已拒绝动作并按原截止时间重新计算；否则继续长轮询
```

不能无条件重试同一动作，否则会在 1 秒窗口内制造重试风暴。409 是官方明确拒绝，可以在权威刷新后换候选；POST 超时、断连或无法确认的 5xx 是结果不确定，必须进入 `AMBIGUOUS` 并封锁同一窗口，二者不能混用。

## 6. 推荐客户端时间预算

### 出牌窗口默认 3 秒

| 环节 | 预算上限 |
| --- | ---: |
| 收包、解析、状态归并 | 100 ms |
| 本地合法动作与规则计算 | 100 ms |
| 牌效/危险度候选评分 | 150 ms |
| 可选快速模型或有界搜索 | 1000-1400 ms |
| 校验、提交、必要的状态重建 | 300-500 ms |
| 安全余量 | 至少 700 ms |

在内部截止到达时立即取消增强计算，提交确定性保底动作。

### 吃/碰窗口默认 1 秒

建议全流程控制在 200-300 ms：

1. 读取预计算决策。
2. 用最新状态重新校验。
3. 串行提交首选；只有明确拒绝且仍有预算时才降级下一候选。

不要依赖在线 LLM，不要等待多 Agent 投票结束。

## 7. 官方 Demo 的使用边界

仓库同时保存当前多阶段 Demo 与 v2 历史样例：

- `references/official_minimal_bot_v7.py`：2026-09-03 门户当前示例，多阶段主循环为 v7 协议。
- `references/official-guide-version-v8.json`：2026-09-03 完整版本接口响应。
- `references/official_minimal_bot_v2.py`
- `references/official-guide-version-v2.json`

v2 Demo 没有多阶段主循环，**不能作为当前参赛入口**。v7 Demo 已改为按 `status` 循环：`running` 处理活跃场次、`stage_open` 重新 `ready`、`stage_done` 等待推进，并持续发现决赛加赛的新 `game_id`。两者都只是协议示例，正式实现仍应使用并发场次监督、版本门禁和仅限固定赛事地址的 `tls_verify=false` 配置。

它适合确认：

- Bearer 请求形式。
- 报名、ready、等待开赛流程。
- `seq=0` 快照和增量长轮询。
- 409 后重建快照。
- v2 自研动作判定的最小字段。

它**不适合直接参赛**：

1. `for active_games: play(game)` 是逐场串行，无法处理多场并发。
2. 429 后固定睡眠 2 秒，可能直接错过 1 秒/3 秒窗口。
3. 不会主动判胡，依赖服务端超时自动胡。
4. 出牌只打第一张，响应窗口永远 pass。
5. 没有在启动时执行指南版本自检。
6. 没有真正维护“本窗口已经响应”的状态。
7. v2 历史副本和当前 v7 Demo 都把一批场次串行执行；正式客户端仍必须并发监督每个场次。

正式客户端应把 Demo 视为协议样例，而不是框架或策略基线。

## 8. 常见错误与恢复策略

| HTTP | 错误码 | 含义 | 推荐处理 |
| --- | --- | --- | --- |
| 400 | `TOKEN_NOT_SCOPED` | 全局 Token 调用了 `/me/rules` 或 `/me/ready` | 改用报名 Token 或显式锦标赛 ID |
| 401 | `UNAUTHORIZED` | Token 无效或被重新生成后吊销 | 停止相关任务并报警，不循环重试 |
| 403 | `FORBIDDEN` | 无赛事/比赛访问权 | 检查 Token 作用域和 game_id |
| 403 | `GAME_NOT_FINISHED` | 试图读取进行中场次完整数据 | 等待比赛结束 |
| 404 | `TOURNAMENT_NOT_FOUND` | 锦标赛不存在 | 停止该赛事任务 |
| 404 | `GAME_NOT_FOUND` | 对局不存在 | 从 `/api/me` 重新发现 active_games |
| 409 | `INVALID_ACTION` | 动作失效或不合法 | `seq=0` 重建；同窗仍开放时排除原动作并按原预算降级，否则结束旧窗口 |
| 409 | `NOT_QUALIFIED` | `stage_open` 中当前身份不在晋级或候补名单 | 停止为该身份确认；记录正常淘汰，不做故障重试 |
| 409 | `TOURNAMENT_STARTED` | 当前不在可报名/确认状态 | 刷新赛事状态；不要把它一律当作整赛已经开始 |
| 409 | `TOURNAMENT_CLOSED` | 赛事已关闭 | 停止该赛事任务 |
| 409 | `NOT_REGISTERED` | 阶段 1 到位前尚未报名 | 仅在 `registering` 中先幂等报名再到位 |
| 409 | `MATCH_LIMIT_REACHED` | 达到同时 16 场上限 | 不再创建/加入更多比赛 |
| 404 | `NO_ROOM_AVAILABLE` | 自动匹配（`/api/match`）无可用房：显式上限低于服务默认（M=10/Rounds=8）为永久条件；或建房后入席失败的兜底瞬态 | 永久条件改上限或放弃、不重试；瞬态按 message 判定后自重试（本项目不调用此端点） |
| 409 | `AUTO_MATCH_ONLY` | 对自动匹配房玩家 API 直连 register/ready（自动房唯一入席入口是 `/api/match`） | 自动房不走 register→ready 流程（本项目不进入自动房） |
| 409 | `MATCH_BUSY` | 在途自动房达 50 上限且无半空房可入（只挡建房、不挡入席） | 延时后自重试（本项目不调用此端点） |
| 429 | `RATE_LIMITED` | 超频或并发挂起超限 | 带抖动退避；动作窗口内优先本地兜底，不能固定睡 2 秒 |

## 9. 关键变更时间线

截至 2026-09-05，当前指南为 v15。v7–v8 为多阶段/赛程变更，v9–v11 为限速与跨局轮询调整，v12–v15 为 SSE、分桌机制、指南全文端点与自动匹配机制（官方变更日志对 v12–v14 回溯扩充了自动匹配条目，2026-09-05 二次同步时一并收录）。

### 9.1 v7/v8（截至 2026-09-03）

相对仓库历史 v2 快照，必须优先完成以下迁移：

- v7：顶层新增 `stage_open / stage_done`，阶段间 `active_games` 为空不代表结束。
- v7：`ready` 在每个新阶段表示出席确认，新增 `NOT_QUALIFIED`。
- v7：新增 `stage / stage_status / stage_crashed / qualified / qualify_role`。
- v7：`games_played` 改为当阶段按单局累计，每阶段清零。
- v7：排名新增 `place_points / god_count`；晋级轮按三键排序。
- v7：决赛同分自动追加新场次，无上限；必须持续发现新 `game_id`。
- v7：赛制按到位人数动态生成并可能降档，不能写死固定四阶段。
- v8：增加 `Description/description` 自由文本；属于兼容新增，但要允许中途修改并留档。

仍需保留的基础 breaking 兼容测试：

- v2：快照移除 `allowed_actions`，动作判定全部由客户端实现。
- v1：碰后、摸牌前禁止胡牌。
- v1：番数算法重构，旧得分期望模型失效。

新增能力：

- v2：吃牌支持 `tiles` 指定组合。
- v2：快照增加本人 `seat`。
- v1：`fan-calc`。
- v1：报名 Token 作用域直达 rules/ready。
- v1：测试房间完整赛后数据 API。

### 9.2 v9–v11（2026-09-03～09-04）

- v9：测试房间数据 API 限速按房间分桶（每房间 5/s + 每来源总量 1000/s 兜底），消除跨房间误伤。
- v10：跨局边界轮询——局终后继续用上一局 seq 轮询立即返回新局全量快照（`gap:true`），不再挂起至庄家出牌超时。
- v11：`/state` 轮询限速放宽 8/s → 16/s（每用户聚合，跨局共享一桶；并发挂起 ≤32 不变）。

### 9.3 v12–v15（2026-09-04～09-05）

- v12（added）：`GET /api/games/{id}/notify` SSE 通知流；帧只含 seq。本阶段不采纳（见 §2.3 工程决策），旧轮询不受影响。
- v12（added，回溯扩充）：玩家 API 新增 `POST /api/match` 自动匹配入席（仅全局 Token）；测试房间创建支持 `match_seats`（门户侧）；门户「我的 AI 身份」昵称 + 全局令牌轮换。
- v13（breaking，已审查）：新建赛事分桌修复——报名=意向，分桌实到 = 开赛时刻「已确认 ∧ 在线」（在线 = 任意已认证请求 90s 内触达）；按实到人数降档、不足 4 作废；`config.OnlineConfirm=true` 标记新建赛事，存量赛（缺键/`false`）沿用旧分桌；门户报名不再自动 ready（玩家 API 不变）；空转期必须 ≤90s 轮询本赛端点。本项目玩家 API `register→ready` 流程与 2s 空转轮询天然兼容，仅需解析并审计 `OnlineConfirm`。
- v13（changed，回溯扩充）：`POST /api/match` 改全自动语义（自动建房与入席一体）；新增 `404 NO_ROOM_AVAILABLE` 与 `409 AUTO_MATCH_ONLY / MATCH_BUSY / MATCH_LIMIT_REACHED`。
- v14（added）：`GET /portal/api/guide` 免认证全文端点（与门户「接入指南」Tab 同源，`?format=text` 给 LLM/终端），根治门户页与接口文档双份漂移。
- v14（added，回溯扩充）：门户新增 `GET /portal/api/leaderboard` 自由对战排行榜（三榜，session 认证）与「我的 AI 身份」昵称修改——门户 API，玩家 API 契约零影响。
- v15（breaking，已审查）：自动匹配服务默认房配置上调 `M=1/Rounds=2 → M=10/Rounds=8`（满员会话 = 10 场并发 × 每场 8 局）。breaking 面仅限 `/api/match` 显式声明上限低于新默认的调用方（→ 404 `NO_ROOM_AVAILABLE`）；无 body 协议不变；自动房占 `config.M` 格 16 场记账。本项目不调用 `/api/match`、不支持全局 Token，正式赛事/测试房间路径零影响（详见 §2.6 工程决策）。

## 2026-09-06 v17 测试房观察补记

以下为保存的实际响应事实，不能推广为未写入指南的普遍保证；来源及原文校验值见[实测报告](../review/official-adapter/live-validation-2026-09-06.md)。

- 玩家端会收到牌值为空的他家 `tile_drawn`。隐藏牌值不表示事件无效。
- 终局响应可同时含 `snapshot` 和 `events`；只读快照会漏掉 `round_ended/game_ended` 的公开结算事实。
- 公开事件实测含 `tile_discarded.data.catch_play`、`tile_drawn.data.gang_replenish`、`timeout.data.window`，以及终局 `draw/fan/detail/scores/final_scores`。抓打标记对本座位当前 god 的作用范围仍待确认。
- 本批官方牌谱 `rounds` 摘要与 8 个单局事件块按本地同编号假设关联时不一致；此假设尚未确认，不能直接判定官方数据错误。保留原文，核验编号作用域；逐单局结果与整场累计结果分别由`round_ended`和`game_ended.final_scores`交叉核对，不把未知摘要静默改写成“官方结果”。
- 显式碰阶段 pass 与碰阶段等待超时的后续吃资格不能混为一谈。新实现等待真实吃窗口；仍需下一批官方测试验证该路径。

## 2026-09-07 v19—v20 兼容扩展

启动测试房`t_b684d5c3eea4`时重新抓取指南，实际版本为v20。v19的玩家数据变更是`round_ended.data`新增`round_no`（本单局号，1基）和`dealer`（本单局庄家座位0—3），胡牌和流局均提供，取翻庄前的值。变更记录同时说明服务端`rounds`表已修复早期单局缺失及编号错位。本地仍保留事件作为单局结果依据，摘要单独核对；不据此改写旧原文。

v19新增门户胡大牌榜，v20把门户两榜top行数从20增至32；它们不改变玩家状态查询和动作接口。全文差异、原始响应和兼容性回归见[本批版本证据](../review/official-live-b684-2026-09-07/README.md#配置和版本)。本地冻结运行源码不因纯加键修改规则；本批32个真实`round_ended`的新增字段均与对应块一致。

当前观察：该房顶层`rounds`仍缺b1第1单局、b3第7单局两条流局记录，延后重读结果相同；已有30条摘要与事件一致。完整事件中32个单局均在，本地按事件导入32个单局，15049个实时快照的累计积分与逐单局积分变化及场终积分全部对齐。原始复查见[本批验收报告](../review/official-live-b684-2026-09-07/README.md#单局顶层摘要和累计积分)，不据此猜测服务端原因。
