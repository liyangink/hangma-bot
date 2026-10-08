# perclass 包的语料选择（先冻结规则、后运行）

> 由 [select_corpus.py](./select_corpus.py) 生成；工具侧读取口径见
> [tools/sitin_gates.py](../../tools/sitin_gates.py) 的 CORPUS_MANIFEST_SCHEMA。

## 0. 面板身份与 canonical 的关系（Lead 裁定 F7，2026-09-16）

| 项 | 值 |
| --- | --- |
| 本清单 panel_id | **subset-perclass-frozen**（角色：诊断子集） |
| 本清单指纹（文件 sha256） | 见 [corpus-manifest.json](./corpus-manifest.json) 的清单哈希 |
| 本清单行数 | 16851 |
| 本清单 record_layer | **raw**（记录原样；不作为效果口径） |
| 唯一 canonical 面板 | **panel-canonical-20260910**（105 份 / 359,262 行，record_layer_filled=true） |
| canonical 清单 | [corpus-manifest-canonical.json](./corpus-manifest-canonical.json) |

**边界**：本子集只用于**逐类账与工具自检**；不得作为 scorer / condition / overall 的分母或效果口径，
也不得与 canonical 面板的数字相加或混用。任何引用必须写明「面板 id + 是否归一化」。

### 0.1 记录层前后的四个量（命名与 corpus 3.6d 对齐；canonical 面板口径）

| 量 | 值 | 判据 |
| --- | --- | --- |
| `newly_attributable` | 21 | 行侧：`raw chain_piao is None ∧ filled is not None` |
| `newly_scored` | **14** | 分母侧：修前被规则层降级排除 ∧ 修后进入计分（**由引擎判据得出的唯一分母口径**） |
| `still_unknown` | 5 | 修后仍不可归因且 `chain_count>0`（逐行列明，不并入分母） |
| `net_usable_window_delta` | +16 | 链族可用窗口差（= 已知数净差；**不得**当作新可判窗口数或新计分窗口数） |

派生：`attributable_but_still_excluded = 21 − 14 = 7`（已可归因但仍被其他规则排除）。
历史注记：corpus 侧初版把该净差命名为 `newly_decidable_windows=16`（已于提交 cb3a3c38 删除，其值实为净差而非新可判窗口数）；引用一律用 `net_usable_window_delta`。
机读与逐行样本见 [raw/51-newly-decidable.json](./raw/51-newly-decidable.json) 的 `reconciliation` 块；
**本包一律以 14（分母口径）为准**，引用 16 时必须写明它是净差。

### 0.2 排除账（整文件行数，扫到底）

| 项 | 值 |
| --- | --- |
| canonical 纳入 | 105 份 / 359,262 行 |
| canonical 排除 | 7 份 / **6,775 行（1.85%）**（四份旧形态 199/982/2,361/3,233 行 + 三份空文件） |
| 家族合计 | 112 份 / 366,037 行（= 纳入 + 排除） |
| 来源 | 本包**本地重算**，与 3.6d 的 `corpus_family.excluded_rows=6,775` 对拍一致 |

## 1. 规则（写死在脚本里，运行前冻结）

1. 根：artifacts/sessions/*/postgame/*/derived/*/decisions.jsonl；
2. 会话目录名以 auto-match- 开头（排除 test-room-* / adapter-*）；
3. postgame 时间戳以 20260910T 开头（09-10 批 = 最新一天）；
4. 按路径字符串**升序**（会话 id 是哈希 ⇒ 等价于按会话随机取）；
5. 整份文件取到累计行数 <= row_cap=20000 为止（**不拆文件**）；
6. 清单与被排除清单一起落盘。

## 2. 全家族分布（复核「新基线不是手挑的」）

| 项 | 值 |
| --- | --- |
| 家族文件数 | 112 |
| 家族总行数 | 366037 |
| 按天（文件数） | 20260907: 4, 20260908: 53, 20260909: 5, 20260910: 50 |
| 按会话前缀（文件数） | adapter: 2, auto: 99, test: 11 |

## 3. 选中子集

| # | 文件 | 行数 | 累计 | 字节 | sha256（前 12） |
| --- | --- | --- | --- | --- | --- |
| 1 | artifacts/sessions/auto-match-a_0534484863f3/postgame/20260910T015846Z-6ad9576e/derived/70aabae4928742e8aee46e3a2872b102/decisions.jsonl | 3464 | 3464 | 87920508 | 5edef1f0a581… |
| 2 | artifacts/sessions/auto-match-a_097edb17d2c7/postgame/20260910T015904Z-8fd80546/derived/65fa040dae934b3d8050d8a4bf2de398/decisions.jsonl | 3477 | 6941 | 92745056 | b3727f8c0eae… |
| 3 | artifacts/sessions/auto-match-a_0fdaf1be70c0/postgame/20260910T015923Z-1a2036b6/derived/2888b2c6ae144045aeed05c19c68e4c2/decisions.jsonl | 3565 | 10506 | 97329065 | ec9ec32f2108… |
| 4 | artifacts/sessions/auto-match-a_10fa4a6f7bc7/postgame/20260910T015943Z-dfd796e4/derived/a6ee9d9529284baab49aa36fbc91bf67/decisions.jsonl | 3346 | 13852 | 81355855 | 5b8b039afd17… |
| 5 | artifacts/sessions/auto-match-a_1a3803f0269d/postgame/20260910T020000Z-0a60f3f4/derived/b306972396f940189f0fcdb79e37cbe1/decisions.jsonl | 2999 | 16851 | 70801387 | 1df98076a0bc… |

**选中 5 份 / 16851 行**（上限 20000）。

## 4. 被排除的文件

| 文件 | 行数 | 理由 |
| --- | --- | --- |
| artifacts/sessions/adapter-acceptance-20260909-d37d2250de96/postgame/20260909T090140Z-349b0c8b/derived/17e2bc9a0324412fafdbda822ab8797b/decisions.jsonl | 2756 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/adapter-confirm-20260909-d37d2250de96/postgame/20260909T090929Z-41823a54/derived/de603850c1cd41e68c9d77f274ec26a2/decisions.jsonl | 2844 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/auto-match-a_014aab011c14/postgame/20260908T143632Z-08e9883f/derived/7b74eba3c5c74237b6da0c03f224e4fa/decisions.jsonl | 2935 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_06fcf39d8ef7/postgame/20260908T143643Z-74875423/derived/0f2c21331a9a4d74b6699a39c96f1146/decisions.jsonl | 3372 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_0c8a9bd9e09e/postgame/20260908T143655Z-fcf1e301/derived/91321933adf44dd8bd37c29d210c607a/decisions.jsonl | 3178 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_1515a95f670b/postgame/20260908T143730Z-fab88333/derived/81ff2ef9417143c2bdd53a3107afdbfc/decisions.jsonl | 3591 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_1da79ad74063/postgame/20260910T020015Z-69b438da/derived/d973fde765ad4c55b602a296a45553da/decisions.jsonl | 3431 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_22fa52669b39/postgame/20260908T143744Z-78c20e32/derived/f15a87449c8a4f03a5c99de19ce74a2f/decisions.jsonl | 3750 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_23dcf81b6808/postgame/20260910T020033Z-c56a93c9/derived/22b4bfbbba2a4abfadb02ccb9191f532/decisions.jsonl | 3832 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_2495e0fda3b7/postgame/20260908T143830Z-e31c3568/derived/0f17a82fee8043ba80c2eb3e7f681c15/decisions.jsonl | 3672 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_2610609fa425/postgame/20260910T020112Z-1286754f/derived/42511a85b4bb4869a30aa048cb59d7bd/decisions.jsonl | 3060 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_28f1e529ff07/postgame/20260910T020128Z-5b890b89/derived/0776e4dfa3c34069b2c40ea7ccc6a24b/decisions.jsonl | 2841 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_2a2325f65163/postgame/20260908T143844Z-5172529c/derived/d83655f333ef45ac9a5bda9b8c362407/decisions.jsonl | 3498 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_2b57c14757df/postgame/20260908T143858Z-6a2464e4/derived/d814ef01463e4ad3ae6e24d64b2c88d0/decisions.jsonl | 2940 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_2e00f34ba4f4/postgame/20260910T020143Z-a1e37bbb/derived/5a812915e1e44d67807cd26f24985cc3/decisions.jsonl | 3468 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_2e25b63381cf/postgame/20260908T143910Z-1ae541f5/derived/9f18b1f4e81c42d288a29f3ecc524553/decisions.jsonl | 3703 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_2e49c34ad2ba/postgame/20260908T143924Z-1398c47f/derived/6cc72896da0c40e08a070996a2de2e67/decisions.jsonl | 3311 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_301f448fd10a/postgame/20260908T143937Z-39fec2fc/derived/6687507548034feda0217422ef35683d/decisions.jsonl | 3325 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_3152990a75b5/postgame/20260908T143950Z-c7c1b23f/derived/0b66417481c442d78e1862ab7b943c09/decisions.jsonl | 3566 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_331e368b65bf/postgame/20260910T020202Z-61fdd427/derived/c949907f4ede414d9709e359e14f5f8a/decisions.jsonl | 3553 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_38edd200c577/postgame/20260910T020222Z-babb54c7/derived/f3f6c836b6144ef5bce96b28b980fff7/decisions.jsonl | 3118 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_3a632d7f4138/postgame/20260910T020238Z-07fa5799/derived/769d0ec83cfd4ba39c57e2d6b29c0ca8/decisions.jsonl | 3355 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_3ae605bc0a75/postgame/20260910T020255Z-92e8afcf/derived/e2749e088c60441c90794ed635e75a11/decisions.jsonl | 3745 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_3e55dbbc2fac/postgame/20260910T020316Z-37ccd374/derived/2cc110f31dc94bf5ba33b0de1be0481a/decisions.jsonl | 3084 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_3eb17fcc2773/postgame/20260908T144040Z-0e812bea/derived/e5076dcc0bc14f7ca5cc4dd476af08c9/decisions.jsonl | 3226 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_3f4a252ff898/postgame/20260910T020332Z-00fb157c/derived/31167a9782e84c0ba55f055e47bda9a2/decisions.jsonl | 3331 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_44a77f44f41b/postgame/20260910T020350Z-fc709023/derived/4c7aa35937f447b09a369ac038db7307/decisions.jsonl | 3243 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_47f6f1c86c8c/postgame/20260910T020407Z-b777aa82/derived/7e224cfc35e34f50a8f2c6a38ab2915b/decisions.jsonl | 3570 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_494bc23524c9/postgame/20260908T144052Z-a656122c/derived/e66ad9823a684f5296e9806d58d2a2b4/decisions.jsonl | 3202 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_503c819b12f8/postgame/20260910T020425Z-7705de27/derived/b044bbcdcb5d45f0a2c419a576af2b8f/decisions.jsonl | 2977 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_506c1697c531/postgame/20260908T144104Z-31ded83f/derived/1b07b95a02514a11a224a1fcb66512ad/decisions.jsonl | 3339 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_5437e0f38143/postgame/20260910T020441Z-85d7ac97/derived/095d1b567a2d461cae6c0a55bdb45090/decisions.jsonl | 3208 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_54ecb8a94693/postgame/20260908T144144Z-6b4c160a/derived/c0626c9d51ab4ec1b9458d2c27f8968f/decisions.jsonl | 2907 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_56aad1309f00/postgame/20260910T020458Z-7cb78ac2/derived/1636a5ba396c40938f4d542ed34f5651/decisions.jsonl | 3307 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_5710ed69b1f2/postgame/20260908T144155Z-19bbc017/derived/138a8942f1ef46f1a59e45774089bd02/decisions.jsonl | 3403 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_5bcbe61fc99b/postgame/20260908T144207Z-4c5d8fe3/derived/d42e8e83ad94449bbb7ae96ed3386a60/decisions.jsonl | 3248 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_5f0f5a01d79c/postgame/20260908T144219Z-9269b115/derived/b3888d07fdc4459bbac0382c03c2f068/decisions.jsonl | 3320 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_61b4af68d574/postgame/20260910T020516Z-ea8f3f1d/derived/1b635074647b4bd8bb5286179cb40d55/decisions.jsonl | 3327 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_632c4abe5dd0/postgame/20260910T020532Z-0209f3b5/derived/ed5239ee667e403ebb6917e1ac8c5635/decisions.jsonl | 4194 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_65c74e043ed5/postgame/20260908T144256Z-18e05486/derived/59c80a30322d40878e9cd48d8253d37a/decisions.jsonl | 3425 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_699dd2c3a335/postgame/20260910T020559Z-0d1bd5a8/derived/6b30070fad0b4e469f3609214debdd42/decisions.jsonl | 3470 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_6bd823fc65bd/postgame/20260910T020618Z-9338e330/derived/8a82888a457b4612bae7594271a4dafc/decisions.jsonl | 2932 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_6c280fd4e25b/postgame/20260910T020633Z-410b1fb4/derived/b880fbbddaeb4e188e9c4cdd6db69fd8/decisions.jsonl | 3394 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_6cf0cd6067ff/postgame/20260908T144309Z-5810bd64/derived/ef1c88de2a8c49519b9bbff51dc37bb0/decisions.jsonl | 3098 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_6dd08b996920/postgame/20260910T020650Z-4473cf34/derived/5f8a18f4d584440289ebd95791f3d239/decisions.jsonl | 3261 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_74567b6d4a3b/postgame/20260910T020708Z-bc1bd9c1/derived/8bcecf1ce4074c8c9e347e1f91e4e323/decisions.jsonl | 2934 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_84ff25b863a1/postgame/20260910T020723Z-0a0a47b1/derived/d6f02f4113e1464a8e40ac1781a595b8/decisions.jsonl | 3221 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_85a614df4ed6/postgame/20260908T144320Z-ee8b873a/derived/fcceec8d80974042bbbf0b3f201c7f92/decisions.jsonl | 3602 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_8620774a16e8/postgame/20260910T020739Z-a82df5ec/derived/18de578f15994a2eb36dd7b78b21d88b/decisions.jsonl | 3114 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_890241a9a990/postgame/20260908T144358Z-e27fc080/derived/af2142308148490dae0ce392f0f8afd2/decisions.jsonl | 3204 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_9321db900414/postgame/20260908T144410Z-ff50c86f/derived/1345e5ffc5294f5aaa8cac5556e960ce/decisions.jsonl | 3260 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_96a3410c5ee7/postgame/20260908T144421Z-125fe046/derived/6fbe6c9cda3f4b948dfeef4bce6723ea/decisions.jsonl | 3733 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_9b513817de19/postgame/20260910T020755Z-346a1cfb/derived/1e6832cd76fb468d88beb48697afa290/decisions.jsonl | 3541 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_9ceaf4308aa8/postgame/20260908T144435Z-32f2eff7/derived/ffb6cc5f931c40948770a25ffd98468c/decisions.jsonl | 3223 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_9d3d76a962c0/postgame/20260908T144507Z-700127de/derived/5bd057b5d5f14b469e18a0edf1047b0a/decisions.jsonl | 3953 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_9f7043655503/postgame/20260910T020813Z-a5c88ec0/derived/b54fd61425784d0cb40a4a9e4b7d5f60/decisions.jsonl | 2981 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_9f9fe44ce27c/postgame/20260908T144544Z-c2f0479d/derived/a5d5171a97264e689c8d20b4549b4377/decisions.jsonl | 3085 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_a0687ee6b813/postgame/20260910T020829Z-f76b5939/derived/f5bcb3b6593445fd9f9027c91afd06be/decisions.jsonl | 3685 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_a24582ede246/postgame/20260910T020848Z-61628e49/derived/f543d77638624654a28ecefeedd5a013/decisions.jsonl | 3169 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_a7d63b5d886d/postgame/20260910T020905Z-f6f3b7ef/derived/8ba8415a8a844033a38ab9b7b831029d/decisions.jsonl | 2818 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_aaecd8dd4e30/postgame/20260910T020919Z-632e4ede/derived/35882071089d42aba231909e4d0b0252/decisions.jsonl | 3630 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_acf100981ba2/postgame/20260908T144554Z-2ec8006a/derived/6c8fbcdcbeb14d809cf1122a34c592fa/decisions.jsonl | 3343 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_af399463d8d4/postgame/20260908T144632Z-831d6bb1/derived/8bc6bb5c821247dea4d47ea5ca0cf3fb/decisions.jsonl | 1799 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_b112c883ebfe/postgame/20260908T144639Z-ca5d789f/derived/301963c25f384dbda4aed7b7c316fb83/decisions.jsonl | 3847 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_b287ac645f5a/postgame/20260910T020937Z-212e795e/derived/e8f52bdc023b42609e640eb317d50ff9/decisions.jsonl | 3638 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_b41d435b6d2f/postgame/20260908T144720Z-2d5493e5/derived/a1f32b078e68483ab1f8d1e07cb2d9ec/decisions.jsonl | 3329 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_b490feba6167/postgame/20260910T020957Z-ac1ef648/derived/b0c7f00de6de41c9921afeca8282b570/decisions.jsonl | 3039 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_b74eb4bd9136/postgame/20260908T144732Z-0f681544/derived/c25d707d86684e36b11b067c4b8baa57/decisions.jsonl | 199 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_b837ab2d6a21/postgame/20260910T021011Z-846af742/derived/6f6519bcbf5d4f66ba81670838cd6c99/decisions.jsonl | 3197 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_bc9a6cef4d89/postgame/20260908T144732Z-0169f8de/derived/60e7314adbc44b01801d98ec793edeb2/decisions.jsonl | 3966 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_bce3dcf1909a/postgame/20260908T144817Z-6dcfa28d/derived/a236696d119a41dca35f053890f9a9af/decisions.jsonl | 3317 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_c3c146453604/postgame/20260910T021028Z-e7b88ab7/derived/c7655f037d634ff5b1984c40808116d2/decisions.jsonl | 3436 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_c63ebb920733/postgame/20260910T021046Z-ffba2f5c/derived/4944a17919d343219c5c649f312c6507/decisions.jsonl | 3943 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_c6c7d691c61c/postgame/20260908T144829Z-536e923c/derived/5983e6194bcd44179ed6440e58879999/decisions.jsonl | 3115 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_c8ae8cdf2afb/postgame/20260908T144908Z-5e69e0c7/derived/f97f0a94b84e4e1ba13183684f6b91fc/decisions.jsonl | 2835 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_ca4a6b3329d1/postgame/20260908T144919Z-b2b7d997/derived/682e3916e7a0460b89d7a702a50cec9d/decisions.jsonl | 3705 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_cd5c88f494b2/postgame/20260908T144932Z-36e2c387/derived/da1088fd22444e4fa840b200f17c1935/decisions.jsonl | 982 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_d0c721d96d48/postgame/20260908T144935Z-a868af09/derived/8961746b058c4a03bc098360e905ab62/decisions.jsonl | 3282 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_d1c8720d65f4/postgame/20260910T021109Z-bd5763df/derived/3bb0ece976da41918bb182f89f939ef0/decisions.jsonl | 3731 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_d2baa85f1612/postgame/20260908T145012Z-6fc0c7da/derived/6d44a713315c4fce89fc7be6aa9788ea/decisions.jsonl | 3094 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_d303274a8edd/postgame/20260910T021129Z-45f7e8d2/derived/a5769093494142b1a4f39c8973cb1b84/decisions.jsonl | 2975 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_d3b34793b175/postgame/20260908T145051Z-3f98b426/derived/975dbd61b5854f46b0eacb4485fdcdae/decisions.jsonl | 3474 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_d3b5d48668d7/postgame/20260910T021146Z-37036178/derived/5744f73bbe5d4d26b58ffff44a0aa658/decisions.jsonl | 2889 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_daf62d6bdd4d/postgame/20260910T021200Z-d146f7c5/derived/49dd3261aa9247b08e84425fa947b346/decisions.jsonl | 3021 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_de1d194af10a/postgame/20260908T145105Z-448e98f9/derived/a966f01ff53749be843475f3d4fc67e3/decisions.jsonl | 3446 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_df5de5962a32/postgame/20260908T145119Z-433ab24b/derived/d1bd134970534dd38e536d9eb9a22e8a/decisions.jsonl | 3089 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_e0581415c7fe/postgame/20260910T021216Z-2c57a3aa/derived/0a209373577048d9b9383d8b8bed31c1/decisions.jsonl | 3579 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_ec93a12a1913/postgame/20260908T145130Z-98d7ad13/derived/0d1aeb4efce54b26b1c6b891520e2c54/decisions.jsonl | 1633 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_efdcec8879f3/postgame/20260908T145135Z-7fcae46a/derived/6d6c33de56454686ace603c965bf1d8e/decisions.jsonl | 3193 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_f24da7e66619/postgame/20260910T021236Z-04cb0c3a/derived/6d367d5a24f845279827ca54e4f4dac0/decisions.jsonl | 3201 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_f5885115dbf0/postgame/20260908T145148Z-400fe75b/derived/026c72d24ad742efb035897d36796c6c/decisions.jsonl | 3094 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_fa4bce14d968/postgame/20260910T021253Z-9a84a2f1/derived/4f8a184ea87c401b8a7d3af8433d7afa/decisions.jsonl | 2097 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-a_fb47fc10cd1a/postgame/20260908T145200Z-0a2652ab/derived/57aeba370e77449dbe2f1e53f4900c61/decisions.jsonl | 2361 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-a_fe6232f47fdf/postgame/20260910T021307Z-933bccc9/derived/17bc1338ef3047c9939de280b8bc2bf7/decisions.jsonl | 3289 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/auto-match-matching-aborted-20260908/postgame/20260908T145206Z-5b89b223/derived/d1666a2eab194124ba04d610b961487c/decisions.jsonl | 0 | 不在 09-10 批（本包只取最新一天，规则先于运行冻结） |
| artifacts/sessions/auto-match-matching-aborted-20260910/postgame/20260910T021325Z-b199d776/derived/f657b272ace94e37b27bd74094a3f8d1/decisions.jsonl | 0 | 排序在截断点之后（累计行数已达/将超上限 20000） |
| artifacts/sessions/test-room-20260907-2f3fd296193f/postgame/20260908T145424Z-73dc81c3/derived/9b9e63ad97374359983ebd4365dd2723/decisions.jsonl | 2998 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260907-5fb2a7c5096e/postgame/20260908T145436Z-25786e87/derived/c321a4c17c3c40e5a91928e5bfcb55b5/decisions.jsonl | 3857 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260907-b684d5c3eea4/postgame/20260907T084839Z-61255059/derived/3bbbccc485974983b1be91e86c0aa535/decisions.jsonl | 7510 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260907-b684d5c3eea4/postgame/20260907T085616Z-1de58bc5/derived/ffa38ac0b3374e12b34ba8e8154f9081/decisions.jsonl | 7510 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260907-e91b044cc716/postgame/20260907T034425Z-7e59b3e3/derived/49d9c873cef047debe86a7b67a352268/decisions.jsonl | 7014 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260907-ef9bd5a31110/postgame/20260907T113712Z-efbb8d26/derived/1ab10c3aee164dadb7e5f8e5779def16/decisions.jsonl | 5716 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260909-32d3356ee4ce/postgame/20260909T062402Z-8837ecb6/derived/8c86bb0c3c6c479d996de3e95d0760f2/decisions.jsonl | 3191 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260909-32d3356ee4ce/postgame/20260909T062727Z-1081878f/derived/1a004645304d4190be9bc9af142868ab/decisions.jsonl | 3191 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-20260909-d37d2250de96/postgame/20260909T082916Z-b2d43a26/derived/dd92753bb8bd41ea890ecceaf74f13e2/decisions.jsonl | 3365 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-legacy-20260906/postgame/20260908T133048Z-e415db7f/derived/f7ff741014884868a29804053732ab43/decisions.jsonl | 3233 | 非 auto-match 会话（测试房间 / 协议验收） |
| artifacts/sessions/test-room-t-dee58824c308-20260904/postgame/20260908T145207Z-c8c115b5/derived/44ed0c1ffacd4c1d89ea95f6aad82a53/decisions.jsonl | 0 | 非 auto-match 会话（测试房间 / 协议验收） |

## 5. 边界（必须与结论一起引用）

1. 本清单**与候选表现无关**：规则先冻结、后运行；换一天或换上限都必须重新落盘。
2. 选中子集是**批内按路径顺序的整份文件**，不是全家族的无偏抽样；
   结论只对该子集成立，不得外推整体发生率。
3. 旧语料 datasets/derived/auto-match-2026-09-06/decisions.jsonl **降级为历史对照样本**，
   只用于 before/after 与回归，不再作为基线。
