# 运行、观测、赛后分析与迁移

本文说明仓库现有脚本的固定用法。所有命令从仓库根目录运行；路径均相对仓库，换机器后无需修改源码。官方依据使用 [2026-09-06 抓取的指南 v18](../review/official-adapter/chain-rate-alignment/guide.txt) 与 [API 说明](official-platform-api-v2.md)，不是对远端当前版本的再次确认。

## 1. 制品目录

一次操作会话（`session`，人为指定、用于归集一次参赛及分析的目录）采用独立名称，例如 `test-room-20260907-roomid`。它不替代官方赛事、桌赛、单局或 `run_id`。`audit_root` 必须指向该会话的 `audit/`，不要再填 `runs/`，以免产生难辨认的多层 `runs/runs`。

```text
artifacts/
  sessions/<session>/
    audit/                        # 单身份 runs/；测试房间 slot-*/runs/
    official/<download-id>/        # 原始响应、source.json、下载错误证据
    postgame/<UTC-time>-<id>/       # 每次重分析新目录，不覆盖旧结果
      bundles/<id>/               # 原始 run、官方原文、分析源码及来源清单
      archives/<id>.tar.gz         # 原始证据归档，旁边有 .sha256
      derived/<dataset-id>/        # decisions / hands / index / manifest / validation
      diagnostic/<source-sha>/     # 原文、终局事件派生行、规则核验
      observation-status.json      # 提交、HTTP 状态、观察问题、封存数
      observation-checks.json      # 连续状态转移与已收事件集合核对
      audit-validation.json        # 每个 run 的原始审计校验
      report.json                 # 总报告，内部使用相对路径
      README.md
    latest-postgame.json           # 最新已完成分析的相对路径
  legacy/runs/                    # 迁入的旧目录，保留原组织方式
  probes/                         # 额外协议取证
  exports/                        # 人工阅读的派生视图
.private/                         # 本机运行配置与凭证，单独迁移
runs/                             # 运行态（进程 stdout 日志、盯盘账本、文件锁）：不入库、可随时清理，不承载审计数据
```

分工约定（2026-09-09）：`artifacts/` 只保存审计取证与赛后制品；仅为定位、追踪或维持运行服务的运行态数据统一放 gitignored 的 `runs/`（如自由赛盯盘的 `runs/auto-match-watchdog/`）。旧 `runs/` 根下的历史审计已于 2026-09-08 全部迁入会话目录，此后 `runs/` 不再作为任何审计落点。

`run_id` 内部布局继续遵守 [审计契约](implementation/interface-contracts.md)；原始运行一律经各入口配置的 `audit_root` 直接写入所属会话目录。已有 `game-records/` 和 `datasets/` 是入库的历史资料，保留原件，新下载不再写入那里。归并的官方原文以 SHA-256（文件内容摘要，用于核对字节与去重）命名，同一原文的多处来源保存在 `source.json`。

## 2. 启动测试房间与赛事

启用系统代理的机器，应在启动赛事的同一终端为官方内网设置代理例外。2026-09-07 实测：免认证采集客户端直连成功，但参赛客户端默认继承 macOS 系统代理，可能在 `guide/version` 连接超时，尚未报名即退出。以下只设置子进程环境，不修改系统代理；换平台主机时同步修改地址。测试房、单身份赛事与自由赛均适用。

```bash
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}10.240.169.190"
export no_proxy="${no_proxy:+$no_proxy,}10.240.169.190"
```

先按 [README](../README.md) 安装依赖。复制 `configs/test-room.example.json` 到 `.private/test-room.json`，修改 `expected_tournament_id`、`audit_root`，把四个真实 Token 各保存为一个单行文件。四个文件名与配置中的 `token_file` 一致。也可使用 `token_env`；同一身份的 `token/token_env/token_file` 只能选一个。

房间的 `M`（每个身份最多同时处理的场次数）、`Rounds`（每场单局数）、`BaseScore` 和 `YouCaiBiKao` 由平台配置决定。启动文件不能修改服务器规则。复制 `configs/rule-config.example.json` 到 `.private/rule-config.json`，按实际房间填写 `base_score` 与 `you_cai_bi_kao`，供赛后核验。

```bash
.venv/bin/python scripts/run_test_room.py --config .private/test-room.json --once
```

`--once` 使每个身份在收到一次 `tournament_finished` 后退出，不再创建下一批次的注册进程；等四身份汇总退出后再执行赛后分析。配置 `max_completed_batches: 2` 可完成两个批次；省略或设为 `null` 沿用持续续赛，`--once` 优先于配置。正常完赛不消耗失败重启预算。Ctrl-C、SIGINT、SIGTERM 会转发给子进程并中止当前工作，不能当成“打完本批次后停”。新测试优先在启动时定好批次数。

单身份测试赛事使用 `configs/participant.example.json`：

```bash
.venv/bin/python scripts/run_participant.py --config .private/participant.json
```

正式赛事需将配置改为实际赛事 ID、`mode: official_tournament`、`token_kind: official`，并提供正式 Token。自由赛使用 `configs/auto-match.example.json` 和 `run_auto_match.py --config .private/auto-match.json`，一个全局 Token 同时只运行一个实例；默认一次自动房会话结束即退出。具体参数见 [自由赛指引](implementation/free-match-start.md)。示例使用当前代码基线 v18 和 `sse_enabled: false`；遇到指南变化先同步、审查兼容性，不能只把版本号改大。

### 2.1 持续多策略对比战役（测试房 watchdog）

`scripts/test_room_campaign_watchdog.py` 把「开房 → 按整轮续打 → 下载牌谱 → 赛后封存 → 提升到数据池 → 增量落库」串成一条可反复调用的命令，用于在同一张桌上长期对比多条策略。四条臂坐在同一场、同一单局里，官方每个场次重新随机换座，因此每个单局天然是一组配对观测。

```bash
# 1) 建房（M=10、Rounds=16、空闲 30 分钟自动关闭），落盘令牌、战役记录与策略归因
.venv/bin/python scripts/test_room_campaign_watchdog.py open \
  --campaign runs/testroom-campaign-20260914 --m 10 --rounds 16 --target-rounds 8

# 2) 开打之前先离线装配四条臂（模型装载、规则适用范围）；失败就不要进房
.venv/bin/python scripts/test_room_campaign_watchdog.py preflight \
  --campaign runs/testroom-campaign-20260914

# 3) 打一个整轮并做完赛后处理；一轮跑完即退出
.venv/bin/python scripts/test_room_campaign_watchdog.py round \
  --campaign runs/testroom-campaign-20260914

# 4) 只读进度与库内累计
.venv/bin/python scripts/test_room_campaign_watchdog.py status --campaign runs/testroom-campaign-20260914
```

**为什么一轮跑完必须立刻下载**：`GET /api/test-rooms/{id}/games/{batch}/events` 只返回**最新一轮**的批次数据（指南 v1 测试房数据 API）。开打下一轮之后，上一轮的官方牌谱就再也取不到了——逐轮下载是硬约束，不是优化。

**整轮唤醒而不是长驻**：脚本内没有任何睡眠轮询。把 `round` 当后台任务挂起，任务结束时再挂下一个 `round`，这就是本战役的节奏。房间空闲 `timeout_min` 分钟会自动 `close`，续打要在分析之前先发起。

**路径与归因**：战役运行态在 `runs/<campaign>/`（gitignored：战役记录、令牌、逐轮摘要、身份进程日志）；逐轮审计会话是 `artifacts/sessions/<campaign>-rN/`；对比数据池是 `datasets/derived/<pool>/{hands,manifests,validations,official}`，这是入库主源。`open` 会把四个令牌的 `user_id` 写进 `datamart/strategy-map.json` 的 `identities`，**座位级策略归因靠它**；四个槽位的策略在整个战役里固定不轮换——官方每场重新随机换座，座位偏差在 M 场内已被随机化。

`round` 退出码 1 表示本轮有步骤失败（摘要仍写出 `runs/<campaign>/summary-rN.json`），不等于没拿到数据。逐轮结果的阅读入口是 `datamart/compare_arms.py`（见 [评估库说明](../datamart/README.md)）。

## 3. 持续观测与定位

常规观测只读本机审计，支持单身份和四身份、普通 JSONL 和压缩分段，不增加平台请求。

```bash
.venv/bin/python scripts/audit_tool.py watch artifacts/sessions/test-room-example --interval 5
.venv/bin/python scripts/audit_tool.py watch artifacts/sessions/test-room-example --once --json
./scripts/run_spectator.sh --watch-dir artifacts/sessions/test-room-example/audit
.venv/bin/python scripts/audit_tool.py validate artifacts/sessions/test-room-example/audit/slot-qinglong/runs/RUN_ID
.venv/bin/python scripts/audit_tool.py inspect artifacts/sessions/test-room-example/audit/slot-qinglong/runs/RUN_ID --game GAME_ID --json
```

`watch` 输出实际 HTTP 状态与应用层结果，`pass_deferred_until_chi` 单列为本地延后 Pass，不算 HTTP 提交失败。尾行未写完会显式显示读取问题。监控启动器预定批次仍以启动器退出结果为准：`--until-closed` 只保证当前已经发现的运行均有收尾文件，不能判断守护进程稍后是否会创建新批次。

额外协议探针 `probe_event_stream.py` 会使用 Token 发请求，属于专项取证；不要为了普通状态显示再启动它。确需采样时指定独立的 `--out-dir artifacts/probes/<case>`，并评估它与参赛进程共享的请求额度。`review/official-adapter/` 中写死房间、时间或事件序号的脚本用于解释历史个案，不作为常规观测入口。

## 4. 完赛后下载、封存与复核

一个命令完成下载指定测试房间批次及分析；`--batch` 是官方 games 列表中的批次号，不是单局号：

```bash
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/test-room-example \
  --download --runtime-config .private/test-room.json --room t_REPLACE_ME --batch 0 \
  --rule-config .private/rule-config.json
```

采集使用免认证端点，客户端只读取基址与限定主机的 TLS 配置。每次下载保存独立目录及原始响应字节；HTTP 错误、未完赛、身份不匹配或未完成的下载保留证据，并隔离出转换流程。需要多个批次时，先对各批次使用 `collect-test-room --runtime-config ... --room ... --batch ... --out SESSION`，再运行一次 `postgame SESSION`。

已下载的会话直接离线重分析，不请求网络：

```bash
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/test-room-example --rule-config .private/rule-config.json
```

所有 `run` 必须已有 `summary.json`；仍在运行则拒绝封存。每次重分析产生新目录，旧包和官方原文不改写。封存包保存分析源码、提交号、工作区状态、规则源码摘要和显式核验配置；历史线上规则版本仍以原始审计 manifest 为准。下载发生时间不冒充比赛发生时间。

命令退出 0 表示成功生成制品，**不是全部正确性检查通过**。先看 `report.json`，再看以下报告：

| 制品 | 可以据此判断 | 限制 |
| --- | --- | --- |
| `audit-validation.json` | 决策链、尝试链、原始审计结构是否完整 | 历史缺原始报文不能补造 |
| `observation-status.json` | 四身份动作结果、HTTP 状态、已报告观察问题 | 统计不是时限正确性的独立证明 |
| `observation-checks.json` | 官方牌谱与本人已收原文的缺失/字段差异（先脱敏他家摸牌）；封存历史集合及快照转移 | 赛后可见集合不证明及时到达；复用投影不能排除投影本身缺陷；未支持的 `catch_play` 等分支保持未检查 |
| `derived/*/validation.json` | 正式导入、决策完整性、历史覆盖和世界导入边界 | 无未来牌墙不能还原 `WorldState`；结构通过不等于规则通过 |
| `diagnostic/*/rule-check.json` | 终局事件派生结果与唯一 `HangmaRules` 的计番、结算检查 | 摘要冲突不因诊断成功变成正式导入成功；缺真实规则配置时不检查 |

历史来源只有计分开关、缺少本地规则版本时，正式单局行的 `rule_config` 保持为空；已知的局部配置继续保存在来源中，供显式重分析使用。正式数据集 `decisions.jsonl` 保留当时的 `PlayerObservation`，用于复评策略前仍需按完整性、阶段是否作废、版本等筛选。官方牌谱与诊断 `hands.jsonl` 是赛后全信息，不能编码进学生观察。`teacher_label_candidate` 只是供教师标签筛选的候选标记，不代表已满足训练准入。历史已失败案例对定位协议和规则回归仍有价值，保留失败报告，不作为成功标签。

本入口固化常规检查；没有自动执行所有个案脚本，也没有把生产投影复用当成完全独立的对拍。进一步训练与桌赛评估见 [评估指引](implementation/evaluation-start.md)。

## 5. 历史整理与环境迁移

已有旧 `runs/` 的机器，先停止启动新赛事并确认所有参赛进程退出，再执行一次：

```bash
.venv/bin/python scripts/audit_tool.py migrate-runs
.venv/bin/python scripts/audit_tool.py import-history artifacts/legacy/runs game-records datasets/official-auto-match --out artifacts/sessions/history
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/history
.venv/bin/python scripts/audit_tool.py catalog
```

迁移不会删除原始记录；相同目标拒绝覆盖。历史导入按原文字节去重，并记录相对来源。旧 `bot-audit` 扁平布局恢复到标准目录；缺失 `raw/` 仍标记为不完整，不能声称恢复出了当时没留存的信息。不同来源对同一原文给出冲突规则配置时停止归并，避免任选一个配置。

`catalog` 更新 `artifacts/catalog.json`，列出规范会话与旧目录会话的最新报告、内容摘要和数据量；后续重新分析后可再次执行。历史集合与单独会话可能包含同一场次，不能直接相加当成训练样本量。

换机器须分别迁移代码、`artifacts/` 和 `.private/`。只 `git clone` 无法得到被忽略的原始审计和封存包；也不要仅复制派生数据集而丢掉原始证据。推荐复制整个会话目录，保持内部相对路径，旧运行数据位于 `artifacts/legacy/runs/`。旧报告需要兼容链接时，在仓库根确认没有实际 `runs` 目录后执行 `ln -s artifacts/legacy/runs runs`。

已明确选择入库的测试证据放在 `datasets/official-test-room/<room_id>/`，可随Git迁移；例如 [M=4测试房制品](../datasets/official-test-room/t_64201ecc3ab3/README.md)同时包含官方牌谱、原始审计封存包和派生分析包。按目录内README核验与恢复，不需要重复复制它们对应的整个本机会话。凭证仍须单独迁移。

只转移某次证据包时，把 `.tar.gz` 和同名 `.sha256` 一起复制，再核验解包到不存在的新目录：

```bash
.venv/bin/python scripts/audit_tool.py unpack /path/to/JOB_ID.tar.gz --out artifacts/restored/JOB_ID
.venv/bin/python scripts/audit_tool.py postgame artifacts/restored/JOB_ID
```

解包会核验归档摘要与清单，并拒绝危险路径和覆盖。它恢复原始证据；旧分析报告与数据集位于归档外，需要保留旧结论时一并复制整个 `postgame/<job>/`。重新分析默认使用新环境当前规则实现；要复现旧分析应使用包内 `references/analysis-source` 和 `analysis-provenance.json` 所指版本与配置。
