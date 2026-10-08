"""包 A（R9 P25 · 复审 C5）：公开接口附录 ↔ **真实投影**逐字段一致性 + 题面渲染 + 输出范例。

复审 R9-P25 C5·P1 的根因是「模型在猜可见接口」：T05/T09 题面只有概述，作者读不到
action_value.py 实际投影给候选的字段（followup_branches / shanten_after /
standard_shanten_after / seven_pairs_shanten_after / useful_tiles / family_progress），
r1/T09 因此读了不存在的 normal_progress / seven_pairs_progress 并弃权；输出侧也没写清
SCORED.reason 的三态与空串禁则。

**本文件不照抄文档**：附录里每条路径、类型、枚举、可空条件都由 action_value.py 的真实投影
（ScoringView.candidate_view()）现场观察，双向断言：
  ① 观察到的每个节点（含 None 与空容器）都必须在附录里声明；
  ② 附录声明的每个类型/枚举成员都必须在真实投影里被观察到（不多写一个字）。
输入来源分三类，逐条列在 public-interface-verification.json 里：
  · 真实规则引擎（HangmaRules.analyze → build_scoring_view）：engine_draw / engine_peng；
  · 真实事实对象（FollowupBranchFacts / ValueRoute / FamilyProgress / Settlement /
    RuleIssue / UsefulTileFact 直投影）：facts_objects / nulls_and_melds / stage_complete；
  · 字典分支载荷（执行器与准入夹具的实际形态）：dict_branches。

运行（仓库根）：
    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_generate_public_interface.py -q
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("sitin_generate", _project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py"))
gen = importlib.util.module_from_spec(_spec)
sys.modules["sitin_generate"] = gen
assert _spec.loader is not None
_spec.loader.exec_module(gen)

REPO = _PROJECT_ROOT

from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import (  # noqa: E402
    FamilyId, FamilyProgress, FollowupBranchFacts, ProgressKind, RouteStatus,
    RuleIssue, Settlement, UsefulTileFact, ValueAnalysisLimits, ValueConditions,
    ValueRoute,
)
from hangma_bot.kernel.actions import (  # noqa: E402
    Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile, WindowKey, WindowPhase,
    action_key as kernel_action_key,
)
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.kernel.observation import (  # noqa: E402
    CompetitionContext, PlayerObservation, PublicDiscard, PublicMeld,
    RankingEntry, RulePublicState,
)
from hangma_bot.policy.action_value import (  # noqa: E402
    SCORING_VIEW_SCHEMA_VERSION, ActionScore, ActionView, CompetitionView,
    ReferenceFeature, ScoreBatch, ScoringView, run_scoring_skeleton,
)
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402

RULES_CONFIG = RuleConfig("pkg-a-public-interface", 1, False)
DRAW_HAND = "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4b"
PENG_HAND = "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b"


# ----------------------------------------------------------------- 夹具构造

def _observation(hand, draw=None, *, response=None, melds=None, remaining=60,
                 rule_state=None, chain_piao=None, gang_draw=None,
                 scores=(0, 0, 0, 0), discards=None):
    """真实 PlayerObservation（牌码与座位序都按 kernel 契约）。"""

    tiles = tuple(Tile(code) for code in hand.split())
    turn = 0 if response is None else 3
    rivers = [(), (), (), ()]
    if response is not None:
        rivers[turn] = (Tile(response),)
    if discards is not None:
        rivers = list(discards)
    return PlayerObservation(
        game_id="pkg-a-public-interface", seat=0, round_no=1, snapshot_seq=10,
        phase=("draw" if response is None else "response_peng"),
        dealer_seat=0, turn_seat=turn,
        responding_seats=() if response is None else (0,),
        my_hand=tiles, drawn_tile=Tile(draw) if draw else None,
        discards=tuple(rivers), melds=tuple(melds or ((), (), (), ())),
        hand_counts=tuple(len(tiles) + bool(draw) if seat == 0 else 13
                          for seat in range(4)),
        last_discard=None if response is None else PublicDiscard(turn, Tile(response), 10),
        remaining_tile_count=remaining, scores=scores,
        rule_state=(rule_state or RulePublicState(Tile("白"), False, 0, False)),
        public_history=(), chain_piao=chain_piao, gang_draw=gang_draw)


def _decision_request(observation, competition=None):
    """真实 DecisionRequest（供 build_scoring_view 走生产投影路径）。"""

    rules = HangmaRules(RULES_CONFIG)
    analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
    return DecisionRequest(
        observation=observation,
        competition=(competition or CompetitionContext(
            tournament_id="t", stage_no=None, stage_role=None, stage_total=None,
            participant_rank=None, ranking=(), observed_at_unix_ms=0)),
        rules=analysis, decision_id="d1", trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(game_id=observation.game_id,
                             round_no=observation.round_no,
                             trigger_seq=observation.snapshot_seq,
                             phase=(WindowPhase.DRAW if observation.phase == "draw"
                                    else WindowPhase.RESPONSE_PENG),
                             seat=observation.seat),
        rejected_attempts=())


def _engine_view(hand, draw=None, *, response=None, competition=None):
    """真实引擎窗口 → ScoringView（生产路径：analyze → DecisionRequest → 投影）。"""

    observation = _observation(hand, draw, response=response)
    return build_scoring_view(_decision_request(observation, competition))


def _av(action, action_type, **fields):
    """真实 ActionView（action_key 由 kernel 单一来源推出）。"""

    return ActionView(action=action, action_key=kernel_action_key(action),
                      action_type=action_type, is_legal=True, **fields)


def _view(actions, *, observation, competition=None, references=(),
          profile=None):
    """真实 ScoringView（动作按 action_key 升序；缺省 analysis_profile 取真实引擎快照）。"""

    ordered = tuple(sorted(actions, key=lambda item: item.action_key))
    return ScoringView(
        schema_version=SCORING_VIEW_SCHEMA_VERSION, visible_state=observation,
        actions=ordered,
        analysis_profile=(profile or _engine_view(DRAW_HAND, "9b").analysis_profile),
        competition=competition, reference_features=tuple(references))


# —— 真实事实对象（不经过引擎，但全部是 hangma 的公开值对象）——

def _real_branch(discard, shanten, support, standard=None, seven=None, useful=()):
    return FollowupBranchFacts(
        followup_key="peng:5w#{0}".format(discard), followup_discard=discard,
        combined_shanten=shanten, standard_shanten_after=standard,
        seven_pairs_shanten_after=seven, useful_tiles=tuple(useful),
        support_remaining=support)


def _real_settlement():
    return Settlement(score_delta=(8, -3, -3, -2), fan=4, details=("route-fan",))


def _real_route(draw_kind="normal", followup="9b", meld_count=0):
    return ValueRoute(
        conditional_settlement=_real_settlement(), shanten=0,
        useful_tiles=(UsefulTileFact("3w", 4), UsefulTileFact("6w", 2)),
        followup_discard=followup,
        conditions=ValueConditions(
            draw_kind=draw_kind,
            pre_draw_hand=tuple(DRAW_HAND.split())[:13 - 3 * meld_count],
            meld_count=meld_count, chain_count=1, chain_piao=0, baotou=True),
        support="conditional_witness")


def _all_family_entries():
    """覆盖 family/progress/route_status 三个枚举的**全部**成员（逐条真实值对象）。"""

    entries = []
    statuses = list(RouteStatus)
    index = 0
    for family in FamilyId:
        for progress in ProgressKind:
            entries.append(FamilyProgress(family, progress,
                                          statuses[index % len(statuses)],
                                          "依据 {0}/{1}".format(family.value,
                                                                progress.value)))
            index += 1
    return tuple(entries)


def facts_objects_view():
    """真实事实对象窗口：分支/路线/立即结算/家族明细/覆盖与问题全形状。"""

    branches = (_real_branch("9b", 1, 6, standard=1, seven=2,
                             useful=(UsefulTileFact("3w", 4), UsefulTileFact("6w", 2))),
                _real_branch("8b", 2, None, standard=None, seven=None, useful=()))
    actions = (
        _av(Chi((Tile("1w"), Tile("2w"), Tile("3w"))), "chi",
            followup_branches=branches, family_progress="ADVANCE",
            routes=(_real_route(),
                    _real_route(draw_kind="replacement", followup=None, meld_count=1)),
            fact_kind="hand_progress", shanten_after=1,
            useful_tiles=(UsefulTileFact("3w", 4),), best_followup_discard="9b",
            standard_shanten_after=1, seven_pairs_shanten_after=None,
            standard_useful_tiles=(UsefulTileFact("3w", 4),),
            seven_pairs_useful_tiles=(), pattern_progress_note="分牌型计数缺证据",
            family_progress_entries=_all_family_entries(), value_coverage="complete",
            value_issues=(RuleIssue(area="routes", reason="截断原因"),)),
        _av(Discard(Tile("4b")), "discard", fact_kind="win", shanten_after=-1,
            immediate_settlement=_real_settlement(), family_progress="CLOSE",
            useful_tiles=(), value_coverage="unavailable"),
        _av(Discard(Tile("5b")), "discard", fact_kind="not_applicable",
            family_progress="RETREAT", value_issues=()),
        _av(Discard(Tile("6b")), "discard", fact_kind="analysis_failed",
            family_progress="SAME", value_coverage="partial"),
    )
    return _view(actions, observation=_observation(DRAW_HAND, "9b"),
                 competition=None)


def nulls_and_melds_view():
    """缺证据与公开副露窗口：能空的全空、能有的都有（None 语义逐条落地）。"""

    melds = [(), (),
             (PublicMeld(seat=2, kind="peng", tiles=(Tile("5w"), Tile("5w"), Tile("5w")),
                         from_seat=3),
              PublicMeld(seat=2, kind="gang", tiles=(Tile("1b"), Tile("1b"), Tile("1b"),
                                                     Tile("1b")),
                         from_seat=None)),
             ()]
    observation = _observation(
        DRAW_HAND, "9b", melds=melds, remaining=None, chain_piao=1, gang_draw=True,
        rule_state=RulePublicState(Tile("白"), True, 2, True, catch_play_owner_seat=2),
        discards=((Tile("1w"),), (), (), (Tile("9b"),)))
    references = (
        ReferenceFeature(name="opp_win_share", value=0.25, version="ref/1",
                         unit="近似比例", missing_reason=None),
        ReferenceFeature(name="missing_share", value=0, version="ref/1",
                         unit="占位（无信息）", missing_reason="缺史：无校准数据"),
    )
    actions = (
        _av(Peng(Tile("5w")), "peng", followup_branches=None,
            family_progress="UNKNOWN"),
        _av(Gang(Tile("5w"), GangKind.EXPOSED), "gang",
            replacement_draw_unknown=True, family_progress="ADVANCE",
            fact_kind=None, shanten_after=None, value_coverage=None),
        _av(Hu(), "hu", immediate_settlement=_real_settlement(),
            family_progress="CLOSE"),
        _av(Pass(), "pass", family_progress="SAME",
            replacement_draw_unknown=False),
    )
    return _view(actions, observation=observation,
                 competition=CompetitionView(stage_scores=None,
                                             table_scores=(1, 2, 3, 4),
                                             freshness_masks=None,
                                             current_stage_scores=None),
                 references=references)


def stage_complete_view():
    """完整阶段账窗口：stage_scores / current_stage_scores 都是四元组（掩码 complete）。"""

    ranking = tuple(
        RankingEntry(participant_id="p{0}".format(seat), total_score=10 - seat * 3,
                     place_points=seat, god_count=0, games_played=2, rank=seat + 1)
        for seat in range(4))
    competition = CompetitionContext(
        tournament_id="t", stage_no=1, stage_role="group", stage_total=6,
        participant_rank=1, ranking=ranking, observed_at_unix_ms=0)
    return _engine_view(DRAW_HAND, "9b", competition=competition)


class _AliasBranch:
    """带规范别名属性的分支载体（对应 _branch_mapping 的**对象分支**路径）。

    生产 FollowupBranchFacts 不带 progress/route_state/fan/draw_kind/hand_codes，
    但它经由同一投影函数透传：这里的载体只为把「载体带这些属性时会出现哪些键」钉住。
    """


def _alias_branch():
    branch = _AliasBranch()
    branch.followup_key = "discard:1w#7b"
    branch.progress = "ADVANCE"
    branch.route_state = "WITNESSED"
    branch.fan = 3
    branch.draw_kind = "normal"
    branch.hand_codes = ("1w", "2w")
    return branch


def branch_carriers_view():
    """别名键载体窗口：对象分支的规范别名键 + 字典分支的原样透传。"""

    actions = (_av(Discard(Tile("1w")), "discard",
                   followup_branches=(_alias_branch(),), family_progress="ADVANCE"),)
    return _view(actions, observation=_observation(DRAW_HAND, "9b"), competition=None)


def dict_branches_view():
    """字典分支窗口：执行器与准入夹具的真实形态（布尔冒充数、null 值、别名键、额外键）。"""

    branches = (
        {"followup_key": "discard:1w#9b", "combined_shanten": True,
         "support_remaining": None, "route_status": "UNANALYZED",
         "standard_shanten_after": None, "progress": "UNKNOWN", "fan": 2,
         "draw_kind": "replacement", "hand_codes": ("1w", "2w"),
         "extra_field": "透传键"},
        # 准入侧 unknown_branch_none 的实际形态：分支存在但字段显式为 null。
        {"followup_key": "discard:1w#8b", "combined_shanten": None,
         "support_remaining": None, "seven_pairs_shanten_after": None},
    )
    actions = (_av(Discard(Tile("1w")), "discard", followup_branches=branches,
                   family_progress="UNKNOWN"),)
    return _view(actions, observation=_observation(DRAW_HAND, "9b"),
                 competition=None)


def minimal_view():
    """附录 examples.input 的最小合法窗口（一个带事实的弃牌 + 一个无事实的 pass）。"""

    actions = (
        _av(Discard(Tile("1w")), "discard", fact_kind="hand_progress",
            shanten_after=1, useful_tiles=(UsefulTileFact("3w", 4),),
            family_progress="ADVANCE"),
        _av(Pass(), "pass", family_progress="UNKNOWN"),
    )
    return _view(actions, observation=_observation(DRAW_HAND, "9b"),
                 competition=None)


FIXTURES = {
    "engine_draw": lambda: _engine_view(DRAW_HAND, "9b").candidate_view(),
    "engine_peng": lambda: _engine_view(PENG_HAND, response="5w").candidate_view(),
    "facts_objects": lambda: facts_objects_view().candidate_view(),
    "nulls_and_melds": lambda: nulls_and_melds_view().candidate_view(),
    "stage_complete": lambda: stage_complete_view().candidate_view(),
    "dict_branches": lambda: dict_branches_view().candidate_view(),
    "branch_carriers": lambda: branch_carriers_view().candidate_view(),
    "minimal": lambda: minimal_view().candidate_view(),
}


def _candidate_views():
    return {name: factory() for name, factory in FIXTURES.items()}


# ----------------------------------------------------------------- 路径工具

def _steps(path):
    """路径 → 步骤表：("key", 名) / ("iter", None)。支持 visible_state.melds[][] 这类多层展开。"""

    steps = []
    for chunk in path.split("."):
        name = chunk
        floors = 0
        while name.endswith("[]"):
            floors += 1
            name = name[:-2]
        if name:
            steps.append(("key", name))
        for _ in range(floors):
            steps.append(("iter", None))
    return steps


def _into(value, steps, found):
    if not steps:
        found.append(value)
        return
    kind, name = steps[0]
    if kind == "key":
        if not isinstance(value, dict) or name not in value:
            return
        _into(value[name], steps[1:], found)
        return
    if not isinstance(value, (tuple, list)):
        return
    for item in value:
        _into(item, steps[1:], found)


def resolve_path(view, path):
    """按附录路径取值：返回该路径在**真实投影**里命中到的全部节点。"""

    found = []
    _into(view, _steps(path), found)
    return found


def _wildcard_prefix(path):
    return path[:-2] if path.endswith(".*") else None


def walk_nodes(value, path=""):
    """真实投影的全部节点路径 → 类型名（空容器也记；非空容器只记子节点）。"""

    nodes = {}
    if isinstance(value, dict):
        if not value:
            nodes[path] = "dict"
        for key in value:
            nodes.update(walk_nodes(value[key],
                                    path + "." + str(key) if path else str(key)))
        return nodes
    if isinstance(value, (tuple, list)):
        if not value:
            nodes[path] = "tuple"
            return nodes
        for item in value:
            nodes.update(walk_nodes(item, path + "[]"))
        return nodes
    nodes[path] = type(value).__name__
    return nodes


@pytest.fixture(scope="module")
def appendix():
    return gen.load_action_value_public_interface()[0]


@pytest.fixture(scope="module")
def views():
    return _candidate_views()


# ------------------------------------------------ ① 断言：观察到的都在附录里

def _declared_lookup(appendix):
    """路径 → 声明；外加「容器声明的元素路径」（X[] 由 X 的 element_types 覆盖）。"""

    return {entry["path"]: entry for entry in appendix["paths"]}


def _match_declaration(declared, path):
    """返回覆盖该观察路径的声明（精确命中，或容器声明 + 元素层）。"""

    if path in declared:
        return declared[path]
    if path.endswith("[]"):
        parent = declared.get(path[:-2])
        if parent and parent.get("element_types"):
            return parent
    return None


def test_every_projected_node_is_declared(appendix, views):
    """反向完备性：真实投影产出的每个节点路径都必须能在附录里查到（含 None/空容器）。"""

    declared = _declared_lookup(appendix)
    wildcards = [prefix for prefix in (_wildcard_prefix(item) for item in declared)
                 if prefix]
    undeclared = []
    for name, candidate_view in views.items():
        for path, type_name in walk_nodes(candidate_view).items():
            if _match_declaration(declared, path) is not None:
                continue
            if any(path.startswith(prefix + ".") for prefix in wildcards):
                continue
            undeclared.append("{0}: {1} ({2})".format(name, path, type_name))
    assert undeclared == [], undeclared


def test_declared_types_are_exactly_the_observed_types(appendix, views):
    """双向一致：声明的类型集合 == 真实投影观察到的类型集合（不多不少）。"""

    problems = []
    for entry in appendix["paths"]:
        if _wildcard_prefix(entry["path"]):
            continue
        observed = set()
        for candidate_view in views.values():
            for value in resolve_path(candidate_view, entry["path"]):
                observed.add(type(value).__name__)
        if not observed:
            problems.append("{0}: 在所有夹具里都没观察到".format(entry["path"]))
            continue
        declared = set(entry["types"])
        missing = sorted(observed - declared)
        unwitnessed = sorted(declared - observed)
        if missing:
            problems.append("{0}: 观察到未声明的类型 {1}".format(entry["path"], missing))
        if unwitnessed:
            problems.append("{0}: 声明了未被观察到的类型 {1}".format(entry["path"],
                                                                    unwitnessed))
        element_types = entry.get("element_types")
        if element_types:
            observed_elements = set()
            for candidate_view in views.values():
                for value in resolve_path(candidate_view, entry["path"] + "[]"):
                    observed_elements.add(type(value).__name__)
            if observed_elements != set(element_types):
                problems.append("{0}[]: 观察 {1} != 声明的元素类型 {2}".format(
                    entry["path"], sorted(observed_elements), sorted(element_types)))
    assert problems == [], problems


def test_declared_enums_are_exactly_the_observed_values(appendix, views):
    """枚举逐成员核对：声明的每个成员都在真实投影里出现过，且没有多写。"""

    problems = []
    for entry in appendix["paths"]:
        members = entry.get("enum")
        if not members:
            continue
        observed = set()
        for candidate_view in views.values():
            for value in resolve_path(candidate_view, entry["path"]):
                if value is not None:
                    observed.add(value)
        if observed != set(members):
            problems.append("{0}: 观察 {1} != 声明 {2}".format(
                entry["path"], sorted(observed), sorted(members)))
    assert problems == [], problems


def test_null_when_is_declared_exactly_when_none_is_possible(appendix, views):
    """可空条件自洽：能出现 None 的路径必须写明 None 的含义；不能出现的不得声明 None。"""

    problems = []
    for entry in appendix["paths"]:
        if _wildcard_prefix(entry["path"]):
            continue
        nullable = "NoneType" in entry["types"]
        if nullable and not entry.get("null_when"):
            problems.append("{0}: 声明可空却没写 null_when".format(entry["path"]))
        if not nullable and entry.get("null_when"):
            problems.append("{0}: 写了 null_when 却没声明 NoneType".format(entry["path"]))
    assert problems == [], problems


def test_shape_text_and_declared_types_agree(appendix):
    """形状文本与声明类型不得互相矛盾（防「形状写错层级」这类静默漂移）。"""

    problems = []
    for entry in appendix["paths"]:
        shape = entry["shape"]
        types = set(entry["types"])
        if _wildcard_prefix(entry["path"]):
            continue
        if "元组[" in shape and "tuple" not in types:
            problems.append("{0}: shape 写了元组但 types 里没有 tuple".format(entry["path"]))
        if shape.startswith("映射") and "dict" not in types:
            problems.append("{0}: shape 写了映射但 types 里没有 dict".format(entry["path"]))
        for type_name in types:
            if type_name == "dict" and "映射" not in shape:
                problems.append("{0}: 声明了 dict 但 shape 未写映射".format(entry["path"]))
            if type_name == "tuple" and "元组" not in shape:
                problems.append("{0}: 声明了 tuple 但 shape 未写元组".format(entry["path"]))
            if type_name == "float" and "浮点" not in shape:
                problems.append("{0}: 声明了 float 但 shape 未写浮点".format(entry["path"]))
            if type_name == "NoneType" and "None" not in shape:
                problems.append("{0}: 声明了 NoneType 但 shape 未写 None".format(
                    entry["path"]))
        if entry.get("element_types") and "元组[" not in shape:
            problems.append("{0}: 声明了元素类型但 shape 不是元组".format(entry["path"]))
    assert problems == [], problems


def test_declared_sources_exist_in_the_projection_module(appendix):
    """附录点名的投影函数必须真实存在（不许指向不存在的实现）。"""

    import hangma_bot.policy.action_value as av

    source = appendix["source_of_truth"]
    assert source["projection_call"] == "ScoringView.candidate_view()"
    assert source["schema_version_value"] == SCORING_VIEW_SCHEMA_VERSION
    for name in source["projection_functions"]:
        assert callable(getattr(av, name, None)), name
    for entry in appendix["paths"]:
        if entry["source"] == "ScoringView.candidate_view":
            continue
        assert entry["source"] in source["projection_functions"], entry["path"]


# ------------------------------------------------ ② 附录例子就是真实投影

def test_appendix_example_input_is_a_real_projection(appendix):
    """最小合法输入必须**逐字节等于**真实投影的 candidate_view（不许手写示例）。"""

    example = appendix["examples"]["input"]
    assert example is not None, "附录缺最小合法输入（examples.input）"
    live = minimal_view().candidate_view()
    assert json.loads(json.dumps(live, sort_keys=True)) == example


def test_appendix_example_outputs_execute_against_the_real_skeleton(appendix):
    """两种合法输出必须真的能过 run_scoring_skeleton；空字符串 reason 必须整批失败。"""

    view = minimal_view()
    outputs = appendix["examples"]["outputs"]
    assert len(outputs) >= 3
    for item in outputs[:2]:
        batch = run_scoring_skeleton(view, lambda _view, raw=item["value"]: raw)
        assert isinstance(batch, ScoreBatch)
        assert batch.status == "SCORED"
        assert sorted(entry.action_key for entry in batch.entries) == sorted(
            view.expected_action_keys())
    with pytest.raises(ValueError) as excinfo:
        run_scoring_skeleton(view, lambda _view: outputs[2]["value"])
    assert "reason" in str(excinfo.value)


def test_reason_three_forms_match_the_production_skeleton():
    """reason 三态逐条执行：省略 / None / 非空字符串合法；空字符串非法。"""

    view = minimal_view()
    entries = tuple(ActionScore(action_key=key, score=-1.0, trace={})
                    for key in view.expected_action_keys())

    def _raw(**extra):
        payload = {"status": "SCORED", "entries": [
            {"action_key": entry.action_key, "score": entry.score,
             "trace": entry.trace} for entry in entries]}
        payload.update(extra)
        return payload

    omitted = run_scoring_skeleton(view, lambda _view: _raw())
    assert omitted.reason is None
    none_reason = run_scoring_skeleton(view, lambda _view: _raw(reason=None))
    assert none_reason.reason is None
    text_reason = run_scoring_skeleton(view, lambda _view: _raw(reason="降级原因"))
    assert text_reason.reason == "降级原因"
    with pytest.raises(ValueError):
        run_scoring_skeleton(view, lambda _view: _raw(reason=""))


# ------------------------------------------------ ③ 附录进题面（生成题/修复题）

MUTATION_MARKER = "（同源测试：改类型即改题面）"


def _generation_text():
    payload = gen.render_action_value_task_contract(
        objective_summary="测试目标", panel_boundary="测试面板", prompt_role="I1")
    return payload, gen.build_action_value_prompt(gen.OPERATOR_I1, payload).text


def test_appendix_is_rendered_into_both_task_kinds(appendix):
    """附录必须真的进题面：生成题与修复题都带逐字段清单（不是只修渲染函数）。"""

    payload, generation = _generation_text()
    repair = gen.build_action_value_repair_prompt("【材料一：候选源码（夹具）】").text
    for text in (generation, repair):
        assert "公开接口附录" in text
        for entry in appendix["paths"]:
            assert entry["path"] in text, entry["path"]
            assert entry["shape"] in text, entry["shape"]
        for item in appendix["view_api"]:
            assert item["name"] in text, item["name"]
        assert "reason 的三种合法形态" in text
    assert payload["public_interface_source"]["sha256"] == \
        gen.load_action_value_public_interface()[1]


def test_appendix_change_changes_both_prompts(monkeypatch, tmp_path, appendix):
    """同源核心：改附录一处类型 ⇒ 生成题与修复题的渲染文本与提示词身份都变。"""

    raw = (_project_file(_PROJECT_ROOT, REPO / gen.AV_PUBLIC_INTERFACE_RELPATH)).read_text(encoding="utf-8")
    payload_raw = json.loads(raw)
    entry = next(item for item in payload_raw["paths"]
                 if item["path"] == "actions[].family_progress")
    entry["types"] = ["str", "NoneType"]
    entry["shape"] = "字符串 | None"
    payload_raw["conventions"].append(MUTATION_MARKER)
    mutated = json.dumps(payload_raw, ensure_ascii=False, indent=2) + "\n"
    path = tmp_path / "action-value-public-interface-v1.json"
    path.write_text(mutated, encoding="utf-8")
    digest = gen.sha256_text(mutated)
    monkeypatch.setattr(gen, "load_action_value_public_interface",
                        lambda path=None: (gen.normalize_public_interface(
                            json.loads(mutated)), digest))
    _payload, generation = _generation_text()
    repair = gen.build_action_value_repair_prompt("【材料一】夹具").text
    for text in (generation, repair):
        assert MUTATION_MARKER in text
        assert "actions[].family_progress：字符串 | None；" in text
    assert "actions[].family_progress：标量；" not in generation
    monkeypatch.undo()
    _payload2, baseline = _generation_text()
    assert MUTATION_MARKER not in baseline
    assert gen.sha256_text(baseline) != gen.sha256_text(generation)


def test_missing_appendix_block_is_fail_closed():
    """附录缺表/缺块必须显式报缺（不得静默当成「没有接口约束」）。"""

    with pytest.raises(ValueError):
        gen.normalize_public_interface({"paths": []})
    with pytest.raises(ValueError):
        gen.normalize_public_interface({"paths": [{"path": "a"}], "view_api": []})
    lines = gen.render_public_interface_lines(
        "generation", {"appendix_id": "x", "applies_to": ["repair"]})
    joined = "\n".join(lines)
    assert "装配缺陷" in joined and "fail-closed" in joined


def test_appendix_and_current_contract_have_separate_frozen_identities():
    """附录是兄弟文件；当前 /4 合同摘要独立冻结，且两处路径不同。"""

    frozen = "69ac62bdac371b410af2448d6845003f7d193720c7785c8d3d2dd00d996de5f8"
    assert gen.sha256_file(_project_file(_PROJECT_ROOT, REPO / gen.AV_CONTRACT_RELPATH)) == frozen
    assert gen.AV_PUBLIC_INTERFACE_RELPATH != gen.AV_CONTRACT_RELPATH
    assert (_project_file(_PROJECT_ROOT, REPO / gen.AV_PUBLIC_INTERFACE_RELPATH)).is_file()


# --------------------------------- C5 点名字段的回归（r1/T09 读错字段）

C5_REQUIRED_PATHS = (
    "actions[].followup_branches",
    "actions[].followup_branches[].followup_key",
    "actions[].followup_branches[].combined_shanten",
    "actions[].followup_branches[].support_remaining",
    "actions[].shanten_after",
    "actions[].standard_shanten_after",
    "actions[].seven_pairs_shanten_after",
    "actions[].useful_tiles",
    "actions[].family_progress",
    "actions[].family_progress_entries",
    "actions[].immediate_settlement",
    "competition",
)


def test_c5_named_fields_are_all_declared_and_rendered(appendix):
    """复审 C5 逐字点名的动作字段必须在附录里（并真的进题面）。"""

    declared = {entry["path"] for entry in appendix["paths"]}
    for path in C5_REQUIRED_PATHS:
        assert path in declared, path
    _payload, generation = _generation_text()
    for path in C5_REQUIRED_PATHS:
        assert path in generation, path


def test_family_progress_is_family_progress_not_normal_or_seven_pairs(appendix):
    """family_progress 必须被写明是**家族**进展；不得暗示存在 normal/seven_pairs 进展。"""

    entry = next(item for item in appendix["paths"]
                 if item["path"] == "actions[].family_progress")
    assert "家族" in entry["note"]
    assert "不是" in entry["note"] and "普通型" in entry["note"]
    _payload, generation = _generation_text()
    assert "没有 normal_progress / seven_pairs_progress 这种字段" in generation
    # 两类进展的名字只作为「不存在」的显式警告出现，绝不作为可用字段出现。
    for ghost in ("normal_progress", "seven_pairs_progress"):
        for line in generation.splitlines():
            if ghost in line:
                assert "没有" in line and "字段" in line, line


def test_appendix_covers_the_action_value_facts_the_review_names(appendix):
    """覆盖字段数（机器可读）：附录必须完整覆盖动作牌效/分支/向听/有效牌/家族/结算。"""

    paths = {entry["path"] for entry in appendix["paths"]}
    expected = {
        "actions[].action_key", "actions[].action_type", "actions[].is_legal",
        "actions[].baotou_after",
        "actions[].fact_kind", "actions[].shanten_after", "actions[].useful_tiles",
        "actions[].standard_shanten_after", "actions[].seven_pairs_shanten_after",
        "actions[].standard_useful_tiles", "actions[].seven_pairs_useful_tiles",
        "actions[].replacement_draw_unknown", "actions[].best_followup_discard",
        "actions[].pattern_progress_note", "actions[].family_progress",
        "actions[].family_progress_entries", "actions[].immediate_settlement",
        "actions[].routes", "actions[].value_coverage", "actions[].value_issues",
        "visible_state.table_scores", "competition.stage_scores",
        "competition.table_scores", "competition.current_stage_scores",
        "competition.freshness_masks", "analysis_profile.ruleset_version",
        "reference_features[].missing_reason",
    }
    assert expected <= paths, sorted(expected - paths)
    assert len(appendix["paths"]) >= 100
