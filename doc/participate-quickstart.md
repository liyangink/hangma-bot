# 参赛操作速查（可直接照抄）

**一句话**：程序通过官方 HTTP API 接入平台参赛，共三类入口——**官方测试房间**（4 个 Token，验证接线）、
**单身份赛事**（测试／正式赛事，1 个 Token）、**自由赛**（1 个全局 Token，自动匹配房）。三类只是配置与
Token 不同，命令都是仓库里的固定脚本。所有命令都在仓库根目录执行。

| 场景 | 入口 | Token | 用途 |
| --- | --- | --- | --- |
| 官方测试房间 | `scripts/run_test_room.py` | 4 个测试 Token | 验证协议、规则、M 场并发、时限与恢复 |
| 测试赛事 | `scripts/run_participant.py` | 1 个测试 Token | 验证完整赛事生命周期 |
| 正式赛事 | `scripts/run_participant.py` | 1 个正式 Token | 正式参赛 |
| 自由赛（单次） | `scripts/run_auto_match.py` | 1 个全局 Token | 自动匹配房，一房结束即退出 |
| 自由赛（连续） | 当前 watchdog 入口（见第 4 节） | 1 个全局 Token | 连续续赛实验 |
| 观战（只读） | `scripts/run_spectator.sh` | 无 | 本机看牌桌与决策，不连平台 |

详细口径见[运行与赛后操作](operations.md#2-启动测试房间与赛事)；本文只给可直接执行的命令。

## 0. 一次性准备

```bash
cd <仓库根目录>
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q          # 可选：确认环境完好
```

**代理例外**：参赛客户端会继承系统代理，在 `guide/version` 上超时后就退出。必须在**启动赛事的同一个终端**里执行；
只影响该终端的子进程，不改系统代理。换平台主机时同步改地址。

```bash
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}10.240.169.190"
export no_proxy="${no_proxy:+$no_proxy,}10.240.169.190"
```

**平台地址与安全边界**（写进配置，不要改代码）：

| 字段 | 值 | 说明 |
| --- | --- | --- |
| `base_url` | `https://10.240.169.190:18080` | 赛事内网地址 |
| `insecure_hosts` | 该主机 IP | 仅对该主机在官方适配器内关闭证书校验；不改系统 TLS，不外扩到其他主机 |

**Token 规范**：一个 Token 一个文件、只含一行、放在 `.private/`（不入版本库，不进日志与截图）。
配置里 `token`（内联）／`token_env`（环境变量名）／命令行 `--token-file` **三选一**，同时给会直接报错。

## 1. 官方测试房间（第一次接入走这条）

```bash
mkdir -p .private
cp configs/test-room.example.json .private/test-room.json
```

编辑 `.private/test-room.json`，只需改三处：

| 字段 | 改成 | 举例 |
| --- | --- | --- |
| `expected_tournament_id` | 本次房间 ID | 填实际房间号 |
| `audit_root` | 本次独立审计目录 | `artifacts/sessions/test-room-20261007/audit` |
| `identities[].token_file` | 四个 Token 文件路径 | `.private/qinglong.token` 等 |

写入四个 Token（每行一个，前后不要留空格或多余换行）：

```bash
printf '%s\n' '<青龙 Token>' > .private/qinglong.token
printf '%s\n' '<白虎 Token>' > .private/baihu.token
printf '%s\n' '<朱雀 Token>' > .private/zhuque.token
printf '%s\n' '<玄武 Token>' > .private/xuanwu.token
```

开打一个批次（四个身份各一个隔离子进程）：

```bash
.venv/bin/python scripts/run_test_room.py --config .private/test-room.json --once
```

`--once` 表示每身份收到一次 `tournament_finished` 后退出、不再续报下一批次；也可在配置里写 `max_completed_batches`。
**Ctrl-C / kill 不是「打完这批再停」**：它会把信号转发给子进程并中止当前工作。

另开一个终端旁观（只读本地审计，不发请求）：

```bash
.venv/bin/python scripts/audit_tool.py watch artifacts/sessions/test-room-20261007 --interval 5
```

## 2. 单身份赛事（测试赛事 / 正式赛事）

```bash
cp configs/participant.example.json .private/participant.json
```

| 赛事类型 | 配置改动 | Token |
| --- | --- | --- |
| 测试赛事 | `mode: test_tournament`、`token_kind: test`、填真实赛事 ID | 测试 Token |
| 正式赛事 | `mode: official_tournament`、`token_kind: official`、填真实赛事 ID | 正式 Token |

两种方式任选一种提供 Token（不要同时用）：

```bash
# 方式一：Token 文件
printf '%s\n' '<参赛 Token>' > .private/participant.token
.venv/bin/python scripts/run_participant.py --config .private/participant.json --token-file .private/participant.token

# 方式二：环境变量（配置里保留 token_env，不要加 --token-file）
export HM_PARTICIPANT_TOKEN='<参赛 Token>'
.venv/bin/python scripts/run_participant.py --config .private/participant.json
```

开打前用只读接口核对「这个 Token 到底绑的是哪一场」：

```bash
.venv/bin/python scripts/resolve_tournament.py --token-file .private/participant.token --config .private/participant.json
```

## 3. 自由赛（单次自动房）

```bash
cp configs/auto-match.example.json .private/auto-match.json
```

编辑 `.private/auto-match.json`：`audit_root`、`strategy`，以及 Token——**用了 `--token-file` 就要把配置里的
`token_env` 删掉**（二者互斥，同时存在会直接报 `ValueError`）。

```bash
printf '%s\n' '<全局自由赛 Token>' > .private/free.token
.venv/bin/python scripts/run_auto_match.py --config .private/auto-match.json --token-file .private/free.token
```

**硬约束**：同一个全局 Token 在同一时刻只能有一个实例在跑；默认完成一个自动房会话后退出。

## 4. 自由赛连续续赛（当前实验入口）

连续续赛入口随实验推进变化，**以[研究证据索引](../review/INDEX.md)顶部「当前入口」为准**，不要恢复旧入口。
先查出当前入口目录：

```bash
grep -rn "free_watchdog.py" review/INDEX.md review/vip-route-2026-09-30/evidence/*/README.md | head
```

然后按该目录 README 执行（三步固定形态）：

```bash
.venv/bin/python <当前入口目录>/free_watchdog.py status      # 只读：核真实进程与当前房
.venv/bin/python <当前入口目录>/free_watchdog.py preflight   # 离线验签，不发 HTTP
.venv/bin/python <当前入口目录>/free_watchdog.py watch       # 续赛：已有玩家自然结束，绝不主动终止
```

## 5. 边打边看（本机观战器）

观战器只读本机审计，不请求官方平台、不持 Token，开关都不影响比赛。

```bash
./scripts/run_spectator.sh                 # 自动跟随最新活跃批次，换批无需重启
./scripts/run_spectator.sh --port 8766     # 换端口
./scripts/run_spectator.sh --watch-dir artifacts/sessions/<批次名>/audit   # 固定看某一批
```

浏览器打开 `http://127.0.0.1:8765/`。页面显示空态说明当前没有活跃批次，等换批即可自动接入。

## 6. 赛后：下载、封存与复核

```bash
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/test-room-20261007 \
  --download --runtime-config .private/test-room.json \
  --room <房间 ID> --batch 0 --rule-config .private/rule-config.json
```

`rule-config.json` 按本次房间真实配置填（模板 `configs/rule-config.example.json`：`base_score`、`you_cai_bi_kao`）；
不提供时保留「规则配置未知」，不会默认开启有财必烤响。产物在 `artifacts/sessions/<批次>/postgame/<时间戳>/`。

**测试房牌谱只在最新一轮可取**：`GET /api/test-rooms/{id}/games/{batch}/events` 只返回最新一轮批次数据，
开打下一轮后上一轮就再也取不到——必须逐轮下载。

## 7. 红线

- 同一个 Token 不得同时被两个进程（或两处配置）使用；自由赛全局 Token 尤其严格。
- Token 不写进代码、仓库、日志、命令行回显或截图；`.private/` 与 `artifacts/` 不进版本库。
- 结果不确定（网络中断、终态未确认、审计缺失）不要盲目重开或重试，先取证。
- 本地工程通过不等于官方现场通过；参赛前仍要核真实赛事 ID、配置与凭据。

## 8. 常见故障速查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `guide/version` 连接超时、未报名就退出 | 继承了系统代理 | 在启动终端设 `NO_PROXY` 后重启 |
| 启动即报 Token／身份错误 | Token 文件多行或有空格；Token 与赛事不匹配 | 改成单行文件，并用 `resolve_tournament.py` 核对 |
| 报「--token-file 与配置内的 token/token_env 互斥」 | 配置文件里仍留着 `token_env` | 二选一，删掉配置里的 Token 字段 |
| 续赛脚本退出码 3 | 巡检失败（如有） | 查 `runs/.../session-*.log` 与对应审计，不要重复开房掩盖异常 |
| 观战页一直空 | 当前没有活跃批次，或目录里没有 `runs/` 审计 | 换批后自动恢复；`--once` 可诊断目录识别 |
| 8765 端口被占用 | 已有观战器实例在同一端口 | 用 `--port` 换端口 |

## 9. 相关文档

- [运行、观测、赛后分析与迁移](operations.md)
- [自由赛盯盘操作](auto-match-watchdog.md)
- [架构与运行流程](architecture.md)、[冻结接口协议](implementation/interface-contracts.md)
- [研究证据索引（当前入口、策略与门禁）](../review/INDEX.md)
