# hangma-bot

面向官方杭麻竞赛平台的全自动 AI Bot。

## 安装与常用操作

在仓库根目录执行，需要 Python 3.11 或更高版本：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

安装时优先复用仓库内经过源码与二进制摘要校验的 C 分组扩展。当前预编译
制品覆盖 macOS 11+、arm64、CPython 3.11，兼容的 M 系列 Mac 无需编译器。
不匹配时再尝试源码构建：macOS 需要 Xcode Command Line Tools，Linux 需要
GCC/Clang 和对应 Python 开发头文件；默认允许同语义的 Python 退路。
运行时直接加载，不在动作窗口编译。
部署若要求必须有 C 加速，使用 `HANGMA_NATIVE=required .venv/bin/python -m pip install -e '.[dev]'`；
若要求完全免编译，使用 `HANGMA_NATIVE=prebuilt .venv/bin/python -m pip install -e '.[dev]'`，
不匹配会明确报错；`HANGMA_NATIVE=off` 构建纯 Python 包。修改 C 源码后须重新安装。
制品与维护方式见[预编译规则制品](prebuilt/hangma/README.md)。

同架构机器可以复用兼容的 wheel 或扩展，但操作系统、Python 二进制接口
（Application Binary Interface，ABI，决定扩展能否被当前解释器加载）和系统库也须匹配。
源码脚本优先使用当前 checkout，迁移源码运行目录时按上述可编辑安装步骤构建，
不要只安装 wheel 却运行另一份尚未构建的 checkout。启动审计的 `hand_math`
记录实际实现、数学语义版本和原生文件 SHA-256；迁移后可先本机检查：

```bash
.venv/bin/python -c 'from hangma_bot.simulation.artifacts import hand_math_runtime_metadata; print(hand_math_runtime_metadata())'
```

首次使用先复制 [测试房间配置](configs/test-room.example.json) 到私有运行配置，填写房间 ID、四个 Token 文件路径，并为每次测试设置独立的 `audit_root`。完整步骤见 [运行、观测、赛后分析与迁移指引](doc/operations.md)。

策略选用见[可用策略枚举与默认值](doc/implementation/strategy-catalog.md)。常用模板显式选择 `weighted_heuristic_v2`；配置省略 `strategy` 时仍回退到旧版 `weighted_heuristic`，建议显式填写。实验候选的可用分支、模式限制及相对V2的改动也集中记录在该表。

```bash
mkdir -p .private
cp configs/test-room.example.json .private/test-room.json
# 编辑配置并准备四个 Token 文件后，完成一个批次就退出：
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}10.240.169.190"
export no_proxy="${no_proxy:+$no_proxy,}10.240.169.190"
.venv/bin/python scripts/run_test_room.py --config .private/test-room.json --once

# 另一个终端只读四身份审计，不向平台发请求：
.venv/bin/python scripts/audit_tool.py watch artifacts/sessions/test-room-example --interval 5

# 完赛后下载指定批次，同时封存、转换数据集、复核规则与事件：
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/test-room-example \
  --download --runtime-config .private/test-room.json --room t_REPLACE_ME --batch 0 \
  --rule-config .private/rule-config.json
```

`rule-config.json` 按本次房间真实配置填写，模板见 [规则配置](configs/rule-config.example.json)。不提供时会保留“规则配置未知”，不会默认开启有财必烤响。`--once` 是完成一个测试房间批次；每场单局数由服务器的 `Rounds` 决定。

上面的 `NO_PROXY` 只让当前终端启动的进程直连赛事内网，避免系统代理阻断连接；更换平台地址时同步修改该主机。测试房、单身份赛事和自由赛启动均需留意此项，赛前免认证下载成功不能替代运行客户端的连接检查。

新制品统一放在 `artifacts/`；赛后入口输出 `report.json`、原始证据包、统一数据集和独立诊断。命令成功表示生成制品成功，是否完整、是否适合训练须看报告。`artifacts/` 不随 Git 提交，迁移机器时须另外复制。

| 脚本 | 用途 |
| --- | --- |
| `run_test_room.py` | 四身份测试房间，`--once` 或 `max_completed_batches` 限制完成批次数 |
| `run_participant.py` | 单身份测试赛事或正式赛事 |
| `run_auto_match.py` | 一个全局 Token 参加一次自由赛自动房会话 |
| `audit_tool.py watch / inspect / validate` | 多身份持续观测、追查决策链、检查原始审计 |
| `audit_tool.py postgame` | 可选下载官方牌谱，生成封存包、数据集、规则诊断和观察复核 |
| `audit_tool.py collect-test-room / convert / pack / unpack` | 单独采集、转换、打包和校验解包 |
| `audit_tool.py import-history / migrate-runs` | 历史原文按哈希归并、恢复旧审计布局、迁移旧运行目录 |
| `audit_tool.py catalog` | 更新 `artifacts/catalog.json`，定位各会话最新分析及报告摘要 |
| `monitor_run.py` | 单个运行的紧凑状态与进程存活观测；四身份汇总用 `watch` |
| `export_game_records.py` | 人工查看多身份合并的审计视图，不作为官方牌谱或训练输入 |
| `probe_event_stream.py` | 专项协议取证，会向平台发请求；常规观测用本地 `watch` |
| `sync_official_guide.py / resolve_tournament.py` | 同步官方指南、核对 Token 对应赛事 |
| `evaluate.py` | 用已筛选的数据集复评决策或模拟桌赛，见评估指引 |
| `run_spectator.sh` | 本地观战页面，见 [观战说明](spectator/README.md) |

历史整理结果见 [2026-09-07 制品清单](doc/artifact-inventory-2026-09-07.md)。`review/` 中按房间编写的脚本保留为历史取证依据，后续常规操作使用上述入口。

## 文档

- [可用策略枚举、默认值与取用示例](./doc/implementation/strategy-catalog.md)
- [技术方案与一个月实施计划](./doc/hangma-ai-bot-technical-plan.md)
- [架构图、运行流程与场景边界](./doc/architecture.md)
- [第一阶段实施导航与 Agent 分工](./doc/implementation/README.md)
- [冻结接口协议](./doc/implementation/interface-contracts.md)
- [第一阶段 MVP 验收标准](./doc/implementation/mvp-acceptance.md)
- [MVP 后并行施工导航与委派文本](./doc/implementation/parallel-workstreams.md)
- [并行开发共享契约 parallel-v1](./doc/implementation/parallel-contracts.md)
- [审计增强实施方案](./doc/implementation/audit-enhancement.md)
- [ADR-0001：第一阶段模块接缝与提交语义](./doc/decisions/0001-freeze-mvp-module-contracts.md)
- [统一术语表](./UBIQUITOUS_LANGUAGE.md)
- [官方赛事流程与多阶段晋级规则（2026-09-03）](./doc/official-tournament-flow-2026-09-03.md)
- [官方平台 API（已同步 v15）与时间模型](./doc/official-platform-api-v2.md)
- [仓库统一开发与文档规范](./AGENTS.md)
