# T2：局部胡资格窄入口的等价优化

日期：2026-09-30。**两条已发现的慢公开请求在同图、同评分、同解释条件下加速。**最终非法座位守卫后的本地复测，碰响应建图1681.34→147.19毫秒，摸牌建图1309.22→108.97毫秒。新入口只省去即时胡查询不消费的完整动作分析和公开历史重扫，没有删根、弃牌续行或相容码。这是局部计算证据，不是完整桌赛、官方时限或发布门证据。

## 1. 范围、依据与旧路径红信号

**复用唯一规则源；完整旧入口保留作参照。**依据[固定合同](./FIXED-FRAMEWORK-CONTRACT.md)、[性能诊断](./T2-PERFORMANCE-DIAGNOSIS.md)及其中的[隔离复算程序](./evidence/t2-performance-profile/profile_visible_observations.py)。公开输入来自[inputs.json](./evidence/t2-performance-profile/inputs.json)：203桌第1局seq67座位2碰响应，以及第2局seq331座位3摸牌。不读取完整模拟状态、未来牌墙、私有凭据或模型。

实现前再次在独立 `Python -I` 进程核验旧冻结源码和原生二进制，以临时输出目录运行原诊断程序的第0条输入。旧碰响应冷建图1728.04毫秒、热1721.87毫秒；规则＋建图＋评分分别1760.54／1745.86毫秒，`response_compute_over_1000ms=true`。3个根、722节点、719边、15192次见证和25363计数操作保持原诊断一致，排序为 `pass, peng:5t, gang:exposed:5t`。临时输出在读取后清理，原证据文件未改。

## 2. 新入口与语义边界

**仅胡见证（`WaitingHuWitness`，指定一次本人普通摸牌条件下的胡真假及结算）不冒充完整动作分析。**新模块为[route_hu_witness.py](../../src/hangma_bot/hangma/route_hu_witness.py)，公开入口：

```python
def analyze_waiting_hu_witness(
    state: ConditionalRouteState, tile: Tile, *,
    wall_remaining_before_draw: int, catch_restricted: bool, config: RuleConfig,
) -> WaitingHuWitness:
    """接受合法弃后13-3m等待态，返回局部普通摸牌的胡事实；不展开其他动作。

    墙余单位张，抓打限制是显式条件；前置、精确正容量或规则身份不符抛ValueError。
    无文件、网络、时钟和外部状态副作用；不证明能走到此摸牌或最终获胡。
    """
```

返回值冻结。`tile/catch_restricted` 记录本次给定条件；墙余字段按此一次实体摸牌减一，单位张。`legal_hu` 与 `immediate_settlement` 分列，结算四座顺序0—3；问题保留为不可变元组。`baotou_after_draw` 由同源生命周期更新。`draw_capacity_before/after` 仅说明所摸码已验证精确公开未见容量的实体增量，不是完整公开库存刷新结果或墙内概率。`local_witness_only` 恒真，`scope` 恒为 `local_given_normal_draw_hu_only`，构造者不能传入另一值；语义常量为 `vip-local-hu-witness/1`。

计算依次复用 `progression.baotou_after_draw(...replacement=False)`、`hand_analysis.analyse_hand_win`、原 `action_families.hu_candidates`；仅在确认合法胡后调用原 `win_split` 与 `settle_win`。根代理按最小受控需求新增了 `HandWinEvidence(is_win,evidence)` 和只判胡数学入口，扩展胡族接受窄事实；没有伪造完整 `HandSummary` 的向听或有效牌字段。数学成胡但分解丢失时仍保留合法胡、空结算与机械问题；链内飘白未知时保持输入问题；胡族异常保留同原组合器的显式问题。

合法观察域的前置与完整见证相同：只接受非结构预列的合法弃后等待阶段，13−3m与公开手牌数一致，座位／庄家／规则身份／公开视图齐全，无未消费的摸牌或他座行动；墙余为整数且超过20，限制为布尔值；绑定相同规则版本、BaseScore=1、YouCaiBiKao=false；所摸码容量必须精确、已知且正。墙21允许摸后20张并胡；不能以摸后墙20关闭胡。

### 2.1 非法座位守卫修正与源码冻结

**独立规格复核发现并关闭了首版窄入口的负索引遗漏。**以有效等待态替换 `seat=-1`、摸非胡牌，旧完整入口在公开库存绑定时拒绝，首版窄入口却可能使用Python负索引并返回非胡。这是实际前置缺陷，根代理批准后在读取公开手牌数前增加本人及庄家的严格整数／0—3范围检查。

实测还发现旧完整入口在非胡分支曾接受 `seat=True` 或 `dealer_seat=True`，不能称其原来已拒绝布尔座位。根代理同步加强旧完整等待入口，两入口现统一拒绝布尔、浮点和越界座位。合法 `PlayerObservation` 域的图与评分等价不变；回归同时覆盖成胡与非胡分支。独立规格复核重跑负索引反例，两入口均拒绝，未发现其他可行动规则问题。

最终 `route_hu_witness.py` 的SHA256为 `56fa528132568eb7b56c94990508994228df19cfe75f5ce42fe3a501ade369e9`。此后只更新报告与测试证据，不再修改运行源码。

## 3. 等价验证

**全部比较调用公开接口，完整旧见证独立生成参照。**[新增测试](../../tests/unit/hangma/test_route_hu_witness.py)覆盖普通型、七对、自然豪华四张、四真白的两种用途、普通／七对重叠、多白等待前驱；白库存0—4、副露0—4、两种抓打限制、四座赢家×庄家组合、末墙、非胡、未知链、旧爆头退出／新爆头形成、精确零／保守／未知拒绝，以及各类必需前置。故障注入锁定分解丢失、胡族异常及同源数学异常；另一用例禁止调用完整手牌分析、全动作组合器和库存重扫。

对两条真实慢请求，逐合法根用公开条件转移展开全部合法弃牌、续杠和精确相容补牌，再按完整相关事实去重：碰响应332个等待事实、21912个摸牌×限制比较；摸牌331个等待事实、21808个比较。逐项比较胡真假、立即四座结算、问题、爆头、局部范围及所摸码容量。覆盖全部精确相容码，不只查询当前综合有效码。

整图对照只在测试中把旧完整见证投影为胡真假／结算／问题，供当前公开建图入口消费；生产入口没有返回假的完整状态。两条请求的新旧图对象及候选映射严格相等，所有评分和完整trace相等，操作计数相等。

复算：

```bash
.venv/bin/python -m pytest tests/unit/hangma/test_route_hu_witness.py tests/unit/policy/test_route_vip_heuristic.py -q
```

最终守卫后结果 **103 passed in 21.36s**，其中新入口74项、策略29项。此计数不包含根代理另跑的契约／烟测检查。独立规格代理另跑58项窄入口测试通过；其侧未重跑两个慢请求的全码对照及两个整图用例，本报告的这四项结果来自作者运行，不能混称独立验证。

## 4. 同输入性能测量

**两个入口消费相同去重事实，没有以剪枝换取加速。**仅见证循环在等待态构造后测量，全精确相容码×两种限制，交换入口顺序各测一次；碰响应完整／窄入口为2369.23／105.05与2382.72／104.32毫秒，摸牌为2385.44／109.86与2357.29／107.42毫秒。这里的调用数多于实际建图，因为独立对照枚举了全部相容码。

第一次优化、非法座位守卫统一前的整图测量按新首次、旧完整首次、新重复、旧完整重复顺序，先分别重建同一请求的规则分析，再计建图和受限评分。每次建图使用新请求内缓存。首次是本进程此请求第一次建图，不等同原冻结隔离进程的冷测；本地测量未隔离机器上的其他研发任务。以下历史数据保留原版本归属，不移作最终源码的成绩。

| 公开请求／入口 | 首次建图ms | 重复建图ms | 首次规则＋图＋评分ms | 重复规则＋图＋评分ms |
| --- | ---: | ---: | ---: | ---: |
| 碰响应／旧完整参照 | 1835.95 | 1834.58 | 1861.54 | 1859.71 |
| 碰响应／仅胡 | 166.63 | 159.03 | 194.41 | 184.81 |
| 摸牌／旧完整参照 | 1402.78 | 1399.15 | 1537.31 | 1531.44 |
| 摸牌／仅胡 | 131.17 | 116.04 | 277.60 | 254.02 |

碰响应仍为3根／722节点／719边／15192见证请求／11628目标距离请求／25363候选操作。摸牌仍为11根／365节点／354边／11610见证请求／22270目标距离请求／17712候选操作。两者整图、全部评分、解释和排名逐项相同，未减少资格请求分母。没有新增跨请求缓存。

**最终守卫后的另一次本地复测仍逐项同图、同候选映射、同绝对评分与完整trace。**按下列程序，每条请求先旧完整再窄入口，各建图一次：碰响应1681.34／147.19毫秒，摸牌1309.22／108.97毫秒。这是作者对最终源码的单次建图测量，不含规则分析及评分耗时，不声称机器空闲或冷缓存；没有由耗时变化推断策略强度。

下列公开接口诊断可复测整图相等并打印建图时间；不运行桌赛，测量不设易受机器负载影响的通过阈值：

```python
import json, runpy, time, pytest
from hangma_bot.policy import route_vip_heuristic as policy

cases = runpy.run_path("tests/unit/hangma/test_route_hu_witness.py")
compare = cases["test_integrated_graph_scores_and_traces_equal_full_witness_oracle"]
build = policy.build_vip_route_scoring_view
rows = []

def timed_build(*args, **kwargs):
    """仅计公开建图调用，单位毫秒；保留其所有输出与异常。"""
    name = policy.analyze_waiting_hu_witness.__name__
    start = time.perf_counter()
    result = build(*args, **kwargs)
    rows.append({"entry": name, "graph_ms": (time.perf_counter()-start)*1000})
    return result

with pytest.MonkeyPatch.context() as patch:
    patch.setattr(policy, "build_vip_route_scoring_view", timed_build)
    for index in (0, 1):
        compare(patch, index)
print(json.dumps(rows))
```

## 5. 限制与后续门

**本批只交窄入口、等价测试与局部优化证据。**胡相关问题与结算保持同源；完整旧入口的其他动作族覆盖没有被搬入窄结果。它不返回可继续执行的 `source_state`，不重写官方序号或长期可达资格，也不提供新规则依据。实际取态、网络、提交、审计写盘、并发排队和保底余量均未计入上述耗时；两个选择出的慢观察不能估计总体分位数。

根代理负责策略接线、实际源码身份与合同更新，以及独立完整桌逐窗口动作／评分复验。根代理报告首版优化身份 `b78fe781...` 的两张8局桌自然完赛，3407个窗口的动作／绝对分／trace全部相同；这是守卫修正前的独立运行证据，原manifest保持不变。最终守卫版已另开 `evidence/t2-final-guarded-complete-tables-202` 输出路径，由根代理单独归档其身份与结果，不沿用首版成绩。

新运行源码已冻结；本报告不把局部加速或规则对照写成完整VIP、强度、上线时限或发布门通过。数据库、官方赛事、旧发布包及原性能证据未改。
