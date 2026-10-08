# T182 原开发批次资源调度补充契约

本补充只改变原 512 个完整桌的执行资源安排。固定 S02、三个原候选、32 个母来源、每来源四换座、每桌八单局、规则、种子、对手装配、逻辑预算、评分公式和原开发选择规则全部由原 [DEVELOPMENT-PLAN.json](./DEVELOPMENT-PLAN.json) 及其源码身份决定。两个 worker 直接调用冻结的 `run_development.run_table`，不替换函数，不修改该模块的 globals，不新增模型或作者，不缩分母。

## 本次交接边界

仅 root 可以在旧离线研究 runner 安全退出之后执行准备器。准备器只读 `ps`，不停止进程，也不向玩家、控制器、watchdog 或其他进程发送信号。旧研究 PID 若被其他命令复用，记录该新命令；只要它仍是交接证据中的原命令就拒绝切换。命令比较采用 `shlex.split` 后的完整参数序列。

本次已存在的交接证据必须一起冻结：

| 原件 | 作用 |
| --- | --- |
| [RESOURCE-OLD-RUNNER-HANDOFF.json](./RESOURCE-OLD-RUNNER-HANDOFF.json) | 原命令、原 PID、原 512 分母、恰 14 个已完成桌及其 START/CLOSURE 原字节 pin；确认无活桌、未提取积分 |
| [RESOURCE-OLD-RUNNER-EXIT.json](./RESOURCE-OLD-RUNNER-EXIT.json) | 原研究实际退出、14 桌完成、零活桌及未向自由赛进程发信号的交接事实 |
| [RESOURCE-OBSERVATION-001.json](./RESOURCE-OBSERVATION-001.json) | 绑定原开发计划的硬件与资源只读观察；不是动作时限或可靠性证明 |

准备器重核原 14 桌终态、实际八单局、零运行异常计数、焦点评分调用数、输入捕获终态、配对证明和三对手身份；只核状态/计数/身份，不提取结算分数，不解码候选评分。对每个原桌冻结 `START.json`、`CLOSURE.json`、`PAIRING-IDENTITY.json`、`focal-decisions.jsonl.gz`、`views.jsonl.gz` 五个原文件的 SHA256 与字节数。原 START/CLOSURE 必须与交接 pin 相同。未知、缺文件、失败、漂移或任何已存在未闭合目录都拒绝生成计划。

原序号按原计划母来源顺序、换座顺序、臂顺序展开，0 起始：S02 为臂 0，三个候选为臂 1—3。原序号 0—13 必须恰为交接的 14 个旧完成桌；14—511 必须恰为 498 个从未开始的剩余桌。全 512 桌任务身份都列入 `RESOURCE-SCHEDULING-PLAN.json`。越计划目录、额外桌或少于该分母均不能悄悄排除。

准备器冻结原开发计划、原生产源码清单、原研究实现、三个新脚本、本契约、全部静态同目录研究 import 及上述交接证据。另外冻结[独立读回格式修复入口](./close_development_readout_repair.py)、[修复契约](./DEVELOPMENT-READOUT-REPAIR-CONTRACT.md)、[实际成功收据/负例验证](./DEVELOPMENT-READOUT-REPAIR-VALIDATION.json)及[原helper36756实际失败](./DEVELOPMENT-FIRST-INPUT-CHECK-FAILED.json)。验证只允许生产已确认的信息审计和对象ID格式，原统计不变；不能用文件存在代替成功分母/负例及源码pin检查。源码或原计划出现漂移即停止；禁止运行 `python -O` 关闭原 runner 的审计断言。准备不生成 WorldState、完整桌、评分、成绩或统计。

修复首个只读预检因本进程降低优先级被sandbox EPERM拒绝，未取共用锁或读收据，另存[实际资源权限失败](./DEVELOPMENT-READOUT-REPAIR-PRECHECK-FAILED-001.json)，新资源计划也冻结它。同一只读入口后续按已有授权用require_escalated完成；这不表示API、策略、评分或牌局失败。

## 固定两个后台研究槽

运行器只接受 `--worker 0` 或 `--worker 1`。任务分区固定为 `worker = ordinal % 2`，按各自剩余序号递增执行；不得按积分、完成速度或观察到的分歧增删任务。每个进程只串行调用原函数，每个槽有自己的独占非阻塞研究锁，故最多两个 CPU worker 进程。重复占槽立即失败。

两个进程均要求 nice 至少 15 和 macOS 后台 IO。模拟期间只持各自 `.resource-scheduling-worker-0.lock` 或 `.resource-scheduling-worker-1.lock`，不持 `.private/t165-live-watchdog/postprocess.lock`，允许独立赛后审计并行。此安排并不证明官方 1 秒/3 秒动作窗口或真实赛事可靠性。原每桌墙上时间保护仍按原计划执行；资源竞争若触发原失败条件，保留原件并拒绝整批完成，不能改阈值后续跑。

每桌执行前核调度计划、本脚本、所有冻结研究/生产实现与原计划 pin，确认原桌目录尚不存在。在独立 `resource-scheduling/tasks/task-NNNN/BEFORE.json` 记录调度计划 pin、原 DEV 计划 pin、新 runner pin、任务身份、worker、PID 和原目录未开始状态。时间戳使用 Unix 秒；持续时间使用单调时钟秒。

随后原 `run_table(index, rotation, arm_index, original_plan)` 一次调用负责原 START、评分费用、输入捕获、配对证明和原 CLOSURE。原 START 仍绑定原 `DEVELOPMENT-PLAN.json`，新调度身份只在新收据中出现。该调用保持原牌山、初庄、八单局、策略可见信息权限和实际三对手映射。调度代码不向策略传完整世界，不读取积分。

调用后重核源码/计划和执行前收据；成功时重验原终态并冻结五个原文件，在新 `AFTER.json` 绑定执行前 pin、实际原函数调用状态、完成/失败、源码稳定和全部原文件 pin。失败留原目录、原费用、原捕获、原 CLOSURE 和新收据；可用的原文件子集也冻结。目录已存在即拒绝重试，不补根，不改 seed，不正常回退 R18。

失败原件逐件pin；任一文件不可读或缺失记入 `original_table_pin_errors`，保留其他可读原件的已有pin。未知不能默认空集合成功。成功AFTER必须该列表为空，否则整体仍未知/失败。

一次失败只停止本 worker，不向另一 worker 发信号，也不杀其正在算的桌。该 worker 仍新建失败 `CLOSE.json`；另一个槽可自然完成。调用数以真实 AFTER 的 `original_run_table_called` 计数；缺收据的调用状态列为未知，不能用排队次数冒充实际支出。整个批次只要任一槽未成功真实闭合就不能授完成。重新运行遇到既有 worker 或桌目录即拒绝，失败/未知任务不得自动重试。

## 完整闭合与原统计

`close_development_resume.py` 先取得两个独立研究槽锁，以确认 worker 已离开槽。两份真实 START/CLOSE 必须成功、源码稳定、无失败，并覆盖各槽恰当的全部剩余序号。每个新桌均须有身份一致的 BEFORE/AFTER、完整原终态和全部五个稳定 pin。旧 14 桌原件也重核。仅全 512 桌和所有原件齐全稳定之后才允许调用新 `close_development_readout_repair.main()`。

闭合包装器外层不持共用 `postprocess.lock`；新修复main自己取得该锁，并直接复用原预检、积分account、来源比较和bootstrap函数，开发选择AST不变。评分收据只校正生产对手信息诊断与对象ID格式，诊断原文/计数保留，焦点和非法/回退/未知/不完整仍失败。包装器不另算统计，不替换选择规则，不授确认强度。

修复读回成功之后，新 `RESOURCE-SCHEDULING-CLOSED.json` 再冻结开发闭合、调度计划、新脚本/合同/全部 import、交接原件、两个 worker 闭合、498 对桌前后收据和原 512 桌全文件，并声明旧完成 14、新完成 498、4096 单局、两槽成功和原科学设定不变。字段明确为 `repaired_dev_readout_called_once_after_all_terminals=true`、`old_original_readout_failed_probe_preserved=true`，不声称旧错误校验已成功。生产源码仍以原清单冻结。所有文件排他新建，不覆盖原件。

原读回成功后若追加调度闭合核验失败，原 `DEVELOPMENT-CLOSED.json` 保留，但本次调度闭合仍未知；不能把已有原读回当作调度闭合成功，也不得覆盖它重算。后续由 root 检查两个闭合都成功后才推进确认准备。本补充本身不授真实动作截止、可靠性、正式强度、发布或上线门。

## 执行入口及当前验证边界

本次实现仅创建三个新脚本及本契约，做语法、AST、导入和原字段静态核对；不执行下列入口，不创建调度计划、世界、桌或成绩。实际切换由 root 执行，工作目录为仓库根，使用同一 `.venv` 且不启用 `-O`。

```sh
.venv/bin/python review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/prepare_development_resume.py --old-runner-pid 85381 --old-runner-session 18422 --checkpoint-confirmed
.venv/bin/python review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/run_development_resume.py --worker 0
.venv/bin/python review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/run_development_resume.py --worker 1
.venv/bin/python review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/close_development_resume.py
```

两个 worker 需由 root 分别启动；上述命令顺序展示入口，不表示在一个 shell 中顺序等待两个 worker。原完整桌是统计单位，原母来源聚类身份保持不变；资源调度计划不是新增独立样本。
