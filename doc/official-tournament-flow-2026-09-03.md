# 官方赛事流程与多阶段晋级规则

> 官方来源：`https://10.240.169.190:18080/portal/#flow-stage`  
> 抓取时间：2026-09-03（v8 基线）；2026-09-05 同步至指南 v14（v13 分桌在线过滤见 §6.6）  
> 同步检查：`GET /portal/api/guide/version` 返回 `version=14`、`updated_at=2026-09-05`；多阶段协议本身由 v7 于 2026-09-02 引入，v8 另新增赛程 `description` 字段。完整响应见[官方 v14 指南版本快照](./references/official-guide-version-v14.json)，指南正文见[官方 v14 指南全文](./references/official-guide-v14-content.txt)，当前示例见[官方 v7 多阶段最小 Bot](./references/official_minimal_bot_v7.py)。  
> 证据边界：第 1—6 节记录官方事实；第 7—9 节是本项目的工程分析与建议。

## 1. 结论摘要

新赛制不能再表示为固定的“第一轮前 16、第二轮桌内前 2、第三轮桌内前 2”。正式赛事是一条由**每个阶段开赛时实际到位人数**决定、且可能在阶段间自动降档的动态流程：

```text
报名/海选到位
  → 按到位人数选择赛制档位
  → 海选全场排名（人数大于 4 时）
  → 阶段完成，公布晋级与候补资格
  → 下一阶段重新确认到位
  → 16 强 / 8 强组内前 2
  → 决赛；总得分同分则四人自动加赛，直到 1—4 名无同分
```

对当前架构的最大影响不在麻将出牌规则，而在赛事生命周期、晋级效用和端到端评估：必须新增赛事级监督状态机，并把阶段格式变成数据，而不是把轮数和晋级线写死在策略中。

## 2. 按到位人数生成的阶段结构

系统按开赛时已经确认到位的人数定档；只报名但未到位的人不计入。报名截止后不接受新人，后续阶段也不允许补报。

> v13 起（2026-09-05 后新建赛事）：定档人数 = 「已确认（`ready`）∧ 开赛时刻在线」的实到人数，而不只是已确认数——开赛时刻前 90s 内无任何已认证请求的参赛者会被剔除（详情见 §6.6）。2026-09-05 前创建的存量赛（`config.OnlineConfirm` 缺键或 `false`）沿用旧口径。

| 开赛时到位人数 | 自动形成的阶段 | 晋级方式 |
| ---: | --- | --- |
| 17 人及以上 | 海选 → 16 强 → 8 强 → 决赛 | 海选全场前 16；16 强为 4 组 × 4 人，每组前 2；8 强为 2 组 × 4 人，每组前 2；4 人决赛 |
| 9—16 人 | 海选 → 8 强 → 决赛 | 海选全场前 8；8 强为 2 组 × 4 人，每组前 2；4 人决赛 |
| 5—8 人 | 海选资格轮 → 决赛 | 海选全场前 4 进入决赛 |
| 4 人 | 直接决赛 | 无海选淘汰 |
| 少于 4 人 | 赛事作废 | 不产生名次 |

官方同时说明：阶段数可能因后续确认人数不足而收缩，客户端必须以当前返回的 `status` 和 `stage` 为准，不能根据报名人数预先认定固定轮数。

## 3. 各阶段怎样运行

### 3.1 海选

- 全体到位者参加，是后续取人、候补和分组的唯一全场排序依据。
- 海选按批推进；每批尽量让所有人上桌，每桌 4 人，同桌组合随机，不同批可能再次相遇。
- 某批不足一桌的少数参赛者该批轮空：该批 0 分，不计名次分和白板获取数，但平台会计入参与进度。
- 每位选手同一时点参与的场数 `M` 和每个官方场次的单局数由组委会配置；不能把历史公告中的“每阶段 8 局”写死，运行时以赛事 `config` 与赛程说明为准。

### 3.2 16 强和 8 强

- 每组固定 4 人，组内循环。
- 每组前 2 晋级；组与组之间的分数不互相比较。
- 分组按上一阶段名次进行种子蛇形分组，并尽量避免上一阶段同组者过早再次相遇。

### 3.3 决赛

- 固定 4 人，决赛排名只看决赛阶段累计的总得分。
- 任意两人总得分相同，四人都会自动再打一场，得分继续并入决赛总账后重排。
- 加赛没有场次上限，直到第 1—4 名总得分两两不同；新加赛会产生新的 `game_id`。

## 4. 晋级、候补与逐阶段确认

设下一阶段计划名额为 `G`：

- 上一阶段第 `1..G` 名是晋级者。
- 第 `G+1..2G` 名进入候补池；若上一阶段人数不足 `2G`，其余未晋级者全部列为候补。
- 晋级者和候补进入每个新阶段前都必须重新确认到位，确认不会跨阶段继承。
- 到开赛时刻按“已经确认者中的上一阶段名次”取足名额；确认先后不影响顺序。晋级者漏确认会自动让位给已确认的高顺位候补。
- v13 起（新建赛事）：取足名额前还要过「开赛时刻在线」过滤——空转期必须对本赛端点保持 ≤90s 轮询，否则连上又断开的身份会被剔除（§6.6）。
- 平台不向参赛者公开实时确认人数；不能根据确认人数做策略判断。

异常人数处理：

| 冻结时已确认人数 | 平台行为 |
| --- | --- |
| 少于 4 人 | 整场赛事作废，无最终名次 |
| 4—8 人 | 直接降为 4 人决赛，多余人员按上阶段名次取前 4 |
| 9—16 人 | 降为 8 强规模 |
| 满足原计划 | 按原阶段继续 |

## 5. 成绩和同分判定

### 5.1 晋级轮

海选、16 强和 8 强按下面三个互不相加的排序键依次比较：

1. `total_score`：当前阶段每个单局局分的累计；流局为 0。
2. `place_points`：每个桌赛按本场总得分排位，依次为 `+3 / +1 / -1 / -3`。本场同分时，共享并列名次区间的平均名次分，例如第 1、2 名并列时各得 `+2`。
3. `god_count`：本阶段配牌获得及牌墙摸到的白板总数；白板不能吃碰杠，因此不会重复计数。

三键完全相同时，参赛者页面表述为平台内部确定顺序；API v7 变更说明进一步写明以 `user_id` 字典序兜底。客户端应直接采用平台返回的 `rank`，不要自行覆盖官方排序。

每个阶段的分数独立起算，不带入下一阶段。轮空为 0 分，也不增加名次分和白板获取数。

### 5.2 决赛

决赛只用 `total_score`，不使用 `place_points`、`god_count` 或其他兜底键拆分名次。同分通过继续加赛解决。

官方指出白板获取数包含平台内部的配牌时点，参赛方无法只靠实时事件准确复算，因此赛事 Bot 必须把平台排名值视为权威数据。

## 6. 与 Bot 直接相关的 v7/v8 协议事实

### 6.1 顶层状态机

```text
registering
  → running
  → stage_done
  → stage_open
  → running
  → ...
  → finished

任意时刻还可能进入 closed 或 void。
```

- `stage_done`：当前晋级阶段已经完成，等待组委会推进；不是整场赛事结束。
- `stage_open`：下一阶段确认期，晋级者和候补需要再次 `ready`。
- `finished`、`closed`、`void` 才是需要赛事 Bot 退出的终态。
- 阶段间 `GET /api/me` 的 `active_games` 可能为空；空列表不是退出条件。

工程上还要区分参赛者终态：`stage_open + qualified=false` 或 `ready` 返回 `NOT_QUALIFIED` 时，当前身份已正常淘汰，可以停止该 Token 的 `ParticipantRuntime`；这不表示整个赛事已经进入 `finished/closed/void`。

### 6.2 阶段和资格字段

`GET /api/tournaments/{id}` 在开赛后增加：

| 字段 | 官方语义 |
| --- | --- |
| `stage.no` | 当前阶段编号 |
| `stage.role` | `qualify` 或 `final` |
| `stage.total` | 当前推断阶段总数；降档后会动态缩小 |
| `stage.name` | 阶段显示名 |
| `stage_status` | `open / running / done` |
| `stage_crashed` | 当前阶段是否中断并等待重赛 |
| `qualified` | 当前身份是否在本阶段晋级/候补名单内 |
| `qualify_role` | `finalist` 或 `backup`；阶段 1 通常为空 |

`POST /api/tournaments/{id}/ready` 与 `POST /api/tournaments/me/ready` 在 `stage_open` 中表示本阶段出席确认。名单外返回 `409 NOT_QUALIFIED`；其他非确认阶段通常返回 `409 TOURNAMENT_STARTED`。阶段 2 起 `ready_users` 固定为 0，以免泄露确认人数。

### 6.3 排名、场次发现和版本

- `ranking` 条目包含 `user_id / total_score / place_points / god_count / games_played / rank`。
- `games_played` 在每个阶段开始时清零，实际按已完成单局累计；不能用它与整场规划比较来判断赛事是否结束。
- `my_games` 是跨阶段累计历史；`active_games` 只表示此刻仍在运行的场次。
- 决赛加赛会在 `running` 中追加新 `game_id`，Bot 必须持续发现。
- v8 为赛事详情增加 `description`；适配器应允许未知字段，并把赛程说明保存到运行记录，但策略不能解析自由文本来代替结构化字段。

### 6.4 平台阶段中断

平台服务异常导致阶段中断时，顶层落到 `stage_done` 并设置 `stage_crashed=true`。平台会清空本阶段中断前的成绩和对局，使用相同参赛名单重新安排该阶段，所有人重新确认。旧对局仍可作为故障记录保存，但必须标为作废尝试，不能进入正式训练标签或赛事成绩聚合。

### 6.5 官方测试环境

- **测试房间**：官方门户确认 `kind=test` 保持单阶段，可随时创建，配置同时场数 `M`、每场单局数 `Rounds`、底分和动作窗口；一次发放 4 个测试参赛 Token，并提供完整赛后数据。完成后四个 Token 再次各 `ready` 只是开启下一次单阶段运行，不会产生正式多阶段晋级状态。
- **测试赛事**：赛事方补充提供模拟正式赛事完整流程的测试赛事，用于验证海选、阶段推进、确认和晋级应对。公开玩家指南尚未定义单独的 `test_tournament` 类型或识别字段，以实际 `GET /api/tournaments/{id}` 响应固化其外显协议。
- **正式赛事**：同样读取 `config.M`，一个参赛 Token 按 `active_games` 并发参与最多 `M` 个场次；实际场次数可能在阶段间暂时少于 `M`，因此不能预创建固定数量的场次会话。

当前赛事观察（2026-09-05 抓取，参赛令牌脱敏快照见 [references/official-tournament-t_dee58824c308-2026-09-05.json](./references/official-tournament-t_dee58824c308-2026-09-05.json)）：

- `t_dee58824c308`「9月4日杭麻竞技一测」：`M=10 / Rounds=16 / BaseScore=1 / YouCaiBiKao=false`，205 人报名；`config.OnlineConfirm=false`，属 2026-09-05 前创建的存量赛，沿用旧分桌规则。
- 抓取时 `status=stage_open`、`stage{no=2, role=qualify, total=4}`，第 1 轮（海选）已结算（榜首 `total_score=1703 / place_points=27 / god_count=120 / games_played=160`，与 M=10 场 × 16 局口径一致）；本项目参赛身份 `qualified=false`，已正常淘汰。

### 6.6 v13 分桌在线过滤与「报名=意向」（2026-09-05 起的新建赛事）

官方修复 2026-09-04 正式赛事故（报名后不上线的玩家仍被分桌，真人被配幽灵同桌）后，分桌语义对**部署后新建**的锦标赛改变：

- 报名（含门户报名）只表示意向，不再自动到位；玩家 API `register` 本就不自动 `ready`（不变）。
- 分桌实到 = 开赛时刻（`StartAt` 整点冻结）同时满足「显式到位（`ready`）」与「在线」的参赛者；按实到人数沿用档位表降档，不足 4 直接作废（`no_players`）。
- 「在线」证据 = 该用户任意已认证 Bearer 请求（`GET /api/me`、`/api/tournaments/{id}`、`/state`、POST 动作等）在最近 90s 内触达服务器；开赛前连上又断开的会被自动剔除。
- 判别：`GET /api/tournaments/{id}`（或 `/me/rules`）的 `config` 含 `OnlineConfirm=true` 为新建赛事；缺键或 `false` 为 2026-09-05 前创建的存量赛，全流程沿用旧规则。
- `ready_users / stage_ready_count` 仍是「已确认累计」，不是分桌预测。
- 空转期（`registering / stage_open / stage_done`）没有 SSE 流可挂，必须对 `/api/tournaments/{id}` 等本赛端点保持轮询间隔 ≤90s（建议 ≤60s），否则开赛时刻会被判离线剔除；同一用户报名多赛时按赛核对各 bot 进程存活。
- 服务重启后若开赛时刻已过或邻近（90s 内），冻结自动顺延 ≤90s 给 bot 重连窗口。
- `kind=test` 测试房间全程豁免（满员即开语义不变）。

对本项目的影响：玩家 API `register→ready` 流程不变；`TournamentSupervisor` 空转期以 2s 间隔轮询本赛详情端点（`next_update`），天然满足 90s 在线要求。适配器仅需解析并审计 `OnlineConfirm` 键（`ParsedRulesConfig.online_confirm`），无需改变应用层状态机。

## 7. 对现有架构的影响

| 模块 | 影响级别 | 现有假设失效点 | 应对性改动 |
| --- | --- | --- | --- |
| `adapters/official` | P0，破坏性 | 只认识 `registering/running/finished`；`ready` 只在赛前调用；排名字段较少 | 升级到 v8 契约；解析 `stage*`、资格和三键排名；识别 `NOT_QUALIFIED`；保留未知字段；启动时检查 v7 breaking 变更 |
| `application` | P0，破坏性 | `active_games` 为空或一批结束即可退出；只有 `GameSession` | 新增赛事监督器（`TournamentSupervisor`）；一个 Token 对应一个参赛者运行单元，按 `active_games` 并发维护最多 `M` 个场次；跨阶段确认、发现加赛，并区分参赛者淘汰与赛事终态 |
| `competition` | P1 | 固定“第一轮前 16、第二/三轮前 2”；只评总积分 | MVP 后引入数据化 `CompetitionFormat`、`StageRule` 和 `RankingKey`；海选目标支持前 16/8/4；中间轮支持组内前 2；决赛支持纯总分和加赛终止 |
| `policy` | P1 | 赛事效用只读取单一积分和固定晋级线 | 接收阶段感知的 `CompetitionContext`；将总得分、名次分、白板数及权威 `rank` 纳入效用；不读取确认人数或赛程自由文本 |
| `simulation` | P1 | 只模拟一桌固定长度牌局 | 牌局引擎不改；在离线评估层新增赛事编排壳，模拟海选批次、轮空、组内赛、阶段清零、蛇形分组和决赛加赛 |
| `learning` | P1/P2 | `StageContinuationModel` 只预测四家最终名次；全局线固定第 16 名 | 候选结果模型的局分输出可保持不变；阶段续局特征增加阶段规则和三键账本，并负责名次分/白板不确定性；将 `GlobalCutoffEstimator` 泛化为海选前 `G` 名截线估计 |
| `offline/ingest` | P0/P1 | 牌谱没有阶段尝试和作废语义 | 样本增加赛事/阶段/阶段尝试、排名三键、是否作废；中断重赛前的记录只能用于可靠性诊断，默认排除训练与成绩标签 |
| `offline/evaluate` | P1 | 只跑固定八局、固定四阶段指标 | 增加全赛制档位评估：海选前 16/8/4、组内前 2、候补递补、降档、决赛加赛；统计单位提升到完整阶段或完整赛事 seed |
| `adapters/recording` | P0 | 只记录 `game_id`、最终积分/排名 | MVP 即记录版本/config、生命周期、规范观察、候选、选择原因、耗时、提交结果、三键排名和作废原因；保持非阻塞并移除 Token |
| `hangma` / `kernel` | 低 | 麻将合法动作和结算没有因晋级规则改变 | `hangma` 不改；只在确有跨模块复用时增加稳定的阶段值类型，避免把易变官方 DTO 倾倒进 `kernel` |

## 8. 推荐的模块边界和数据流

`application` 负责“赛事有没有进入下一阶段、是否该确认、有哪些场次要运行”；`competition` 负责“给定结构化阶段规则和可能的结果，这个动作对晋级有多大价值”。两者不能合并：前者包含网络、时钟和副作用，后者必须是可离线复算的纯逻辑。

```text
OfficialTournamentClient
  → TournamentSnapshot（结构化状态、阶段、资格、排名）
  → TournamentSupervisor（生命周期、ready、场次发现、故障隔离）
      → GameSession(game_id) → BotPolicy
      → CompetitionContextCache → CompetitionEvaluator

OfflineTournamentHarness
  → 同一 CompetitionFormat / CompetitionEvaluator
  → SimulationGame + 对手池
  → 完整阶段和完整赛事指标
```

建议 `CompetitionFormat` 由“API 已观察事实 + 版本化官方流程规则”派生，不解析官方 `description` 文本。`target_size/group_advance/ranking_keys/score_resets/overtime_until_unique` 是本地派生字段，并非 v8 同名响应字段：

```python
@dataclass(frozen=True)
class StageRule:
    """一个赛事阶段的本地派生规则；供线上效用和离线评估共用。"""

    stage_no: int                 # 当前阶段编号；以官方响应为准，不由客户端猜测
    role: Literal["qualify", "final"]  # 晋级轮或决赛；决定排序与终止方式
    target_size: int | None       # 海选晋级人数 16/8/4；组内赛或决赛可为空
    group_advance: int | None     # 中间轮每组晋级人数，当前官方规则为 2
    ranking_keys: tuple[str, ...] # 按优先级排列的权威排序键；决赛只含 total_score
    score_resets: bool            # 新阶段是否独立计分；当前官方规则为真
    overtime_until_unique: bool   # 是否同分自动加赛直到完整名次唯一；仅决赛为真
```

## 9. 实施顺序和验收用例

### P0：先保证不会因新流程退赛

1. 版本上限从 v2 提升到 v8，并为 v7 所有 breaking 项增加契约 fixture。
2. 实现 `TournamentSupervisor`：`stage_done` 等待、`stage_open` 幂等确认、`running` 持续发现新场，并区分参赛者终态与赛事终态。
3. 为以下轨迹增加状态机测试：
   - `running → stage_done → stage_open → running`；
   - `stage_open + finalist/backup → ready 200`；
   - `stage_open + qualified=false → NOT_QUALIFIED`；
   - `running + active_games=[]` 不退出；
   - 决赛追加新 `game_id` 后自动创建场次会话；
   - `stage_done + stage_crashed=true` 标记旧阶段尝试作废并等待重赛。
4. 记录三键排名和阶段身份，保证重启后仍可恢复赛事级状态。
5. 正式运行以一个 Token 启动一个 `ParticipantRuntime`；测试房间以四个 Token 启动四个运行单元，每个按 `active_games` 管理最多 `M` 场。
6. 第一阶段审计必须关联生命周期、决策依据、动作提交和最终结果；日志失败不得阻塞动作窗口。

### P1：再修正效用和评估

1. 用数据化阶段规则替换固定轮次分支。
2. 让海选截线估计器接受 `G∈{16,8,4}`，并在排名过旧时降级为保守期望积分策略。
3. 首版由阶段续局估计器处理 `place_points/god_count`；只有同分边界样本表明收益明显时，才扩展候选结果模型的输出，避免因第三排序键重做全部局部网络。
4. 用完整赛事壳评估所有人数档位、轮空、动态降档和决赛加赛。
5. 将训练/验证划分提升到赛事和阶段尝试级别，避免同一赛事跨集合泄漏。

### 仍待赛事方或实际赛程确认

- 正式赛事创建时的到位人数、`M`、`Rounds`、底分和各阶段开赛时间。
- “每阶段 8 局”的旧赛事公告是否仍对本次正式赛事强制成立；程序无论如何应以运行时 `config` 为准。
- 正式赛事牌谱下载端点和中断阶段旧牌谱的可见期限。
- 官方测试赛事的创建方式、Token 发放、外显类型和赛后数据端点。
- 决赛现场网络、硬件和部署限制。
