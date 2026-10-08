# hangma-bot

面向官方杭麻竞赛平台的全自动 AI Bot。

按任务进入对应资料；历史交接与日期型执行清单保留作当时证据，不代表当前结论。

| 任务 | 首要入口 |
| --- | --- |
| 了解当前候选、进化停线与接线证据 | [研究证据索引](review/INDEX.md) |
| 核对策略名称与可配置候选 | [算法路线与候选命名](doc/algorithm-lineage-names.md)、[策略目录](doc/implementation/strategy-catalog.md) |
| 启动测试房、测试赛事或正式赛事 | [参赛说明](doc/participate-quickstart.md)、[运行与赛后操作](doc/operations.md#2-启动测试房间与赛事) |
| 启动或暂停自由赛 watchdog | [当前 G37-RF1 独立根续赛](review/vip-route-2026-09-30/evidence/t227-rf1-default-and-live-1/README.md)、[通用盯盘操作](doc/auto-match-watchdog.md) |
| 观测、审计与赛后处理 | [本地观测](doc/operations.md#3-持续观测与定位)、[完赛后下载与复核](doc/operations.md#4-完赛后下载封存与复核) |
| 修改模块或接口 | [架构与运行流程](doc/architecture.md)、[冻结接口协议](doc/implementation/interface-contracts.md) |

## 安装与常用操作

Apple Silicon Mac 参赛只需两条命令，在仓库根目录执行：

```bash
bash participate.sh check   # 按提示输入报名 Token，只检查赛事
bash participate.sh start   # 确认赛事正确后启动，保持终端运行
```

入口自动准备独立的 CPython 3.11 环境、安装依赖并生成赛事配置，现场已有其他 Python 版本也可使用。当前正式策略直接复用已验证的预编译文件，无须编译器或手动激活环境；首次准备需要联网，后续复用已安装环境。测试赛事在两条命令末尾加 `--test`。Windows／Linux 尚需对应正式策略发布包；编译准备见 [Windows 编译指南](doc/windows-build-guide.md)。

同一赛事可提前启动，阶段之间会自动等待，并在下一阶段开放时确认出席；保持电脑联网运行，无需每个阶段重新执行。旧进程退出后可重新执行 `start`，从平台当前状态恢复，产生新的运行日志；本目录同一模式已有进程时，重复检查或启动会被拒绝。报名和到位仍须符合平台时限及资格要求，重启不能补回已错过的动作或恢复淘汰资格。更换赛事 ID／Token 时须重新准备对应配置，原配置会拒绝赛事错配。

终端显示安装进度、赛事检查结果、运行模式、策略、审计目录和结束结果。详细生命周期、动作决策及官方事件写入启动时显示的审计目录；可另开终端查看实时状态，将下方路径替换为该目录：

```bash
.private/participant-runtime/venv/bin/python scripts/monitor_run.py --run-dir '<审计目录>'
```

2026-10-07 已完成 75 项相关回归、系统 Python 3.9 下的干净环境自动安装、免再次下载的环境复用，以及假赛事完整启动验证。假赛事完成报名、到位和结束，10 个计算进程正常关闭、计算故障为 0；这些是工程核验结果，尚未进行官方现场参赛。

开发安装在仓库根目录执行，需要 Python 3.11 或更高版本：

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

```bash
mkdir -p .private
cp configs/test-room.example.json .private/test-room.json
# 编辑配置并准备四个 Token 文件后，完成一个批次就退出：
.venv/bin/python scripts/run_test_room.py --config .private/test-room.json --once

# 另一个终端只读四身份审计，不向平台发请求：
.venv/bin/python scripts/audit_tool.py watch artifacts/sessions/test-room-example --interval 5

# 完赛后下载指定批次，同时封存、转换数据集、复核规则与事件：
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/test-room-example \
  --download --runtime-config .private/test-room.json --room t_REPLACE_ME --batch 0 \
  --rule-config .private/rule-config.json
```

`rule-config.json` 按本次房间真实配置填写，模板见 [规则配置](configs/rule-config.example.json)。不提供时会保留“规则配置未知”，不会默认开启有财必烤响。`--once` 是完成一个测试房间批次；每场单局数由服务器的 `Rounds` 决定。

运行客户端会对配置在 `insecure_hosts` 中的官方内网主机自动直连，无需手动设置代理例外。正式赛和单身份测试赛事可用 `resolve_tournament.py --write-config` 自动生成配置，见[两步参赛说明](doc/participate-quickstart.md)。

新制品统一放在 `artifacts/`；赛后入口输出 `report.json`、原始证据包、统一数据集和独立诊断。命令成功表示生成制品成功，是否完整、是否适合训练须看报告。`artifacts/` 不随 Git 提交，迁移机器时须另外复制。

2026-10-08最后一次测试赛的[赛后处理数据包](datasets/official-tournament/t_e3c195576228/README.md)已精选入库，压缩2.15MB，含逐局轨迹、合法候选摘要和复算脚本；原始审计仅本地归档。旧展开数据的清理及发布包重新绑定记录见[归档与清理记录](doc/maintenance/local-archive-20261008.md)。

| 脚本 | 用途 |
| --- | --- |
| `participate.sh check / start` | Mac 自动准备环境，检查正式／测试赛事并启动；`--test` 选择测试赛事 |
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
| `sync_official_guide.py / resolve_tournament.py` | 同步官方指南；查询 Token 绑定赛事，`--write-config` 从模板生成参赛配置 |
| `evaluate.py` | 用已筛选的数据集复评决策或模拟桌赛，见评估指引 |
| `run_spectator.sh` | 本地观战页面；无参数时自动跟随最新活跃自由赛批次，见 [观战说明](spectator/README.md) |

历史整理结果见 [2026-09-07 制品清单](doc/artifact-inventory-2026-09-07.md)。`review/` 中按房间编写的脚本保留为历史取证依据，后续常规操作使用上述入口。

## 文档

当前工作按上方任务表进入。[统一术语表](./UBIQUITOUS_LANGUAGE.md)、[架构与运行流程](./doc/architecture.md)、[接口协议](./doc/implementation/interface-contracts.md)及[官方平台 API（v34 全文基线）](./doc/official-platform-api-v2.md)用于核对实现。早期 MVP 计划、并行施工方案和按日期命名的交接报告保留为历史设计与证据，从[实施导航](./doc/implementation/README.md)或[研究证据索引](review/INDEX.md)按需查阅。

## 策略选用

截至 2026-09-29 的连续自由赛使用显式配置的 `r18_integrated_positive_v2` 冻结候选；之后的实际身份须逐次核对运行清单。是否适合测试赛事或正式赛事仍以发布门禁为准。新旧候选的可配置范围和发布包摘要以[策略目录](doc/implementation/strategy-catalog.md)及对应[配置模板](configs/r18-integrated-positive-v2.auto-match.example.json)为准。
