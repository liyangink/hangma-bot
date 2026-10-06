# 参赛说明

## 一、参赛程序说明

### 准备

```bash
cd <仓库根目录>
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

# 代理例外：必须与启动赛事的终端相同，否则 guide/version 超时、未报名即退出
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}10.240.169.190"
export no_proxy="${no_proxy:+$no_proxy,}10.240.169.190"
```

```bash
cp configs/participant.example.json .private/participant.json   # 改 mode / token_kind / expected_tournament_id / audit_root
printf '%s\n' '<参赛 Token>' > .private/participant.token      # 单行文件；.private/ 不入版本库
```

Token 三种给法**三选一**：配置内 `token`、`token_env`、命令行 `--token-file`（同时给会直接报错）；
同一 Token 同一时刻只能有一个进程在用。平台地址写在配置里：`base_url` = `https://10.240.169.190:18080`。

### 开始比赛

**有开赛脚本**，赛事走单身份入口 `scripts/run_participant.py`：

| 场景 | 开赛脚本 | 关键配置 |
| --- | --- | --- |
| 测试赛事 | `scripts/run_participant.py` | `mode: test_tournament`、`token_kind: test` |
| 正式赛事 | `scripts/run_participant.py` | `mode: official_tournament`、`token_kind: official` |
| 官方测试房 | `scripts/run_test_room.py` | 四身份、四个 Token；`--once` 打一批就退 |
| 自由赛 | `scripts/run_auto_match.py` | 一个全局 Token，一房结束即退 |

```bash
# 开打（测试赛事 / 正式赛事）
.venv/bin/python scripts/run_participant.py --config .private/participant.json \
  --token-file .private/participant.token

# 开打前用只读接口核对「这个 Token 绑的是哪一场」（不 register / 不 ready）
.venv/bin/python scripts/resolve_tournament.py --token-file .private/participant.token --config .private/participant.json
```

连续自由赛不由单次脚本负责，用当前 watchdog 入口续赛（入口见[研究证据索引](../review/INDEX.md)顶部）。

### 日志怎么看

| 目的 | 命令 | 看什么 |
| --- | --- | --- |
| 单场实时状态 | `.venv/bin/python scripts/monitor_run.py --audit-root artifacts/sessions/<会话> --interval 5` | 进程存活、当前场次与单局、动作与截止 |
| 全量原始审计 | `.venv/bin/python scripts/audit_tool.py watch artifacts/sessions/<会话>` | 每个身份的决策链、提交结果、异常（`--once` 只看一次） |
| 图形界面（只读本机） | `./scripts/run_spectator.sh` → `http://127.0.0.1:8765/` | 牌桌、手牌、决策候选与增量事件 |

落盘位置 `artifacts/sessions/<会话>/audit/runs/<run_id>/`：

- `participants/<身份>/decisions.jsonl`：每次决策的观察、候选、选择、耗时与提交结果
- `raw/*.jsonl`：官方原始报文留痕；`lifecycle.jsonl`：生命周期；`summary.json`：终态汇总
- 连续自由赛的守护日志：所属 watchdog 目录下的 `watch.stdout.log`、`background.stdout.log`

常见问题：`guide/version` 超时未报名 → 代理例外没设；启动报 Token/身份错误 → Token 文件多行或与赛事不符；
报「`--token-file` 与配置内 `token/token_env` 互斥」→ 二选一，别同时给。

## 二、源码地址

```
git@github.com:liyangink/hangma-bot.git
https://github.com/liyangink/hangma-bot.git
```
