# 自由对战对手排行榜打标可行性（2026-09-09）

**结论：可行。** 官方牌谱 `seats[].user_id` 与门户排行榜行的 `user_id` 是同一脱敏参赛身份标识空间，可赛后直接 join 打标"对手是否为排行榜用户"。两个硬约束：

1. 三个排行榜端点均为门户 OpenID 登录态接口（2026-09-09 实测无登录 401 `UNAUTHORIZED`），玩家 API Bearer Token 不可用，榜单只能经人工/离线辅助拉取；
2. 各榜只暴露 top 32 行（+v27 prev 前 4），"在榜"是强正向信号，"不在榜"强度未知，禁止当负标签。

## 1. 证据链

### 1.1 牌谱侧（官方已确认 + 实测）

- 端点 `GET /api/test-rooms/{id}/games/{batch}/events`（免认证，仅 test/auto 房）：`seats[]` = `{name, user_id}`；auto 房 `name` 为 AI 昵称，"真名绝不下发，昵称缺失为空串"（接入指南 v27 快照，2026-09-09，`doc/references/official-guide-v27.txt`）。
- 实测 `datasets/derived/auto-match-rooms-20260908`（44 房 × 10 场 = 440 份牌谱）：
  - 我方身份 `u_13495c3d79c8`（昵称"中国人能飞"）440 场全部在席，与审计目录 `participants/u_13495c3d79c8/` 一致；
  - 去重对手 53 个；15 个空昵称对手仍有 `user_id`——join 键不受昵称缺失影响。
- 官方明示"前端只按 `user_id === me_uid` 高亮，**禁止按 name 匹配**"（v27 积分总榜 prev 键描述）——打标 join 键必须是 `user_id`。

### 1.2 排行榜侧（官方已确认，指南 v27 + v20 changelog）

| 端点 | 榜 | 行关键字段 | 行数 |
| --- | --- | --- | --- |
| `GET /portal/api/leaderboard?period=all|today|week` | 积分总榜（三期） | `rank/user_id/name/rooms/firsts/score`（v27 prev 描述"与主榜行同形"） | top 恒 32（v20 由 20 升 32） |
| 同上响应 `prev` 键（v27 新增，仅 today/week） | 上期前四 | 行同形 + `me_uid` + `streak` | ≤4 |
| `GET /portal/api/leaderboard/huge-win` | 胡大牌榜 | `detail/count/room_id/game_id/can_replay`；排序 tiebreak `user_id` | top 恒 32 |
| `GET /portal/api/leaderboard/best-game` | 单场分榜 | `score/wins/pinghu/baotou/big/lianzhuang/room_id/game_id`；tiebreak `user_id→game_id` | top 恒 32 |

- 三端点均 OpenID 登录态；2026-09-09 无登录实测：`{"code":"UNAUTHORIZED","message":"login required"}`。
- 榜单数据源 = 自动匹配房（`Kind=auto`）整场完整打完的战绩（finished 计、closed 宽限照计；void/崩溃收敛/强关/测试房/正式赛不计）——即榜单用户就是自由对战同一计分池里官方认证的 top 表现者，"在榜⇒优质对手"的打标语义成立。

### 1.3 审计日志的作用与边界（当前观察）

- 作用：我方座位/身份定位（`participants/<user_id>/`、`authoritative_state.payload.window.seat`）、终局分对拍（`game_finished.final_scores` 与牌谱逐局求和互核）。
- 边界：auto 房玩家面 `GET /api/tournaments/{room_id}` 实测 `ranking: []`（registering 期响应原文见审计 raw），且房间关闭后该端点一律 404——**玩家 API 面不存在 auto 房排行榜**，榜单只能走门户。

## 2. 打标流水线设计（已落地，见 §5）

1. 人工浏览器登录门户，DevTools 保存三榜响应 JSON（或导出门户 Cookie 走一次性离线脚本；门户 Cookie 不入库、不进日志、不进线上进程——与 Token 纪律同规格，符合 `doc/official-platform-api-v2.md` §4"Bot 不应依赖门户 Cookie"）。
2. 离线 join：牌谱 `seats[].user_id` × 榜单 `user_id` 集合 → 打标产物，每行带 `room_id/game_id/seat/user_id/period/rank/score/rooms/firsts/榜单快照时间/guide_version`（沿用 `official/dl-*/source.json` 的 `captured_at_unix_ms + guide_version` 模式）。
3. 标签语义：`on_leaderboard=true` 强正向（官方 top 32）；`false` = 未上榜（强度未知）。训练样本按 true 侧加权，不按 false 侧降权。
4. 时效防错位：today/week 榜滚动、all 榜累积；对历史牌谱打标必须带榜单快照时间，避免"当时在榜、现已掉榜"或反向错位。
5. 模块归属：榜单拉取属人工/离线辅助（`offline` 消费已有牌谱产物），不进线上动作闭环；`adapters` 不新增门户会话依赖。

## 3. 互补信号

- 自建对手强度分：现有 440 场牌谱可按 `user_id` 统计每个对手对局数与终局分分布（前几位：`锅8` 120 场、`秋瑞` 80 场、`玩一下`/腾蛇-5023 各 60 场），与官方榜单交叉验证；官方榜覆盖百人级 top 集，自建统计覆盖我方实际遇到的全部 53 个对手。

## 4. 实捕确认（2026-09-09 首次授权，解除全部待确认假设）

- 五端点均 HTTP 200、top 恒 32 行；积分总榜响应顶层键 `as_of/from/me/period/prev/top`，行字段与官方文档一致；today/week 的 `prev.top` 恒 4 行。
- 胡大牌榜/单场分榜行**均显式返回 `user_id`**（另有 `name/rank/score/at_unix/room_id/game_id/can_replay` 与各榜业务字段），"行无 user_id 则跳过"的兜底未触发。
- 昵称漂移实证：`u_f858b8682094` 本地牌谱昵称"腾蛇-5023"、当前榜单昵称"关灯 天胡九莲宝灯"（同一 user_id）——印证官方"禁止按 name 匹配"；打标产物 `opponent-tags.json` 用榜单名、`game-annotations.jsonl` 用牌谱当时名，两处不同属预期。

## 5. 落地组件（2026-09-09）

| 组件 | 位置 | 职责 |
| --- | --- | --- |
| `scripts/fetch_leaderboard.py` | 正式脚本（离线辅助，定位同 `sync_official_guide.py`） | 用人工导出的门户 Cookie 拉三期积分总榜 + huge-win + best-game 原文，落 `datasets/leaderboard/snapshots/<UTC时间戳>/`（snapshot.json 记录 captured_at/guide_version/各端点状态）；`--min-age-min` 节流；全部 401 → 退出码 3 提示人工重登；失败残证快照不参与节流（下次巡检即重试） |
| `scripts/tag_opponents.py` | 正式脚本（只读本地） | 最新快照 × 牌谱 seats 生成 `opponent-tags.json`（user_id 级标签 + detail）与 `game-annotations.jsonl`（game_id 级座位标注 + strong_opponent_count）；当日/当周实时榜只入 detail |
| `watchdog_cycle.py`（hangma-auto-match skill） | 巡检集成 | 每次巡检自动 fetch（60 分钟节流）+ tag；Cookie 缺失静默跳过，401/失败仅打印提示，不影响盯盘与结算 |
| `.private/portal-session/cookie.txt` | 私有凭证（不入库） | 人工一次性导出的门户 Cookie；裸 Cookie 头 / Netscape jar / JSON 数组三种格式自动识别，绝不打印 |

标签集合：`总榜16强`（all rank ≤16）、`总榜32强`（all rank ≤32）、`昨日榜前4`（today 响应 prev.top）、`上周榜前4`（week 响应 prev.top）、`单场分榜32强`、`胡大牌榜32强`（后两榜官方行含 user_id 时）。当日/当周实时榜不进标签，防切期空榜误标。

## 6. 关于"按 user_id 检索牌谱"的澄清

- 官方**没有**按 user_id 查询牌谱的接口：牌谱按 `room_id + batch` 拉取（`GET /api/test-rooms/{id}/games` 列场次 → `/api/test-rooms/{id}/games/{batch}/events` 拉原文，均免认证、仅 test/auto 房）。
- 本地检索已实现：`game-annotations.jsonl` 即 user_id ↔ game_id 双向索引（由本地牌谱 seats 生成），训练侧按 hands 行的 `game_key.game_id` 关联。
- 官方通路补充：huge-win/best-game 榜单行自带 `room_id/game_id` 复盘导航——拿到榜上强手代表场次 id 后可经免认证端点反查该房全部 10 场牌谱（含四家手牌）。`can_replay` 门禁只控制门户复盘入口渲染，不限制牌谱数据端点。本项目暂不自动化该扩采通路，仅记录可行性。

## 7. 会话有效期与首捕结果（2026-09-09）

- 门户会话 Cookie 名 `majiang_sid`（JWT 形态，载荷 `u/e/n`，`e` = 过期 Unix 秒）。首次导出的会话有效期约 26 天（至 2026-10-05 12:27 CST），"拿到登录态可用很久"成立；是否滑动续期待观察，401 时重新导出覆盖 `.private/portal-session/cookie.txt` 即可。
- 首捕打标结果：41 个榜单标签用户；440 场牌谱中 340 场（77.3%）含榜上对手（总榜16强×240 场、总榜32强×160、单场分榜×270、胡大牌榜×240、昨日榜前4×30、上周榜前4×50）。自由赛对手池与榜单高度重叠（榜单本就从 auto 房战绩计算），但仍有约 23% 场次不含榜上对手——标签语义保持"正向加权"，不作负向筛选。
