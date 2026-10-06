# 正式赛接入说明

## 一、参赛程序说明

### 准备

```bash
cd <仓库根目录>
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'

# 代理例外：必须与启动赛事的终端相同，否则 guide/version 超时、未报名即退出
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}10.240.169.190"
export no_proxy="${no_proxy:+$no_proxy,}10.240.169.190"

# 取正式赛模板 + 把报名给的 Token 落成单行文件（.private/ 不入版本库）
cp configs/r18-integrated-positive-v2.official-tournament.example.json .private/official.json
printf '%s\n' '<报名拿到的 Token>' > .private/official.token
```

### 需要调整的配置项

只改这四项，其余保持模板不动：

| 字段 | 必改原因 | 怎么填 |
| --- | --- | --- |
| `expected_tournament_id` | 程序用它核对「是不是要打这一场」 | 填平台赛事 ID（用 Token 反查，见下），替换模板里的 `t_REPLACE_WITH_...` |
| `audit_root` | 每次参赛要独立审计目录 | 例：`artifacts/sessions/official-20261007/audit` |
| Token 来源 | 模板用的是环境变量名 | ① 把 `token_env` 改成你自己的环境变量名；② 或删掉 `token`/`token_env`，改用命令行 `--token-file`（三选一，同时给会报错） |
| `strategy`、`expected_policy_release_id` | 仅当不用模板绑定的策略与冻结包时 | 换策略时同时换成该策略人工批准的发布包 SHA-256；缺失或不匹配会拒绝启动 |

**`expected_tournament_id` 是什么**：本次要打的官方锦标赛 ID（形如 `t_xxxx`）。程序启动时把它与
`GET /api/me` 返回的绑定赛事严格核对，不一致直接判 `target_mismatch` **永久失败**（重试无效）。
报名只给了一个 Token 时，用 Token 反查它：

```bash
.venv/bin/python scripts/resolve_tournament.py --token-file .private/official.token \
  --config .private/official.json

# 平台基址: https://10.240.169.190:18080
# 绑定锦标赛: t_xxxxxxxx   ← 把它填进 expected_tournament_id
# 赛事名称 / 状态 / 赛制: M=…, Rounds=…, 底分=…
# 动作窗口: 碰 1s / 吃 1s / 出牌 3s
```

该命令只发幂等 GET（`/api/me`、`/api/tournaments/me/rules`），**不 register、不 ready**，赛前随时可跑。
若它显示绑定锦标赛为空，说明该 Token 未绑定赛事，不能用于正式赛。

**为什么不改 `known_guide_version`**：它是「平台指南版本下限」，程序要求 `平台指南版本 ≥ 该值`，
填高会在平台指南较低时判 `INCOMPATIBLE_GUIDE` 起不来；模板里的值已可用，只有官方指南升级且仓库适配后才跟着调。
`mode`、`token_kind`（正式赛固定 `official`，与 `mode` 交叉校验）、`base_url`、`insecure_hosts` 模板已对，不用动。

### 开赛

开赛脚本是 `scripts/run_participant.py`（单身份跑到参赛者终态）：

```bash
.venv/bin/python scripts/run_participant.py --config .private/official.json \
  --token-file .private/official.token
```

同一 Token 同一时刻只能有一个实例；结果不确定（网络中断、终态未确认、审计缺失）不要盲目重跑，先取证。

### 日志怎么看

| 目的 | 命令 |
| --- | --- |
| 单场实时状态（进程存活、当前场次与单局、动作与截止） | `.venv/bin/python scripts/monitor_run.py --audit-root <audit_root> --interval 5` |
| 全量审计（每个身份的决策链、提交结果、异常） | `.venv/bin/python scripts/audit_tool.py watch <audit_root>`（`--once` 只看一次，`--until-closed` 等结束） |
| 图形牌桌与决策（只读本机，不影响比赛） | `./scripts/run_spectator.sh` → `http://127.0.0.1:8765/` |

落盘位置 `<audit_root>/runs/<run_id>/`：

- `participants/<身份>/decisions.jsonl`：每次决策的观察、候选、选择、耗时与提交结果
- `raw/*.jsonl`：官方原始报文留痕；`lifecycle.jsonl`：生命周期；`summary.json`：终态汇总
- 赛后封存、官方牌谱下载与复核见[运行与赛后操作](operations.md#4-完赛后下载封存与复核)

## 二、源码地址

```
git@github.com:liyangink/hangma-bot.git
https://github.com/liyangink/hangma-bot.git
```
