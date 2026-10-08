# Git 项目数据构成与清理核对

> 本文是实施前审计快照。已执行的目录迁移、历史重写与验证见[2026-10-09 维护记录](git-storage-migration-20261009.md)。

**体积审计基线 main 为 `f608024c130070c035a64e1b03700c9977312769`，共 139,192 个已跟踪文件、12.93 GiB。研究目录 `review/` 占基线文件长度约 97%；按 Git 文件对象存储长度统计，证据分块、封包与压缩日志占 97.38%。清理重点是这些数据载荷。**

本次只输出三项核对：参赛必须保留的依赖、已过时或重复数据的清理候选、最高占用目录与文件。此前新增的轻量克隆 README 和参赛说明改动已撤回。没有删除项目数据、移出跟踪、改写历史或修改远端。

统计分为当前提交按路径累计的文件长度，以及本地 Git 对象选中副本的存储长度。1 MiB＝1,048,576 字节，1 GiB＝1,073,741,824 字节。后者可以反映大载荷的优先级，但受差量编码和重复 pack 影响，不能直接作为清理后的可释放容量。

## Git 中的项目数据构成

| 当前 main 目录 | 文件长度 | 占当前文件长度 | 内容 |
| --- | ---: | ---: | --- |
| `review/` | 12.54 GiB | 96.97% | 研究原件、实验准备、运行记录、源码快照、封包与分块 |
| `datasets/` | 308.75 MiB | 2.33% | 精选牌谱、训练及评估数据 |
| `game-records/` | 52.16 MiB | 0.39% | 历史牌谱 |
| `prebuilt/` | 16.67 MiB | 0.13% | 规则与策略二进制、生成源码、发布清单与批准证据 |
| `datamart/` | 9.96 MiB | 0.08% | 离线分析数据库 |
| `tests/` | 7.03 MiB | 0.05% | 回归代码与固定样本 |
| `src/` | 3.27 MiB | 0.02% | 生产及离线源码，受发布摘要约束 |
| `doc/` | 2.20 MiB | 0.02% | 团队方案、接口、操作和历史记录 |
| `spectator/` | 0.80 MiB | 0.01% | 可选观战页面 |
| `scripts/` | 0.67 MiB | 0.01% | 启动、赛后处理、研发及维护工具 |

相同目录的展开体积和 Git 存储体积差异很大：JSON 很大但可压缩，已经压缩的封包和分块占据大部分 Git 空间。

| 数据类别 | 当前文件长度 | 文件长度占比 | Git 当前对象存储长度 | 存储占比 |
| --- | ---: | ---: | ---: | ---: |
| 证据分块 | 4.89 GiB | 37.82% | 4.82 GiB | 62.45% |
| JSON 证据与准备记录 | 4.08 GiB | 31.55% | 144.39 MiB | 1.83% |
| 压缩日志或数据 | 1.60 GiB | 12.35% | 1.31 GiB | 16.93% |
| 证据压缩包 | 1.44 GiB | 11.12% | 1.39 GiB | 18.00% |
| 展开 JSONL 数据 | 563.53 MiB | 4.25% | 23.05 MiB | 0.29% |
| Python 源码含研究快照 | 210.69 MiB | 1.59% | 14.75 MiB | 0.19% |
| 其他 | 173.64 MiB | 1.31% | 25.11 MiB | 0.32% |

`.bin` 和 `.part-*` 的大多数文件是历史证据分块，不是参赛模型。分块使单个文件低于上传限制，却没有减少总存储量。现有 `.gitignore` 已排除部分新封包，但仍在跟踪的历史文件不会因此退出 Git。

## 参赛程序必须保留的文件

核对期间 main 新增了 G37-RF1 发布提交；以下以最新 `f608024c13` 为准。默认参赛入口仍选择 P0 `approved-v4`，G37-RF1 是新发布的可选修复包。不能依据旧日期或旧 v3 核对结果删除新包。[当前证据索引](../research/INDEX.md)、[策略目录](../implementation/strategy-catalog.md)。

| 文件范围 | 保留理由 |
| --- | --- |
| `participate.sh`、`pyproject.toml`、`hatch_build.py` | 参赛环境准备、安装与原生制品核验 |
| `scripts/participate.py`、`scripts/resolve_tournament.py`、`scripts/run_participant.py` | 赛事检查、配置准备和单身份参赛入口 |
| `scripts/run_test_room.py`、`scripts/run_auto_match.py` | 测试房／自由赛入口，同时受发布源码摘要绑定 |
| 完整的 `src/hangma_bot/**/*.py`、`*.c`、`*.h` | 当前 `source_manifest` 覆盖整个源码树，含 `offline`；删离线源码同样会使发布校验失败 |
| `configs/vip-s03-rulefix-p0-approved-v4.*.example.json` | 当前 P0 对应模式的模板与发布包 ID |
| `configs/vip-g37-rf1-v1.*.example.json` | 选用 RF1 时的对应模式模板 |
| `prebuilt/hangma/` | 规则数学后端、原生二进制和摘要清单 |
| `prebuilt/vip-s02-compiled-runtime-v1/` | P0 和 RF1 仍复用其中的编译助手，属于当前依赖 |
| `prebuilt/vip-s03-rulefix-p0-compiled-v1/`、`prebuilt/vip-s03-rulefix-p0-release-evidence-v1/` | 当前 P0 公式、编译收据和批准证明 |
| `prebuilt/vip-s03-rulefix-p0-*-approved-v4/` | 当前 P0 对应模式的冻结包 |
| `prebuilt/vip-g37-rf1-compiled-v1/`、`prebuilt/vip-g37-rf1-release-evidence-v1/`、`prebuilt/vip-g37-rf1-*-v1/` | RF1 对应模式的编译文件、问题修复证明及发布清单 |
| 本机实际 Token、赛事配置与参赛环境 | 运行时必须准备；不属于共享源码集合 |

预编译目录中的生成 `.c`、`.pyx`、`source.py` 不能直接当作普通构建缓存删除：当前启动会校验这些文件的摘要。资格证明中出现的历史 `review/` 路径有些仅表示来源身份；P0 与 RF1 实际读取的是 `prebuilt/` 副本，不能只凭字符串出现就认定整个研究目录是运行依赖。

旧 P0 v1—v3 的 12 份发布清单合计仅 674.15 KiB。v3 仍被 `scripts/freeze_vip_rf1_release.py` 用作生成后继包的输入，赛事配置解析回归也读取 v3 模板，因此这些旧文件不能仅因版本号低就整批删除。当前运行依赖与发布维护依赖需要分别保留。

已只读提取 399 个文件、13.47 MiB 的保守依赖集合，包含完整源码、脚本、配置及 P0／RF1 正式和测试赛事包。两条路线各两种赛事模式通过公开 `load_config` 和 187 项源码摘要核验，平台 HTTP 请求为 0。测试房和自由赛还需各自模式清单。这项核验用于证明依赖范围，不改变拉取方式或运行入口。

当前 P0／RF1 的正式和测试赛事不需要加载整个 `review/`、`datasets/`、`game-records/`、`datamart/`、`tests/` 或 `spectator/`。其中测试、文档、观战和源码体积小且仍有研发用途，清理收益远低于大证据载荷。

## 已过时和重复数据的清理候选

**已验证的重复展开数据是第一批具体清理对象；原始证据的内容仍应由封包保全。** 不能将“参赛不用”直接等同于“无研究用途”。

| 分类 | 核对结果 | 建议处置 |
| --- | --- | --- |
| 已封存的重复展开文件 | 共核对 1,355 个同字节重复项、224.57 MiB；31 组封包／顺序分片摘要已实际核验 | 保留封包、恢复工具及来源摘要，优先去除重复展开载荷 |
| 重复数据载荷候选 | 排除代码、文档、配置、索引和账本后，899 个文件、208.54 MiB | 可作为移出 Git 跟踪的核对名单；先修复原路径引用，再确认没有后续改动及运行依赖 |
| 重复文档、脚本、索引和账本 | 456 个、16.03 MiB | 本次保留，避免断开旧报告和复算工具 |
| 误跟踪的 Python 缓存 | T96 的 `__pycache__/extract.cpython-311.pyc`，3,500 字节 | 可清理生成缓存并保留 `.py`，体积收益很小 |
| 41 个独立历史归档目录 | 当前 main 共 3.10 GiB，最大为 T39／T41 约 1.00 GiB | 适合将大载荷迁出代码仓库，保留报告、索引、哈希、恢复工具和取回位置；目前不能当作无备份垃圾销毁 |
| T191、T195 等旧研究原流、确认过程和重复源码快照 | 当前不是默认参赛依赖，仍被研究报告和复算调用 | 将大载荷和摘要分开处置；不按目录日期整包删除 |
| 旧发布包和模型候选 | 当前 P0／RF1 未选用部分包，但旧配置和回退调用仍可能引用 | 调用者核对后再退役；优先级低于多 GiB 证据，S02 共享助手必须保留 |

[逐文件清理候选清单](git-cleanup-candidates-20261008.json)保存全部 899 个候选的路径、字节数、SHA-256 和封存索引。它是可审阅的候选集合，不是已经完成引用迁移的删除清单。该字节数是展开文件长度，移出后 Git 减少量还受旧提交保留和编码方式影响。

最大的已封存重复数据如下；同字节封包已在本机验证：

| 展开文件 | 文件长度 | 保留的封存索引 |
| --- | ---: | --- |
| `review/vip-route-2026-09-30/evidence/t18-actual-C-maintained-wait-abc-preparation-2/PREPARED.json` | 69.35 MiB | `review/vip-route-2026-09-30/evidence/t18-closed-maintained-wait-archive-1/MANIFEST.json` |
| `review/vip-route-2026-09-30/evidence/t18-actual-C-maintained-wait-abc-preparation-1/PREPARED.json` | 69.35 MiB | `review/vip-route-2026-09-30/evidence/t18-closed-maintained-wait-archive-1/MANIFEST.json` |
| `review/vip-route-2026-09-30/evidence/t18-natural-outcome-and-three-white-diagnostic-1/ALL-C-CURRENT-HU-PUBLIC-INPUTS.json` | 5.47 MiB | `review/vip-route-2026-09-30/evidence/t17-natural64-closed-archive-1/MANIFEST.json` |
| `review/vip-route-2026-09-30/evidence/t17-actual-C-first-change-abc-preparation-1/PREPARED.json` | 5.18 MiB | `review/vip-route-2026-09-30/evidence/t17-closed-local-phase-archive-1/MANIFEST.json` |
| `review/vip-route-2026-09-30/evidence/t19-last2-parent-scout-closure-1/FIRST-COMMON-PUBLIC-DIVERGENCES.json` | 4.27 MiB | `review/vip-route-2026-09-30/evidence/t19-last2-natural-closed-archive-1/RECEIPT.json` |
| `review/vip-route-2026-09-30/evidence/t18-natural-outcome-and-three-white-diagnostic-1/THREE-WHITE-PUBLIC-DRAWS.json` | 3.47 MiB | `review/vip-route-2026-09-30/evidence/t17-natural64-closed-archive-1/MANIFEST.json` |

两份各约 69.35 MiB 的 T18 `PREPARED.json` 已被 `t18-closed-maintained-wait-archive-1/MANIFEST.json` 覆盖；主要体积来自嵌入的 `roots` 数据。它们在历史报告中仍有直接链接，因此需把链接改成封存与恢复入口后再移出跟踪。

### 暂不列入可清理的材料

T52、T64—T65、T67、T77 的四份归档索引列出的分块当前不在本机。历史 README 指向的专用上传分支也不在本次远端分支清单中；当前远端公开的分支仅有 `main`。本次未验证这些旧备份仍能完整取回，因此其对应展开材料不纳入已验证清理候选。历史 `REMOTE-COMPLETION.json` 表示当时完成，不代表现在仍可取得。

当前发布证明、官方规则样本、被实际调用的研究脚本、活跃状态文件以及来源不明的未提交改动继续保留。具体归档规则见[研究证据索引](../research/INDEX.md#状态标记与归档规则)。

## 存储占比最高的目录和文件

以下是当前 main 的大目录，Git 列按本地唯一对象的代表路径归属：

| 目录 | 当前文件长度 | Git 当前对象存储长度 |
| --- | ---: | ---: |
| `review/vip-route-2026-09-30/evidence/t191-four-day-execution-1` | 1.40 GiB | 1.27 GiB |
| `review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution` | 1.19 GiB | 51.18 MiB |
| `review/vip-route-2026-09-30/evidence/t195-future-progress-formula-1` | 1.07 GiB | 580.14 MiB |
| `review/vip-route-2026-09-30/evidence/t39-t41-closed-evidence-archive-1` | 1.00 GiB | 1020.60 MiB |
| `review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1` | 642.97 MiB | 498.86 MiB |
| `review/vip-route-2026-09-30/evidence/t142-t131-closed-archive-1` | 327.19 MiB | 326.64 MiB |
| `review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1` | 311.60 MiB | 227.12 MiB |
| `review/vip-route-2026-09-30/evidence/t8-bounded-natural-geometry-1` | 297.27 MiB | 224.64 MiB |
| `review/vip-route-2026-09-30/evidence/t11-abc-informed-joint-author-1` | 288.31 MiB | 268.12 MiB |
| `review/vip-route-2026-09-30/evidence/t9-closed-natural-new8-archive-1` | 240.79 MiB | 238.94 MiB |

当前 main 的最大单文件为：

| 文件 | 文件长度 | 占当前文件长度 |
| --- | ---: | ---: |
| `review/vip-route-2026-09-30/evidence/t29-closed-common-natural-archive-1/closed-t29-common-natural-full.tar.gz` | 79.75 MiB | 0.60% |
| `review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/glm-i1-natural-development-1/match-data.tar.gz` | 69.45 MiB | 0.52% |
| `review/vip-route-2026-09-30/evidence/t18-actual-C-maintained-wait-abc-preparation-2/PREPARED.json` | 69.35 MiB | 0.52% |
| `review/vip-route-2026-09-30/evidence/t18-actual-C-maintained-wait-abc-preparation-1/PREPARED.json` | 69.35 MiB | 0.52% |
| `review/vip-route-2026-09-30/evidence/t27-t28-closed-natural-and-coverage-archive-1/closed-t27-t28-natural-and-coverage-full.tar.gz` | 69.19 MiB | 0.52% |
| `review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/S02/source-evidence.tar.gz` | 68.37 MiB | 0.52% |
| `review/vip-route-2026-09-30/evidence/t4-conditional-payment-batch-1/sol-i1-natural-development-1/match-data.tar.gz` | 67.59 MiB | 0.51% |
| `review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/S01/source-evidence.tar.gz` | 63.04 MiB | 0.48% |
| `review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wait-natural-1/wait-stage-002-raw.tar.gz` | 57.46 MiB | 0.43% |
| `review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wait-natural-1/wait-stage-001-raw.tar.gz` | 54.24 MiB | 0.41% |

已经从当前文件树删掉的大文件，也可能仍在 main 历史中。例如 `review/heuristic-baseline-campaign-2026-09-07/base-source.tar.gz` 为 84.29 MiB，当前路径已删除，但本地可达 main 历史仍保留约 84.13 MiB 的对象副本。

## 清理对 Git 体积的影响

### 整个 review 退出 Git 的边界

2026 年 10 月 9 日补核 main `46aa3277f2178fdceedfb6bd9913af900d0a9d96`：正式赛事默认 P0 approved-v4，测试赛事默认 G37-RF1。这两类赛事的标准入口不读取已有 `review/` 内容，发布校验实际读取 `prebuilt/` 中的证明副本；上述隔离校验所涉及的源码和发布文件相对审计基线未变。

当前自由赛自动续赛仍有明确依赖：[T227 控制器](../../tools/offline/free_match/rf1_controller.py) 会从 `review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/` 装入原控制器，还会校验运行清单指定的证明原件。因此，换机使用标准正式／测试赛事入口不需要研究数据，但复用当前自动续赛流程不能直接移除整个目录。先迁出并重新核验这些控制脚本、证明与下述进化依赖，再考虑整目录忽略。

仅添加 `.gitignore` 不改变已经跟踪的文件，也不移除历史对象；不会令当前仓库的正常完整拉取变小。

### 后续进化对旧 review 的依赖

按 2026 年 10 月 9 日实际代码核对，旧目录中仍有当前进化依赖，不能只按日期整目录退役：

- `src/hangma_bot/offline/vip_eoh_generate.py` 会读取并冻结 `review/llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py` 和 `sitin_process.py`。
- T200 的 `author_round.py` 读取 T185 的 `AUTHOR-BATCH.json` 并动态装入 `glm_max_transport.py`。
- T200 的续打和机械工具仍使用 `.private/t199-four-step-execution/` 中的 helper、来源计划、公开反例和恢复材料。
- 研究父包装载会递归检查重绑定、格式修复和评分修复的原父包、批次、源码及谱系。父代代码、`generation.json`、当前反例和来源绑定不能因为批次闭合就删除。

因此，899 项同字节重复展开载荷可以在保留封包与修复引用后退出默认代码交付；旧大规模逐桌运行原流和历史封包也适合外置。这里没有证明这些原始内容永远不再被回查。未来进化需要保留的最小来源和反例应先冻结成清单，再让其余整批载荷退役；外置后仍能按索引恢复。

### 其他电脑同步 main 的效果

| 其他电脑的状态 | 只提交当前 review 文件删除的效果 |
| --- | --- |
| 已完整同步到清理前版本 | 删除提交通常只需少量新对象，工作区会明显变小；后续不再提交大载荷时，新增同步较轻 |
| 已有仓库，但缺失期间多个大数据提交 | 仍可能需要下载未持有的历史对象，不能保证一次追上 main 就轻量 |
| 新电脑首次完整克隆 | 旧大文件仍在可达历史中，不会只因最新提交删掉文件就消失 |
| 希望已有电脑的 `.git` 也变小 | 工作区删除不会自动收回旧历史、标签和引用仍保留的对象 |

`fetch` 获取的是完成所选引用历史所需的对象，不仅是最新文件树。因此，要同时改善首次完整克隆和长期磁盘占用，需要在载荷外置后单独处理大文件历史及保留它们的引用。历史处理改变提交身份，需要独立协调其他电脑的同步。[git fetch](https://git-scm.com/docs/git-fetch#_description)、[git gc](https://git-scm.com/docs/git-gc#_notes)。

当前版本文件对象的本地存储长度合计 7.72 GiB，main 全部可达且已在本机的对象合计 7.92 GiB。部分克隆中仍有 5,990 个未下载的历史对象，本次用 `GIT_NO_LAZY_FETCH=1` 统计，未补拉，因此这不是远端完整仓库的精确传输量。

只删除工作区文件、新增忽略规则，或从当前树移出跟踪，不会自动去除旧提交保留的数据。要降低普通完整克隆的数据量，需先把大载荷可靠迁出、保留索引与恢复链，再单独处理 main 历史及保留旧对象的引用。本次没有执行历史改写或强制推送。[git gc](https://git-scm.com/docs/git-gc#_notes)

本机物理 `.git` 约 35.66 GiB，还包括本地 Codex 恢复引用、不可达对象和重复 pack。本机检查点中 600 多 MiB 的旧日志不在当前 main 可达历史中，不能当作新电脑必下的主线文件。它们属于另一个本机 Git 维护问题，不用于本次主线数据清理优先级。对象副本和差量编码的统计限制见 [git cat-file](https://git-scm.com/docs/git-cat-file#_caveats)。

清理核对的优先级为：已验证重复展开载荷 → 多 GiB 历史证据封包与分块外置 → 对应历史对象处理。生产源码、当前发布包、共享编译助手、文档与回归保留。

完整字节统计见[机器可读审计](git-storage-audit-20261008.json)。本次新增或更新的只有这份核对报告、统计文件和候选清单；项目数据没有删除。

## 从零拉取和长期追上 main 的历史瘦身方案

**建议保留代码提交历史，按经过核对的路径移除大数据的全部历史版本。** 同时清理当前文件树，并让新运行的大载荷继续保存在 Git 之外。此前当前文件对象约 7.72 GiB、主线已在本机的可达对象约 7.92 GiB，说明单独处理已删除的历史文件不会解决当前主要占用。

1. 完整历史和原始证据先备份到仓库之外，并验证可恢复。备份不能作为同一远端的旧分支或标签继续保留，否则完整克隆仍可能下载旧大历史。
2. 冻结公共工具与参赛依赖清单，保留生产源码、共享研究工具、发布证明、必要回归样本和薄索引。按用户明确的“后续进化仅在本机进行”，父包谱系、完整反例池、原始回复、旧批次与研究记录可以保存在本机数据目录，无须随 Git 分发。899 项重复数据仅是其中的一小批，不能当作完整瘦身范围。
3. 在独立、完整的仓库副本中生成大数据历史路径清单，包含曾经改名或移动前的路径。使用 `git filter-repo` 从相关提交和标签中移除这些路径，保留代码历史和新旧提交映射。不能按大小一刀切删除受校验的预编译文件；完成公共工具、发布证明及文档抽离后，可以从历史移除整个旧 `review/` 前缀。
4. 验证当前代码及所有必要发布文件字节保持、配置与发布包校验通过、研究工具和保留反例仍可读取。验收使用普通完整克隆，以及从较旧的清理后提交追上 main 的实际传输量，不依赖额外浅克隆参数。
5. 本地结果通过后，单独发布改写后的 main，并处理仍指向旧大历史的远端标签和分支。其他电脑需一次性备份本地修改、重新对齐新历史；最省事的是保留旧检出另作备份，再克隆已瘦身的仓库。不能把旧历史重新合并并推回。
6. 后续大日志、整批原流和封包不再入 Git；入库只保留代码、必要小样本、报告、索引与摘要。这样长期缺席后追上 main 只需补小量代码和元数据。

工具调用的形式如下，路径清单必须先核定，且只在独立副本执行：

```bash
git filter-repo --invert-paths --paths-from-file approved-large-data-paths.txt
```

`git-filter-repo` 不自动跟随历史改名，需要覆盖旧路径；历史改写会产生新的提交号，工具提供 `commit-map`。GitHub 推荐用它移除早期提交中的大文件。[GitHub 大文件处理](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github#removing-a-file-that-was-added-in-an-earlier-commit)、[git-filter-repo 项目与文档](https://github.com/newren/git-filter-repo)。

改写发布后，旧历史上的电脑不能在第一次迁移时继续按原来的普通 pull／合并流程操作；一次对齐后，后续正常 pull 恢复。长期轻量取决于新的可达历史始终保持轻量，不保证与网速无关的固定耗时。该方案目前只有核对和说明，没有实际改写提交或推送。

## 公共工具与本机研究分离的具体方案（2026-10-09）

**可行；进化仍需使用的历史数据，也可以完整保存在本机并退出 Git。** 本节按用户确定的边界规划：其他机器取得共享工具和正式参赛所需文件，本机另外拥有完整研究数据。剥离指退出版本控制，历史数据的本机原件继续保留。

### 目标目录与规模

| 位置 | 内容 | 是否随 Git 分发 |
| --- | --- | --- |
| `src/hangma_bot/`、`scripts/` | 生产核心、共享进化与评估工具、参赛和自动续赛入口 | 是 |
| `tests/`、`configs/` | 工具回归、必要小样本、无凭据的配置模板 | 是 |
| `prebuilt/` | 当前发布包、编译助手、启动实际读取的证明副本 | 是 |
| `doc/research/` | 当前研究结论、框架合同、来源索引与迁移映射 | 是，精选小文件 |
| `local-data/review/` | 旧 `review/` 完整原目录树、候选、父代谱系、原始请求、结果、源码快照和封包 | 否，本机数据 |
| `artifacts/`、`.private/` | 新运行产物、本机配置、凭据与运行状态 | 否，沿用现有约定 |

最新 `46aa3277f2` 的 `review/` 有 131,336 个已跟踪文件、13,466,477,376 字节（12.542 GiB）。整个当前 main 排除它后剩 421,247,987 字节（401.73 MiB），主要为 `datasets/` 与 `game-records/`。这只是当前文件长度，不是改写后完整克隆的传输量；迁出的公共工具和精选文档会增加少量文件。

同一边界也适用于 `datasets/`、`game-records/`、`datamart/` 中的大批离线数据：三者当前合计约 370.87 MiB。核对实际引用后，将完整数据移至本机数据根，只有共享回归确实需要的小样本提升到 `tests/fixtures/` 等受维护位置。完成这部分抽离后，共享当前树有望降至几十 MiB 级，最终规模以必要样本、文档和工具清单为准；历史传输量仍需单独验收。

已核对的 Sitin tools、T199 runtime、T200 工具和 T227 脚本合计约 5.84 MiB 的 Python 源码，尚不含下面列出的其他依赖。旧目录全部 Python 文件有约 202.69 MiB，包含大量批次候选和源码快照，不能把所有 `.py` 都当作公共工具搬入新代码目录。

### 公共工具抽离清单

下表是已经确认的入口和依赖边，实施前还需闭合它们的真实文件读取和动态导入，不能只复制入口文件。

| 已确认位置 | 共享维护内容与处理 |
| --- | --- |
| `review/llm-guided-heuristic-route-2026-09-15/tools/` | 抽离实际使用的生成、回复封套、解析、隔离装载和相关工具；共用逻辑进入现有 `offline` 模块，命令入口进入 `scripts/`，工具测试进入 `tests/` |
| `review/vip-route-2026-09-30/evidence/t200-eoh-fast-evolution-1/` | 抽离当前生成、评分检查、输入准备和完整续打驱动；原批次计划、父代和采样数据进入本机数据目录 |
| T185 的 `glm_max_transport.py` | T200 实际动态装入的模型传输工具，需要共同抽离；`AUTHOR-BATCH.json` 是旧批次数据，本机保留并由显式输入定位 |
| T227 的 `controller.py`、T199 的 `runtime/` | 抽离当前自由赛控制、运行根校验、自然终态与后台处理；更新入口路径和运行清单，不启动另一 owner |
| T194 `wiring/free_watchdog.py`、T165 `watchdog_nonblocking.py`／`watchdog.py`／`analyze.py`、T163 `summarize_closed.py` | T199/T227 继续调用的真实工具链，需要抽离其被调用逻辑与测试 |
| `.private/t199-four-step-execution/` 中被 T200 装入的 helper | 复用代码与本机数据分离；只提升已核需要共享的代码，计划、公开输入原件与运行状态仍在本机 |

生产规则与策略继续遵守现有模块边界。赛事生命周期逻辑归 `application`，记录副作用归对应适配器，离线生成与分析归 `offline`，`scripts/` 提供运行入口。迁移不新增线上到 `offline` 的反向依赖。

### 顺序与验收

1. **冻结与备份。** 固定实施提交，逐项登记本机 `review/` 的原路径、大小、SHA-256、跟踪状态以及未提交修改。完整数据和完整 Git 历史另存独立备份，核验可恢复；当前部分克隆缺少历史对象，不能直接称作完整历史备份。在用研究任务的输入与输出也要登记。
2. **先抽离工具。** 在旧路径仍存在时完成上述迁移，去除公共代码对历史 `review/` 或 `.private/` 内代码的硬编码导入。本机数据路径改为明确的配置／命令行输入。同步 README 场景入口、AGENTS 证据索引入口、架构与主技术方案及受影响接口文档。
3. **保持历史原件身份。** 旧记录中的来源路径和摘要保持原字节；用旧路径到 `local-data/review/` 的迁移映射定位数据。不要批量改写历史 `generation.json`、收据或父包绑定，也不要用外部符号链接绕过现有运行根校验。新批次按迁移后的工具版本重新冻结来源。
4. **核验与重新绑定发布。** 当前 P0/RF1 的 `source_manifest` 包含 `src` 下的源码，修改离线工具路径也可能改变包装身份。通过现有冻结逻辑生成新版本包装与配置，核对算法公式、核心候选身份、规则语义和批准依据是否保持；重新跑受影响工具回归、四模式包校验及生命周期／恢复检查。不得手填摘要或伪造通过收据。正在使用的冻结运行根继续保持原字节，后续交接自然完成后才采用新根。
5. **迁出当前文件树。** 验证新参赛目录不带本机数据即可装载，验证本机进化能装入现有父代、读取原输入并复用已保存回复。再把旧目录完整迁至 `local-data/review/` 并校验清单，令 Git 中 `review/` 已跟踪文件为零；加入 `/local-data/`、`/review/` 忽略规则。所需薄文档和合同已在共享目录。新数据默认输出到被忽略的位置。
6. **改写历史与发布切换。** 在完整独立副本中移除旧 `review/` 前缀，补齐此前在其他位置的同类历史数据路径；处理可克隆分支和标签，防止它们继续保留大对象。核对保留文件字节，执行普通完整克隆及从较旧的清理后提交同步最新 main 的验收，记录传输量与耗时。最后发布经过核验的新 main、提交映射和迁移说明，其他电脑一次性备份本地改动并对齐新历史，随后恢复正常 pull。

整个旧目录均已抽离时，独立副本中的核心过滤命令可以是：

```bash
# 仅用于完成抽离、备份与验证后的完整独立副本。
git filter-repo --path review/ --invert-paths
```

若历史中同类数据曾位于其他前缀，应使用已经核定的路径清单一起过滤。工具不会自动追随改名。[git-filter-repo 官方手册](https://raw.githubusercontent.com/newren/git-filter-repo/main/Documentation/git-filter-repo.txt)。

### 完成标准

- 新机器用普通完整克隆得到当前参赛包和公共工具，无须取得 12.54 GiB 本机研究目录；适配目标系统的编译制品仍按现有发布要求提供。
- 本机历史数据原件、未提交修改、父代装载、来源绑定和当前反例读取均可核验；数据缺失明确报错。
- Git 当前文件树和可克隆历史中都不再保存旧 `review/` 大载荷；新运行产物也不会重新入库。
- 体积结论依据实际完整克隆和对象统计，不把工作区文件长度当作远端传输量，不把服务端存储回收时间当作克隆速度保证。

本节是已核对依赖后的执行方案；公共工具迁移、数据剥离、历史过滤及远端发布尚未执行。
