# 参赛速查：准备与赛事

**范围**：程序通过官方 HTTP API 接入平台参赛；本文只覆盖**准备**与**单身份赛事**（测试赛事 / 正式赛事）。
测试房间、自由赛与观战命令见[运行与赛后操作](operations.md)与[自由赛盯盘操作](auto-match-watchdog.md)。
所有命令都在仓库根目录执行。

## 1. 准备

```bash
cd <仓库根目录>
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q          # 可选：确认环境完好
```

**代理例外**：参赛客户端会继承系统代理，在 `guide/version` 上超时后就退出。必须在**启动赛事的同一个终端**执行；
只影响该终端子进程，不改系统代理；换平台主机时同步改地址。

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
配置里的 `token`（内联）／`token_env`（环境变量名）／命令行 `--token-file` **三选一**，同时给会直接报错。

## 2. 测试赛事 / 正式赛事（单身份）

```bash
cp configs/participant.example.json .private/participant.json
```

| 赛事类型 | 配置改动 | Token |
| --- | --- | --- |
| 测试赛事 | `mode: test_tournament`、`token_kind: test`、填真实 `expected_tournament_id` | 测试 Token |
| 正式赛事 | `mode: official_tournament`、`token_kind: official`、填真实赛事 ID | 正式 Token |

两种方式任选一种提供 Token（不要同时用）：

```bash
# 方式一：Token 文件（配置里不要保留 token / token_env）
printf '%s\n' '<参赛 Token>' > .private/participant.token
.venv/bin/python scripts/run_participant.py --config .private/participant.json --token-file .private/participant.token

# 方式二：环境变量（配置里保留 token_env，不要加 --token-file）
export HM_PARTICIPANT_TOKEN='<参赛 Token>'
.venv/bin/python scripts/run_participant.py --config .private/participant.json
```

开打前用只读接口核对「这个 Token 绑的是哪一场」（不 register、不 ready）：

```bash
.venv/bin/python scripts/resolve_tournament.py --token-file .private/participant.token --config .private/participant.json
```

注意：

- 同一 Token 不得同时被两个进程或两处配置使用。
- 结果不确定（网络中断、终态未确认、审计缺失）不要盲目重开或重试，先取证。
- 本地工程通过不等于官方现场通过；参赛前仍要核真实赛事 ID、配置与凭据。

## 3. 相关文档

- [运行、观测、赛后分析与迁移](operations.md)
- [冻结接口协议](implementation/interface-contracts.md)
- [研究证据索引（当前入口、策略与门禁）](../review/INDEX.md)
