# 启动脚本实施规范

## 范围

- `run_participant.py`：一个 Token、一个 `ParticipantRuntime`，用于测试赛事或正式赛事。
- `run_test_room.py`：恰好接收四个测试 Token，启动四个隔离子进程；每个子进程继续使用同一个正式运行入口。
- `run_auto_match.py`：自由赛自动匹配入口（parallel-v1）；一个进程恰好持有**一个全局 Token**，默认只完成一个自动房会话（`POST /api/match` 入席 → 等待开赛 → 运行 active_games → 终局收尾 → 退出），完成后默认退出不循环。只解析配置、核对 `mode=auto_match` 并调用 `bootstrap.build_auto_match_runtime`；自动房专用生命周期与协议重试归 `application/auto_match_runtime.py` 与 `adapters/official/auto_match.py`。部署约束：同一全局 Token 同一时刻只能由一个节点的一个进程持有，多节点须使用不同 Token。
- `sync_official_guide.py`：文档同步工具（v14 起官方指南端点免认证）。拉取 `guide/version` 变更日志与 `guide?format=text` 全文到 `doc/references/`，并与 `dto.py` 的 `KNOWN_GUIDE_VERSION` 对比输出基线之后的新变更（breaking 醒目提示）；不携带 Token、不进线上动作闭环。
- `fetch_leaderboard.py`：门户排行榜快照工具（离线辅助，定位同 `sync_official_guide.py`）。用人工导出的门户登录 Cookie（`.private/portal-session/cookie.txt`，不入库、不打印）拉取 `/portal/api/leaderboard` 三期与 `huge-win`/`best-game` 原文到 `datasets/leaderboard/snapshots/`（带 captured_at/guide_version 血缘）；全部 401 时提示人工重登（退出码 3），`--min-age-min` 节流供 watchdog 高频巡检安全反复调用；不携带玩家 Token、不进线上动作闭环。
- `tag_opponents.py`：把最新排行榜快照打标到本地牌谱对手池，只读本地数据。正向标签只用稳定窗口（总榜 32/16 强 + 昨日/上周榜前四 + 单场分/胡大牌榜行含 user_id 时），当日/当周实时榜只入 detail；产出 `opponent-tags.json` 与 `game-annotations.jsonl`（game_id 级，训练侧与 hands 行 `game_key.game_id` 关联）。
- 启动脚本只解析配置、核对模式并调用 `bootstrap.py`，不得实现规则、HTTP DTO、策略或生命周期；同步脚本只做抓取、落盘与版本对比，不得修改 `dto.py` 或文档正文（人工审查后才可更新基线）。

## 第一阶段约束

- 测试房间使用四进程，不做同进程多租户或共享模型。
- 一个身份失败不得主动终止其余三个身份；最终汇总必须清楚标出失败身份。
- Token 可保存在团队约定的私有运行配置，但命令输出、进程标题、错误和审计中必须脱敏。
- 简单进程守护允许有限次数重启；重启后由权威 `/api/me` 和 `seq=0` 恢复，不能复用内存中的提交判断。

## 验收标准

- `M=1/Rounds=1` 冒烟和目标 `M/Rounds` 都能生成四身份独立审计目录。
- 启动时明确显示运行模式、目标赛事、脱敏身份、指南/规则版本和策略版本。
- 测试 Token 不能以正式模式启动，正式 Token 不能以测试房间模式启动。

