# T3：VIP 联合 EoH 生成接线准备

日期：2026-09-30。**结论：可复用现有调用、解析、受限执行、源码身份和费用账的底层入口；VIP 要使用独立 profile、完整多父谱系及新的编排封套。** 本文只读核对仓库源码，未调用模型、未读私有凭据、未运行桌赛，未修改旧生成器、搜索器或合同。下文的新增记录与接线均为工程建议，须等机械／策略代码及事实合同稳定、双轴审核完成后冻结。本批按根代理安排只交计划，暂不新增生成脚本。

依据：[新固定框架合同](./FIXED-FRAMEWORK-CONTRACT.md)、[EoH 方法核对](./EOH-FIXED-FRAMEWORK-ALIGNMENT.md)、[原评测合同](./EVALUATION-CONTRACT.md)。本文以本批工作区源码为一手证据；它不是生成、候选效果或发布验收。

## 1. 可复用路径与可行性

**保留唯一规则、执行与身份来源；旧 runner 不承担 VIP 的实际运行。** 当前生成器只列出 `i1/m1`；旧 action-value 生成路径硬绑定旧合同及单个 `parent`。搜索器的 `run_av_evolution` 也只从档案选 `m1` 或 `i1`，父代缺失时改成 `i1`。所以不能给旧函数传入新算子名字后，宣称 `e1/e2/m2` 已经接通。[生成器 `OPERATORS` 与 `_run_generate_action_value`](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)、[搜索器 `run_av_evolution`](../llm-guided-heuristic-route-2026-09-15/tools/sitin_search.py)

| 可复用源码 | 精确入口与范围 | VIP 适配点 |
| --- | --- | --- |
| [sitin_generate.py](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py) | `PromptPacket`、`sha256_text`、`normalized_code`、`parse_model_reply`、`ModelReply`、`load_reply_envelope`、`build_backend`、`SamplingSpec` | 新提示词 profile；前置验证唯一说明／JSON／Python 围栏和算子声明；多父不能压成旧单父记录。 |
| 同上 | `ApiBackend.complete`、`ReplayBackend.complete`、`HeadlessBackend.complete`、`DelegateBackend` | 真实调用由根代理之后接入；保持出处强度、真实采样和用量来源，禁止自动切换后端。 |
| [sitin_process.py](../llm-guided-heuristic-route-2026-09-15/tools/sitin_process.py) | `run_supervised`：进程组超时、整组终止、有界输出 | 新装载／候选静态与窗口探针使用这个监管入口；不直接执行生成源码。 |
| [action_value_executor.py](../../src/hangma_bot/policy/action_value_executor.py) | `static_check`、`ActionValueExecutor.score_vip_route` | 只接受新精确类型 `VipRouteScoringView`；不得调旧 `score(ScoringView)` 冒充新输入。 |
| [route_heuristic_view.py](../../src/hangma_bot/policy/route_heuristic_view.py) | `VipRouteScoringView.candidate_view`、`run_vip_route_scoring_skeleton` | 唯一候选输入是它的白名单值映射，保留所有合法根和条件分支，子节点在前；不送入 `visible_state` 原对象。 |
| [route_vip_heuristic.py](../../src/hangma_bot/policy/route_vip_heuristic.py) | `compute_vip_candidate_identity`、`RouteVipHeuristicPolicy` | 整套候选源码一次绑定，严格评分失败显式抛出；内含子函数也联合验收。 |
| [vip_heuristic_smoke.py](../../src/hangma_bot/offline/vip_heuristic_smoke.py) | `freeze_vip_identity` | 当前唯一离线身份封装：合同、真实依赖字节、数学后端、原生 C／已加载二进制、操作与投影额度。生成／准入／评测／恢复共用它。 |
| [scoring_sources.py](../../src/hangma_bot/offline/scoring_sources.py) | `source_manifest(显式 roots)`、`write_code_snapshot` | 主线的 VIP 身份封装已使用显式 roots；其默认旧候选 roots 不适用于新 profile。 |
| [sitin_search.py](../llm-guided-heuristic-route-2026-09-15/tools/sitin_search.py) | `ActionValueLedger`、`av_atomic_write_bytes`、预留／结算／恢复费用保留纪律 | token、桌赛等账户可以使用独立路径的账本；真实调用数、墙钟及 VIP 编排状态另有新封套，不能改旧账语义。 |
| [vip_evaluation.py](../../src/hangma_bot/offline/vip_evaluation.py) | `audit_vip_batch` | 复用完整同墙四换座、整根缺失失效的核验；本模块不注册候选，不发生成调用。 |

旧 `action_value_executor.compute_candidate_identity` 的 `candidate_kind` 写死为 `action_value_v1`，旧 `sitin_gates.av_identity_binding` 同样绑定旧合同和种类。VIP 已有自己的唯一计算入口和离线封装，不再另造身份算法；旧准入记录不能直接放行新候选。[旧身份实现](../../src/hangma_bot/policy/action_value_executor.py)、[旧准入绑定](../llm-guided-heuristic-route-2026-09-15/tools/sitin_gates.py)、[新离线封装](../../src/hangma_bot/offline/vip_heuristic_smoke.py)

## 2. 新 profile 与五种算子

**候选始终只产出一套 `score_actions(view)`，其动作、路线、节点聚合和胡／继续取舍联合评测。** 新 profile 的名字可拟为 `vip-route-eoh/1`；这是待冻结的编排名称，不是已经存在的 CLI。候选种类采用主线 `vip_route_heuristic_v1`，输入采用 `vip-route-scoring-view/1`，执行采用 `score_vip_route`。入口返回 `ScoreBatch` 对应的受限映射；每个合法动作键恰一条有限评分及有界解释，评分点越大越优，不跨候选比较绝对数值。[新固定合同 §4](./FIXED-FRAMEWORK-CONTRACT.md#4-评分与严格执行)、[新视图与输出骨架](../../src/hangma_bot/policy/route_heuristic_view.py)

| 算子 | 父代输入 | 必须出现在思想／声明里的内容 | 实际执行核验 |
| --- | --- | --- | --- |
| `i1` | 空列表 | 新机制、触发、预期方向和反例；不得伪造成绩 | 无父代；完整源码静态检查和新视图装载。 |
| `e1` | 至少两个不同候选 | 参考哪些父代，准备探索哪种不同形式，预计哪些动作选择改变 | 保留有序多父列表；外部行为面板逐父比较，不因自称“不同”发差异信用。 |
| `e2` | 至少两个不同候选 | 父代共同骨架、继承处、新增取舍及可能反例 | 共同骨架只作可核验设计说明；仍交一套完整源码，不能把父代分别胜出的子函数当已验组合。 |
| `m1` | 一个 | 哪条开发反馈导致哪处条件、聚合或逻辑改动；预期动作差异 | 父代身份准确；完整整套候选重测，不只测改动子函数。 |
| `m2` | 一个 | 原参数、新参数、单位、预期动作差异和过拟合风险 | 只允许冻结参数声明的位置变化；归一化语法树中其余结构相同。逻辑变化记算子不匹配，不静默改标签。 |

父代数量规则及算子形状来自已采纳的 EoH 对齐；`m3` 不进入本批五种入口。`m2` 的语法树参数核验是本仓工程建议，尚未实现；若候选没有可核验的参数位置，应拒绝本次 `m2` 材料并另行规划算子，不把调用后产物重新标成 `m1`。[EoH 算子依据](./EOH-FIXED-FRAMEWORK-ALIGNMENT.md#2-思想代码与算子的实际含义)

### 2.1 思想、代码与行为声明

**思想是源码设计说明，行为差异由外部冻结可见窗口验证。** 可保留现有输出形状：花括号内一句中文思想、唯一 JSON 机制说明、唯一 Python 完整代码；JSON 保留 `trigger/changed_branches/expected_direction/counterexample`，新增算子声明与逐父差异作为新 profile 字段。声明记录父代候选 ID、窗口类别、拟改变的动作键与次序；没有测得结果时标“预期”，不填数值成绩。[既有四字段与解析器](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

建议复用 `parse_model_reply(..., entry_name="score_actions", require_entry_definition=True)` 切思想和代码，并在外层严格校验新 JSON。旧解析器允许部分格式退路，`parse_action_value_reply` 仅检查四字段非空，不能据此证明唯一 JSON、精确键集合和新算子声明都合格。新 profile 不放宽静态子集或执行器限制。

既有 `behavior_change_report` 已把首选改变与单纯分值改变区分：保序平移、正比例缩放、只改非首选次序不发行为差异信用。VIP 可复用这条纪律，但冻结题集、合法键集合及同分处理必须采用新严格策略的真实选择口径。普通／七对或条件子节点的分值绝对量级不能跨候选当差异证据。[行为核验实现](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

## 3. 调用后端与凭据接线

**真实调用底层已经可调用；旧 action-value runner 本身仍只有文件式／回放生成流程。** 后续 VIP runner 可用 `build_backend(kind, prompt_sha256=..., config=..., model=..., tier=..., sampling=..., timeout_sec=...)` 构造后端，再调用 `.complete(prompt)`；此前必须完成授权、身份冻结和费用预留。本批没有构造真实后端、没有触碰凭据。[`build_backend`、`ApiBackend.complete` 与旧 runner](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

| 后端 | 已有精确入口 | VIP 新调用的建议记录 |
| --- | --- | --- |
| `api` | `ApiBackend.complete(prompt)`；使用兼容 HTTP 的 `messages` 请求 | 请求模型与实际响应模型、采样来源、端点主机、HTTP 状态、`finish_reason`、原始用量及 `usage_source=response_body`；外层单调计时。 |
| `headless` | `HeadlessBackend.complete(prompt)`；受监管 DSH 子进程 | 运行体能访问工作区，信息边界记 `weak`；实际模型配置与用量从会话日志取，不能把 CLI 请求模型当作实际模型。 |
| `delegate` | `DelegateBackend`、`emit_prompt`、`load_reply_envelope` | 导出提示词只生成交接件，不算新模型调用；摄入后保留委派来源自述强度和实际调用费用对应关系。 |
| `replay` | `ReplayBackend(reply_file, prompt_sha256=...).complete(prompt)` | 提示词哈希必须匹配；历史来源与历史用量引用保留，本次新模型调用为 0。人工格式夹具不算模型候选。 |

`ModelReply.to_json` 已区分 `tool-observed-http`、会话日志观测、封套自述和人工夹具。API 只取 `message.content`，推理正文不进入源码解析；`reasoning_content` 只记存在与长度。实际 `finish_reason` 显示截断时先记调用失败／截断，仍结算费用，不进入准入。缺终止原因的摄入材料须保留未知并按冻结来源规则处理，不猜成功。[`ModelReply`、`ApiBackend` 与来源分类](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

### 3.1 只说明配置键，不展示配置内容

**后续复用现有凭据解析；密钥只进传输层。** `resolve_api_credentials` 的当前顺序是显式 `config` 路径、`SITIN_LLM_CONFIG` 路径、`DEEPSEEK_API_KEY` 仅密钥环境变量、默认 `.private/sitin-llm.json` 路径。这里列出的是源码定义，不确认本机任何私有配置存在或可用。[解析函数](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

| 键／参数 | 用途及注意事项 |
| --- | --- |
| `default_endpoint`、`endpoints.<name>` | 多端点配置；端点取显式 `endpoint` 或默认名。 |
| `base_url`、`chat_path` | 服务地址与兼容接口路径；记录只留主机，避免路径或查询参数携带敏感内容。 |
| `api_key` | 仅内存中构造 `Authorization`；不打印 `resolve_api_credentials` 返回对象，不进入提示词或制品。 |
| `models.<tier>`、显式 `model`／`tier` | 显式模型优先，否则由档位映射决定；新批次须冻结实际值，不能照搬旧默认模型的质量或费用假设。 |
| `provider`／`kind` | 来源说明；不构成模型版本或用量的证据。 |
| `SITIN_LLM_API_KEY`／`api_key_env` | `ApiBackend` 构造阶段可读取的备用环境键；它不在 `resolve_api_credentials` 上述四级路径顺序里，不能据它单独存在断言 `build_backend` 一定成功。 |
| `dsh_bin`、`dsh_home` | headless 运行位置；该后端实际模型由 DSH 运行痕迹证明。 |

多端点文件的现有标记为 `sitin-llm-credentials/1`，也支持扁平配置形状；模型映射必须有相应档位或显式模型。新入口在进入凭据解析前检查本批授权和预算，禁止为预览、回放、缺预算路径读取私有配置。落盘前复用 `redact/find_leaked_secrets`，异常与审计删除 `Authorization` 和密钥原文。[凭据、泄漏检查与零预算前置检查](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

## 4. 候选身份与多父谱系

**源码身份和生成出处分别记录；同一源码由不同作者生成可以得到同一候选身份，但每次付费尝试都必须留下独立记录。** 调用 `freeze_vip_identity` 获得候选 ID、合同摘要、完整依赖／数学后端摘要和实际额度；生成模型、提示词、算子和父代属于出处，不塞进候选 ID。[新身份冻结](../../src/hangma_bot/offline/vip_heuristic_smoke.py)、[新 ID 计算](../../src/hangma_bot/policy/route_vip_heuristic.py)

拟议的新生成记录至少包含：

| 字段组 | 单位、来源与可空语义 |
| --- | --- |
| profile／schema／算子 | 新 profile 与请求／实际算子；二者不符即失败，不事后修名。 |
| 本批与尝试身份 | 运行 ID、尝试序号、独立调用 ID；每次真实重试有新序号，截断空回复不能覆盖前一尝试。 |
| 合同／提示词 | 合同原文快照、字节 SHA256、提示词原文与 SHA256、接口附录／子集说明摘要；事实合同未冻结时明确 `draft`，禁止真实准入。 |
| `parents` | **有序列表**，逐项保留候选 ID、源码／记录／思想摘要、合同与执行参数身份、产物路径、装载和准入状态；`i1` 才可为空列表。 |
| 思想／机制／源码 | 原始思想、结构化声明、原始回复、实际解析／执行源码及摘要；格式失败为空并附原因，不能补造思想。 |
| 作者与采样 | 后端、请求与观测模型、来源证据、实际采样和用量来源；缺证据使用未知，不填默认值冒充实际。 |
| 行为材料 | 冻结可见题集 ID、逐父首选比较、未知／失败掩码；生成前只是预期声明，实测与声明分栏。 |
| 时间与费用 | UTC 墙钟起止、单调耗时（秒）、真实调用、输入／输出 token、桌赛费用和失败／重试状态。 |
| 准入／发布 | 生成记录默认尚未准入、未发布；装载通过不等于全桌／确认／运行／人工发布门通过。 |

父代按落盘源码和记录重算身份，不信 CLI 自报 ID；拒绝缺文件、哈希不符、重复父代、旧 profile 或不同事实合同／执行额度的材料。列表顺序进入提示词与谱系摘要，因为顺序能影响生成。`e1/e2` 不允许压成一个 `parent_candidate_id`；`m1/m2` 不允许找不到父代后悄悄改 `i1`。失败产物作为修复材料时，单独记录 `repair_of_attempt_id` 和失败状态，不冒充已验父代，不兑换正常进化信用。上述多父与修复分栏是待实现建议；旧 `av_parent_binding` 的逐字节核验纪律可以复用，旧单父 schema 不能直接承载新列表。[旧父代核验与尝试目录](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

## 5. 调用、token、桌赛及墙钟预算

**预算先登记上限、先落盘预留、再发真实调用或桌赛；失败和重试保留成本。** `ActionValueLedger` 已有互斥重读、原子写入、重复预留拒绝和未知用量保守计费，但账户白名单目前仅有输入／输出 token、完整／部分桌赛、前缀生成和确认；不存在真实调用数或墙钟账户。应以独立 VIP 编排封套登记这两类约束，复用其原子及恢复纪律，不能把它们塞进旧账户换个含义。[账本账户与实现](../llm-guided-heuristic-route-2026-09-15/tools/sitin_search.py)

| 账项 | 预留与结算建议 |
| --- | --- |
| 真实生成调用数（次） | 发出 API／headless 或已授权外部委派前预留 1；校验／导出／回放不占新模型调用。网络不确定或截断仍计一次已发起调用，重试另记。 |
| 输入 token（个） | 先按冻结 tokenizer 或保守上限预留；实际 provider 输入字段结算。没有可靠 tokenizer／用量时保留未知，不以字节数冒充准确 token。 |
| 输出 token（个） | 按本次实际 `max_tokens` 预留；实际输出字段结算。推理 token、缓存读取是分项证据，不能未经确认再次加到已经包含它们的输入／输出总量。 |
| 完整桌赛（完整桌实例） | 先登记臂、牌山根、四换座、对手池、运行时 `Rounds` 与应有实例数量；完成按既有完整性核验，不按决策数计桌。 |
| 部分桌赛（尝试实例） | 失败桌成本留存、完整桌分母不删；重试新尝试关联同根及旧费用。部分单局数和实际耗时另记。 |
| 墙钟预算（秒） | 批次上限和每次调用／受监管执行超时另冻；外层以单调时钟累计真实耗时，UTC 只作审计时间，不用于持续时间相减。 |
| 确认预算 | 保持独立根与独立额度，开发调用／档案不能读取确认结果或借用确认预算；本准备批确认与真实调用均为 0。 |

### 5.1 用量未知不得结算零

**原始用量、规范化实际数和保守计费数分别留存。** HTTP 当前来源是 `prompt_tokens/completion_tokens/total_tokens`，headless 会话来源是 `inputTokens/outputTokens/totalTokens`；缓存和推理分项保留原文，不重复累计。具体 provider 对分项包含关系仍须在真调用前核对，本批未访问远程资料确认它。[`usage_tokens` 与 `ModelReply`](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

当前 `usage_tokens(None)` 返回 0，只是旧工具的缺失读取行为，不能在 VIP 当真实免费成本。新封套对缺用量或仅部分字段记 `usage_unknown=true`，对应实际字段为 `None`；仍按已预留额度保守计费，未知输入／输出各自保留，不以总 token 猜拆两项。`ActionValueLedger.settle(actual=None, usage_unknown=True)` 已保留原预留额。只有可信来源明确给出的实际零才能结算零。恢复时先对账原调用／预留及产物，费用已发生而产物缺失也不清零。[未知保守结算与恢复](../llm-guided-heuristic-route-2026-09-15/tools/sitin_search.py)

另外，旧 `_run_generate_action_value` 在 delegate 导出或 replay 之前就调用 `GenerationBudget.reserve`；因此它的 `spent_calls` 不能直接当 VIP 真实 LLM 调用总数。新生成封套必须区分导出次数、历史回放次数和实际发起次数，并保留历史回复对应的费用引用，不双计历史成本。[旧生成 runner 与预算](../llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py)

## 6. 最小实施与验收顺序

**先稳定事实合同及人工种子，再用无模型夹具检验接线，最后由根代理安排真实调用。** 下列均为后续任务，不是本批已执行结果。

1. 机械／策略主线落稳，双轴审核完成；冻结新事实视图、只读接口附录、子集约束、目标配置和实际工作量／投影上限。
2. 新增独立 VIP 生成／编排入口，复用上表纯入口；共同使用 `freeze_vip_identity`。冻结清单覆盖真实规则、投影、执行器、模拟器、统计器、对手池、生成脚本与工具依赖、根用途和家族席位配置。旧运行状态不复用到新 profile。
3. 用人工格式夹具验证五种算子、单父／多父核验、提示词／回复摘要、截断拒绝、字段未知、算子不匹配、重复预留、费用恢复与源码依赖漂移；夹具产物明确非模型候选，测试不发模型调用、不跑桌赛。
4. 用新精确视图的冻结窗口进行受监管装载／完整返回／行为比较；先确保 `score_actions` 一次包含全合法根，故障注入不会被生产紧急包装吞掉。
5. 根代理登记第一批调用与输入／输出 token／桌赛／墙钟上限、查看次数和停止准则，再发真实调用。生成模型身份从实际来源取证，准入失败也记录费用。
6. 整候选经严格持续完赛、机会／自然双账及根级独立确认；行为去重和家族席位保留是开发档案决策，不自动整体晋升。旧父代、人工种子和对照成绩分别保留原身份。

`audit_vip_batch` 能承担完整根核验，但 T3 仍需把新的候选／评测身份带入逐窗与结果记录。模型能否稳定产出不同形式、`m2` 是否常产生真实选择差异、API 成功率／token 成本和端到端运行预算，都是待真实调用或评测回答的未知。不得把本接线计划当作这些问题已解决。
