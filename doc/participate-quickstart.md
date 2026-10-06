# 正式赛接入说明

## 一、参赛程序说明

### 准备

```bash
cd <仓库根目录>
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'

# 代理例外：必须与启动赛事的终端相同，否则 guide/version 超时、未报名即退出
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}10.240.169.190"
export no_proxy="${no_proxy:+$no_proxy,}10.240.169.190"

# 取正式赛模板 + 落 Token（单行文件；.private/ 不入版本库）
cp configs/r18-integrated-positive-v2.official-tournament.example.json .private/official.json
printf '%s\n' '<正式赛 Token>' > .private/official.token
```

### 关键配置项（`.private/official.json`）

| 字段 | 必填 | 怎么填 |
| --- | --- | --- |
| `mode` | 是 | 固定 `official_tournament` |
| `token_kind` | 是 | 固定 `official`；与 `mode` 交叉校验，填 `test` 直接拒绝启动 |
| `base_url` | 是 | `https://10.240.169.190:18080` |
| `expected_tournament_id` | 是 | 本次正式赛赛事 ID，必须非空；填错会在报名阶段暴露 |
| `known_guide_version` | 是 | 仓库当前已适配版本（见 `src/hangma_bot/adapters/official/dto.py` 的 `KNOWN_GUIDE_VERSION`，当前 35）；模板里的值可能滞后 |
| `audit_root` | 是 | 本次独立审计目录，如 `artifacts/sessions/official-20261007/audit` |
| `strategy` | 是 | 已批准的策略名（如 `r18_integrated_positive_v2`）；不要留默认 `weighted_heuristic` |
| `expected_policy_release_id` | 冻结包策略必填 | 人工批准发布包的完整 SHA-256；缺失或不匹配会拒绝启动 |
| `token` 或 `token_env` | 二选一 | 内联 Token 或环境变量名；与命令行 `--token-file` 三选一，同时给会报错 |

其余项按模板保留：`insecure_hosts: ["10.240.169.190"]`（仅对赛事内网关闭证书校验）、`sse_enabled`、
`discard_pacing_enabled`、`source_namespace`。**配置不接受未知字段**，字段名拼错会在组装期直接报错。

### 开赛

开赛脚本是 `scripts/run_participant.py`（单身份跑到参赛者终态）：

```bash
.venv/bin/python scripts/run_participant.py --config .private/official.json \
  --token-file .private/official.token

# 开赛前只读核对「这个 Token 绑的是哪一场」（不 register / 不 ready）
.venv/bin/python scripts/resolve_tournament.py --token-file .private/official.token \
  --config .private/official.json
```

注意：同一 Token 同一时刻只能有一个实例；`--token-file` 与配置里的 `token`/`token_env` 互斥；
结果不确定（网络中断、终态未确认、审计缺失）不要盲目重跑，先取证。

## 二、源码地址

```
git@github.com:liyangink/hangma-bot.git
https://github.com/liyangink/hangma-bot.git
```
