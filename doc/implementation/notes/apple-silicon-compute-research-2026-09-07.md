# Apple Silicon 计算优化调研：M4 Pro / M5 Pro，各 48GB

> 调研日期：2026-09-07。硬件型号与容量由用户确认；本机只读检查确认 arm64、macOS 26.4.1、项目 Python 3.11.15。仓库参考提交：`2b8197c`。本文是选型研究，不代表已实施、已测得加速或变更现有模块契约。
>
> 证据标记：“厂商确认”指框架或芯片一手资料，不是杭麻赛事官方规则；“当前观察”指仓库代码或本机检查；“工程建议”指本项目取舍；“待实测”指尚未验证的性能与兼容性。文中沿用 [统一术语表](../../../UBIQUITOUS_LANGUAGE.md)。

## 1. 结论与适用范围

**工程建议：这两台 Mac 可以承担当前项目的小模型训练、模拟评估与线上推理。优先采用 CPU 多进程模拟、GPU 批量模型计算、CPU 独立保底的组合。不要先把整套杭麻规则迁移到 GPU。** 数据质量、规则一致性与完整桌赛吞吐很可能比模型容量更早成为约束；这是项目判断，尚无性能剖析证明瓶颈占比。

图形处理器（`GPU`，适合同时处理大量相似计算）并不会自动执行普通 Python 分支和递归。中央处理器（`CPU`，执行通用逻辑和控制流程）仍适合规则推进、少量候选排序和不规则搜索。统一内存（`Unified Memory`，本机 CPU/GPU 共用物理内存）有利于容量与数据访问，但不消除调度、同步、数据格式转换及带宽竞争。[MLX 统一内存](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html)、[Apple 小网络调度开销说明](https://developer.apple.com/metal/tensorflow-plugin/)

| 工作负载 | 建议路线 | GPU 价值 | 相对开发难度 |
| --- | --- | --- | --- |
| 现有启发式候选评分 | 保持 CPU，测量后优化重复计算 | 单次候选少，可能反而更慢 | 低 |
| 胡牌、向听、有效牌计算 | 有界缓存、紧凑计数；热点再尝试 Numba 编译 | 批量规模足够大时才探索 GPU | 中；规则对拍是主要成本 |
| 大量完整桌赛模拟 | 按独立牌山根组分片，多进程及两机并行 | 规则模拟本身无自动加速；模型调用可批量化 | 中 |
| 小型候选结果模型训练 | 首选 PyTorch MPS；同一模型原型比较 MLX | 高潜力，是否更快取决于模型与批量 | 低到中；不包含构建可靠训练标签 |
| 线上小模型推理 | 先比 CPU 与 MPS；需要时再评 MLX/Core ML | 单请求不保证更快；同窗候选批量更有意义 | 接通低，满足时限与降级中 |
| 启发式搜索、展开模拟 | CPU 管搜索与推进，GPU 批量评估叶节点 | 模型较重、独立节点较多时有价值 | 中到高 |
| 全 GPU 杭麻模拟器/搜索器 | 暂缓；热点原型通过后才考虑 | 上限可能高，验证与改写成本也高 | 高 |

候选结果模型（`CandidateOutcomeModel`，从玩家观察与候选动作预测本局四座位联合积分结果分布）是项目已有方向；这里讨论其计算后端，不引入线上语言模型。

## 2. 两台 48GB 机器的实际含义

**工程建议：48GB 对项目规划的小型网络是宽裕的起点，优先用来容纳数据缓存与多个模拟进程；不能据此承诺任意批量或搜索规模。**

| 项目 | M4 Pro 本机 | M5 Pro 另一台 | 证据边界 |
| --- | --- | --- | --- |
| 安装的统一内存 | 48GB | 48GB | 用户确认 |
| 芯片系列内存带宽 | 273GB/s | 最高 307GB/s | Apple 标称；不是 Python 程序实测吞吐 |
| GPU 神经网络加速器 | 不套用 M5 的新增描述 | Apple 确认每个 GPU 核心具有 Neural Accelerator | 具体网络是否受益由框架、算子与形状决定 |
| 精确 CPU/GPU 核心配置 | 未核验 | 未核验 | 不由芯片名称推定满配核心数 |

厂商依据：[M4 Pro 发布资料，2024-10-30](https://www.apple.com/newsroom/2024/10/apple-introduces-m4-pro-and-m4-max/)、[M5 Pro 发布资料，2026-03-03](https://www.apple.com/newsroom/2026/03/apple-debuts-m5-pro-and-m5-max-to-supercharge-the-most-demanding-pro-workflows/)。按两项带宽标称值相除，307/273 约为 1.12；这是带宽比值计算，不能推导模型或模拟快 12%，也不能套用 Apple 特定 AI 演示的倍数。

48GB 不是“CPU 48GB 加独立显存 48GB”。系统、开发工具、多个 Python 进程、模型参数、训练中间结果和 GPU 缓存共同占用它。两台机器也不是透明的 96GB 共享池；跨机数据必须显式传输。

初期安排：M5 Pro 作为训练主机，M4 Pro 承担开发和独立模拟；运行官方赛事时，赛事机器暂停重型训练与大规模模拟。两机都空闲时，各自执行不重叠的完整实验根组，再汇总。M5 Pro 的训练主机定位是待实测的调度建议，不能用它的成绩替代 M4 Pro 的部署延迟验收。

## 3. Python 框架选型

**工程建议：首先验证 PyTorch 的 CPU/MPS 两种后端；只给同一个代表模型做一次 MLX 对照。长期维护一个训练实现，不同时维护两套逐渐分歧的网络。**

Metal 是 Apple 的 GPU 计算接口；Metal Performance Shaders（`MPS`，Apple 的加速算子库）是 PyTorch 在 Mac 上的 GPU 路线。它与 CUDA 的英伟达 GPU 路线不同。

| 框架 | 能复用什么 | 本项目取舍 | 一手资料 |
| --- | --- | --- | --- |
| PyTorch + MPS | Python 网络、自动求导、优化器，使用 `mps` 设备训练/推理 | 首选验证；保留同一网络的 CPU 路径，未来转其他硬件较方便；含 CUDA 专用算子的外部代码仍需改造 | [MPS 后端](https://docs.pytorch.org/docs/stable/notes/mps.html) |
| MLX | NumPy 风格数组、自动求导、网络与优化器、编译、统一内存 | Mac 优先的新模型值得对照；不是只支持大语言模型；也不是 PyTorch 模型直接换设备名 | [MLX 官方文档](https://ml-explore.github.io/mlx/build/html/index.html) |
| Core ML + coremltools | 转换已训练模型，在 macOS 中用 Python 调用预测 | 固定模型的部署优化候选；需验证转换、算子和数值；不作为本项目通用训练循环首选 | [模型预测](https://apple.github.io/coremltools/docs-guides/source/model-prediction.html) |
| NumPy + Numba | 数组处理，把适合的数值循环编译为本机 CPU 代码 | 优先用于离线热点；Numba 官方 CPU 平台支持 osx-arm64，官方 GPU 文档主要是 CUDA，不能把 `njit` 当作 Metal 加速 | [平台支持](https://numba.readthedocs.io/en/stable/reference/support_tiers.html)、[入门与 GPU 目标](https://numba.readthedocs.io/en/stable/user/5minguide.html) |
| Python multiprocessing / ProcessPoolExecutor | 多 CPU 核心执行独立桌赛批次 | 当前模拟评估最直接的并行起点；持久进程，避免每一步序列化完整世界 | [Python 3.11 多进程](https://docs.python.org/3.11/library/multiprocessing.html) |
| Taichi + Metal | 从 Python 编写受约束的并行计算内核 | 将来只试固定形状热点；不自动编译现有全部 Python 对象与规则 | [Taichi 入门 v1.6.0](https://docs.taichi-lang.org/docs/hello_world)、[develop 类型支持表](https://docs.taichi-lang.org/docs/master/type) |
| JAX + jax-metal | 数组变换、编译与批量模型计算 | Apple 当前页面仍标实验性，部分数据类型与测试不支持；本项目不以此作为首发后端 | [Apple JAX 插件](https://developer.apple.com/metal/jax/) |
| TensorFlow + tensorflow-metal | 现成 TensorFlow 模型的 Mac GPU 训练 | 有旧模型时可考虑；仓库没有此依赖，新增一套生态的理由不足 | [Apple TensorFlow 插件](https://developer.apple.com/metal/tensorflow-plugin/) |

文档版本边界：本次 MLX 页面显示 0.32.2；PyTorch、Numba 为随发布更新的 stable 页面；Taichi 分别引用 v1.6.0 教程与 develop 类型表；Apple JAX 页面最高列出的插件版本为 0.1.0。它们说明能力与限制，不构成已验证的依赖锁定组合。实际接入应锁定 Python、macOS、框架及相关依赖版本，先做前向、反向、保存/加载与真模型算子检查。

神经网络引擎（`Neural Engine`，Apple 独立的模型计算硬件）与 GPU 不同，也不等于 M5 GPU 核心内的 Neural Accelerator。PyTorch 的 `mps` 路径表示 GPU；Core ML 的计算设备选项可允许系统使用 CPU、GPU 和 Neural Engine，但不保证每层都由某一种硬件执行。训练和推理不必用同一设备，但必须使用相同网络语义、特征编码和通过校验的模型产物。[Core ML 预测与设备选择](https://apple.github.io/coremltools/docs-guides/source/model-prediction.html)

Taichi 的 develop 类型表仍将 Metal 的部分 64 位类型和 f16 标为不支持；不能根据芯片支持某种类型，就推定框架支持。MLX 也提供 [自定义 Metal 内核](https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html)，但那已经涉及内核代码、并行布局与验证，不属于普通 Python 低成本优化。

## 4. 结合当前仓库：先优化哪里

**当前观察：代码已有 CPU 模拟和评估路径，尚未建立机器学习框架依赖；调研不能把未来规划误写成已接入能力。**

| 观察位置 | 已看到的事实 | 工程建议 |
| --- | --- | --- |
| [依赖配置](../../../pyproject.toml) | 正式依赖仅 httpx；本机项目环境未发现 numpy、numba、torch、mlx、coremltools、taichi | 独立实验环境做选型，不在运行赛事的环境临时安装框架 |
| [V2 策略](../../../src/hangma_bot/policy/heuristic_v2.py)、[评分](../../../src/hangma_bot/policy/evaluation_v2.py) | 消费规则候选与事实，Python 分项评分、排序、协作式截止检查 | 首先计时；少量标量评分通常没有足够 GPU 工作量 |
| [手牌分析](../../../src/hangma_bot/hangma/hand_analysis.py) | 递归、元组状态、`lru_cache(maxsize=65536)`；已经有有界缓存 | 分别测冷缓存与热缓存；若是热点再改紧凑状态或编译，不重复提出“先加缓存” |
| [模拟引擎](../../../src/hangma_bot/simulation/engine.py) | 保存完整世界状态，通过 HangmaRules 推进 | 以完整实验根组作为进程任务，继续共用唯一规则来源 |
| [评估器](../../../src/hangma_bot/offline/evaluate.py) | 当前实验按 seed 和变体循环，`drive_match` 按决策推进 | 在独立实验层分片；异步函数本身不等于多核计算 |
| [动作预算](../../../src/hangma_bot/application/deadline.py) | 默认增强截止比例 0.5、保底 0.7、最晚发送 0.85，实际受权威剩余时间限制 | 直接复用预算；不能把 1 秒/3 秒整段交给 GPU |

以上是源码阅读，不是热点剖析。`hand_analysis` 的真实成本、缓存命中率、进程序列化成本和每分钟完整桌赛数都待实测。

第一步适合测量规则分析、候选评分、完整世界推进、观察编码、记录写入各占多少时间。若 80% 时间在规则推进，即使把剩余 20% 模型计算无限加速，总体也最多约 1.25 倍；这是用于说明瓶颈的假设算例，不是仓库测量。

Numba 需要可编译的数值数据和控制流。不能直接给包含复杂对象、异步操作和现有缓存装饰器的整个函数加一个装饰器就承诺完成。若修改规则热点，算法继续归 `hangma`，生产与模拟调用同一份实现，并通过官方金例或 `fan-calc` 与既有回归。不能在 `simulation` 再写一套“GPU 杭麻规则”。

## 5. 模拟与搜索如何使用 CPU、GPU 和内存

**工程建议：先把独立实验并行起来，再批量化真正昂贵的数值计算。**

1. 本地模拟按独立牌山根组分片。同组保留基线、候选及换座位配对；完成运行时 `Rounds` 指定的整个桌赛再统计。每个工作进程独立持有世界与规则对象，集中汇总轻量结果。Python 3.11 的 macOS 默认使用 `spawn` 创建进程，应在子进程初始化所需资源，不能依赖父进程 GPU 上下文被安全继承。[Python 多进程](https://docs.python.org/3.11/library/multiprocessing.html)
2. 工作进程数先比较 1、2、4、6、8，不据逻辑 CPU 数直接开满。测总吞吐、单进程峰值和缓存重复占用；限制每个进程内部计算库线程数，避免多进程再乘多线程。上述数列是测试点，不是核验后的最佳配置。
3. 模型进入模拟策略后，先实现一个进程内部的批量预测。确有调用开销瓶颈时，再考虑离线批量推理工作进程；传入的仍是玩家观察（`PlayerObservation`，当前座位依法可读的信息），不能因为离线运行就把完整世界状态（`WorldState`，包含四家手牌和未来牌墙）泄漏给学生策略。
4. 展开模拟（`Rollout`，从候选动作继续模拟后续过程）可以按独立采样并行。CPU 处理规则推进与搜索树，GPU 一次评估许多叶节点。树的动态分支、哈希表、优先队列和小对象访问并不天然适合 GPU；全量迁移需要重整数据布局和控制流。
5. 训练数据采用紧凑数组、按需批量读取；可用 [NumPy memmap](https://numpy.org/doc/stable/reference/generated/numpy.memmap.html) 映射磁盘文件，避免每个进程各加载一份完整数据。内存映射不意味着整份数据永驻内存，也不自动使跨框架张量零拷贝。用于网络的特征和整数规则计数分开管理。

两机实验保留相同代码、规则、策略、数据划分和随机源版本，机器身份另记。不能因为机器速度不同就截断桌赛并拼接统计；GPU 浮点差异也可能改变分数接近时的排序，应检查最终动作变化而不只比较损失值。

厂商确认：MLX 0.32.2 已提供基于 TCP 网络环的通信后端、消息传递接口（`MPI`，多进程/多机通信标准）及数据并行训练示例。其 JACCL 通信后端还支持 macOS 26.2 起通过 Thunderbolt 5 使用远程直接内存访问（`RDMA`，减少跨机数据传输开销）；需要恢复模式启用及连接拓扑配置。本次未核验另一台机器的系统版本、连接线和配置。[MLX 分布式通信](https://ml-explore.github.io/mlx/build/html/usage/distributed.html)

工程建议：两机各训练一份模型、同步梯度属于数据并行；将同一模型拆到两机是另一种更复杂方案。二者都不会自动形成普通程序可用的 96GB 数组。对目前的小模型，通信和慢节点等待可能抵消收益；先用独立实验分片，需要同步训练时再测。线上策略执行保持本机可独立完成，不依赖另一台机器实时返回结果。

## 6. 48GB 统一内存怎样用得有效

**工程建议：控制总工作集和中间结果，比设法“占满显存”更重要。**

为了估算量级，假设一个 1000 万参数模型全部用 32 位浮点训练，参数、梯度及 Adam 的两份优化器状态，每参数合计约 16 字节，约 160MB；尚未包括中间激活、临时工作区、额外权重副本和分配器缓存。这个算例解释小模型的参数通常不会单独吃满 48GB，不代表某个尚不存在模型的峰值预测。

针对两台各 48GB 的机器，可把“项目全部重型任务合计先控制在约 28–32GB，余下留给系统、开发工具和波动”作为初测安排。它不是系统保证的 GPU 可用额度，也不是框架分配比例设置。根据内存压力、交换空间增长和持续运行峰值再调整；正式赛事机器不靠磁盘交换承载实时计算。

建议依次优化：

- 用有界规则缓存和紧凑样本提高复用，记录命中率和每进程内存。四个隔离身份进程不会自动共享 Python 缓存和模型对象。
- 模型、固定形状工作缓冲和常用编码在启动阶段准备好。批量内保持张量计算，减少逐候选 `.item()`、转 Python 列表或跨框架转换造成的同步。
- 训练从 32 位浮点（`FP32`）基线开始；再测半精度或脑浮点（`FP16/BF16`，减少数值位宽的格式）是否满足具体算子支持、数值稳定性与校准要求。规则合法性和积分结算仍使用精确规则计算。
- 按框架文档记录实际活动内存、驱动分配和缓存，而不是相加重复计算同一份物理内存；不关闭保护阈值作为默认优化。

MLX 的共享数组内存可以减少 CPU/GPU 显式搬运需求，但惰性求值（`Lazy Evaluation`，先记录计算、需要结果时再执行）和异步执行要求明确计时边界。[MLX 统一内存](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html)、[惰性求值](https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html)

厂商确认：PyTorch 提供 MPS 内存水位及 `PYTORCH_ENABLE_MPS_FALLBACK` 算子回退设置；MLX 提供活动、峰值及缓存内存统计。MLX 的 `set_memory_limit` 是指导额度，不能视为严格的进程隔离配额。统一内存不意味着 PyTorch、MLX、NumPy 或多个进程之间任意转换都无复制。[PyTorch MPS 环境变量](https://docs.pytorch.org/docs/stable/mps_environment_variables.html)、[MLX 内存管理](https://ml-explore.github.io/mlx/build/html/python/memory_management.html)、[MLX 内存限制](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.set_memory_limit.html)

## 7. 线上推理与 1 秒/3 秒窗口

**工程建议：线上以端到端尾延迟选择 CPU 或 GPU。GPU 利用率和离线每秒样本数不能作为上线依据。**

Apple 明确指出，小网络、小批量可能因 GPU 调度开销而比 CPU 慢。这个结论来自 TensorFlow Metal 文档，是比较小模型时必须检验的机制；它不是 PyTorch/MLX 本项目实测结果。[Apple 说明](https://developer.apple.com/metal/tensorflow-plugin/)

默认预算在完整剩余窗口下，仅约前 0.5 秒/1.5 秒用于增强；观察到达较晚时更短。增强还可能要容纳规则事实、编码、排队和结果处理，不是单独的神经网络运行额度。实际一律读取现有 `DecisionBudget`，不复制比例到另一个计时器。

- 在调用增强计算前已经有合法保底动作；1 秒吃碰窗口使用预计算和快速推理，不新增重型搜索。
- 一次预测同一窗口的多个候选；不为凑大批量无限等待其他官方场次。跨窗口合批必须计入最早截止时间与排队延迟。
- 启动时加载模型，覆盖常用输入形状预热；禁止动作窗口中首次编译、读权重或加载新框架。
- GPU 同步和阻塞式预测不直接阻塞官方事件循环。工作执行位置由组合根装配、应用层管理预算；取消等待不等于已提交的 GPU 内核停止执行，必须丢弃过期结果并限制在途增强任务与队列长度。
- 模型输出最终仍由 `hangma` 复核；异常、不兼容、非有限输出或超时使用保底。框架将不支持算子回退 CPU，与业务切换保底策略是两回事。
- 四个 Token 继续使用四个隔离身份进程，并按 `active_games` 管理 `config.M`。不为了节省一个小模型副本，立即增加跨身份公共 GPU 服务。

以上是后续接入要求。现有 `BotPolicy.choose(DecisionRequest, DecisionBudget)`、唯一规则来源及信息权限不改变。真正实施新调度或数据流时，必须同步 [架构](../../architecture.md)、[主技术方案](../../hangma-ai-bot-technical-plan.md)、受控契约和调用方；本次仅研究，不预建 `learning` 空模块或计算后端接口。

## 8. 小型验证实验与开发投入

**工程建议：先用 2–4 人日形成可复核的选型基准，再决定优化投入。** 以下估算按一名熟悉仓库的开发者、已有可用输入样本计算；不是交付承诺，不包含补齐杭麻规则、建立可靠反事实标签或训练出更强策略。

| 工作 | 估算 | 完成证据 |
| --- | --- | --- |
| 现有代码性能剖析 + CPU/MPS/MLX 代表模型比较 | 2–4 人日 | 两机相同输入与权重、端到端计时、峰值内存及限制 |
| 独立实验分片、持久多进程与两机汇总 | 2–5 人日 | 相同根组结果可追溯，完整桌赛吞吐提高且统计口径不变 |
| 一个已定位规则热点的紧凑化/编译 | 3–7 人日 | 官方金例/对拍、冷/热耗时、长时间缓存与内存证据 |
| 已训练小模型接入线上时限与保底 | 3–7 人日 | 双机及四身份并发下的尾延迟、故障降级与规则复核 |
| Core ML 导出一个支持良好的固定模型 | 额外 1–3 人日 | 转换成功、动作差异与部署延迟；遇不支持算子重新估算 |
| 全 GPU 规则模拟器或复杂搜索改写 | 数周以上，需先做热点原型 | 不能仅以一个内核快而声称完整桌赛快 |

基准至少覆盖下面的独立问题：

| 测量层 | 对照与采样 | 记录内容 |
| --- | --- | --- |
| 当前规则与启发式 | 同一组真实决策，冷/热进程分别测 | 规则、评分、复核分段耗时；缓存和峰值内存 |
| 完整本地模拟 | 1/2/4/6/8 工作进程；先 20 个独立根组验证流水线 | 每分钟完整桌赛数、CPU/内存、失败与未完赛数；20 组不作策略强度结论 |
| 模型训练 | 一个代表网络，同一初始权重/数据；批量 64/256/1024，内存允许才继续 | 每秒样本数、总训练步耗时、损失/梯度健康和峰值；不只测矩阵乘法 |
| 线上推理 | CPU 对 MPS，再按需 MLX/Core ML；单请求与同窗候选批量 | 编码至动作可用的 p50/p95/p99、观察到提交耗时、超时/保底次数 |
| 并发与故障 | 实际 `M`、四身份进程；注入模型失败与慢结果 | 排队、事件循环延迟、最晚提交余量、GPU 恢复后过期结果处置 |

尾延迟（`Tail Latency`）是慢端请求的耗时，例如 p99 表示约 99% 样本不超过的时间。采样应重复多批、数量足够且报告样本量与最大值；一次均值或少量请求的 p99 不能证明按时稳定性。基准同时保存机器配置、macOS/Python/框架版本、输入和权重哈希、批量、线程/进程数、电源与热状态。

计时使用本机单调时钟，持续时间用毫秒。PyTorch 在 GPU 完成边界调用 `torch.mps.synchronize()`；MLX 先确保输出已求值，再同步。分别记录冷启动/编译和预热后的运行，禁止只计“把工作放进 GPU 队列”的时间。[PyTorch 同步接口](https://docs.pytorch.org/docs/stable/generated/torch.mps.synchronize.html)、[MLX 同步接口](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.synchronize.html)

## 9. 本次调查边界

已完成源码定位、只读环境检查和一手资料核查；尚未安装框架、执行 GPU 基准、访问另一台机器或训练模型。因此不能承诺加速倍数、最佳批量、每秒模拟数量或哪一个后端一定最快。

研究建议的采用顺序为：现有路径计时 → 独立模拟并行 → 代表小模型 CPU/MPS 比较及一次 MLX 对照 → 选择一种实现 → 通过双机运行与完整桌赛评估门禁。硬件能力不是策略更强的证据，吞吐优化也不能替代同牌山换座位评估、置信区间和正式发布门禁。
