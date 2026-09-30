"""SimulationEngine：完整世界推进（parallel-v1 契约 §6 的实现）。

职责与边界：

- 不执行策略、网络、文件、系统时钟或评估统计；世界随机源只来自 MatchSpec；
- 规则裁决全部委托 hangma.progression（唯一规则源）与注入的 HangmaRules
  （合法性复核）；本文件只做发牌、牌墙物理顺序、事件簿记与机械应用；
- start/advance 返回的世界总在决策边界、终局或 blocked 三态之一；
- frame 把所有同期响应者一次性给出（同一推进前状态取观察），advance 对
  缺少/重复/多余窗口、旧 revision、非法动作原子拒绝（原世界不变）；
- 发牌按 (scenario_id, seed, round_no) 独立派生（shuffle.deal-v1），
  策略调用次数不消耗后续单局发牌随机源。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Optional, Tuple

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.progression import (
    EVENT_KIND_GAME_ENDED,
    EVENT_KIND_ROUND_ENDED,
    EventRecord,
    attach_draw,
    deal_state,
    end_as_draw,
    next_dealer,
    recompute_baotou,
    resolve,
)  # noqa: E501
from hangma_bot.kernel.actions import SEAT_COUNT, Tile, action_key
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import ScoreVector

from . import identity, projection, shuffle
from .artifacts import GUIDE_CAPTURED_AT, GUIDE_VERSION
from .interface import MatchSpec, SimulationChoice, SimulationDecision, SimulationFrame
from .shuffle import DEAL_ALGORITHM, RESERVE_TILES
from .state import RoundRecord, WorldState

WORLD_SCHEMA = "simulation-world/1"
"""模拟初版世界导出版本名（parallel-v1.json world_schema）。"""

_DECISION_WINDOWS = ("draw", "response_peng", "response_chi")


class SimulationEngine:
    """完整世界推进；不执行策略、网络、文件、系统时钟或评估统计。"""

    def __init__(self, rules: HangmaRules, *, rules_hash: Optional[str] = None) -> None:
        """由组合根注入唯一规则实现；各世界随机源只来自 MatchSpec。

        rules_hash 为规则源文件清单稳定哈希（simulation.artifacts.
        compute_rules_hash），由组合根离线计算一次传入，写入导出产物；
        为 None 时导出产物标注缺失。
        """
        if not isinstance(rules, HangmaRules):
            raise ValueError("SimulationEngine 必须注入 HangmaRules 实例")
        self.rules = rules
        self.rules_hash = rules_hash

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def start(self, spec: MatchSpec) -> WorldState:
        """创建新世界；固定 spec/规则与发牌版本可复现，不影响其他世界。"""
        self._validate_spec(spec)
        return self._deal_round(
            match_id=spec.match_id,
            scenario_id=spec.scenario_id,
            seed=spec.seed,
            rounds_per_game=spec.config.rounds_per_game,
            round_no=1,
            dealer_seat=spec.initial_dealer,
            initial_dealer=spec.initial_dealer,
            timing=spec.config.timing,
            scores=spec.initial_scores,
            seq=0,
            parent_hand_id=None,
        )

    def frame(self, world: WorldState) -> SimulationFrame:
        """返回独立可见观察；终态 decisions 为空，阻塞须提供原因。"""
        if world.blocked_reason is not None:
            return SimulationFrame(
                revision=world.revision,
                decisions=(),
                completed_hands=world.completed_hands,
                final_scores=None,
                blocked_reason=world.blocked_reason,
            )
        if world.is_match_end:
            return SimulationFrame(
                revision=world.revision,
                decisions=(),
                completed_hands=world.completed_hands,
                final_scores=world.scores,
                blocked_reason=None,
            )
        state = world.progression
        if state.window not in _DECISION_WINDOWS:
            raise ValueError(
                "frame 只能作用于决策边界/终局/阻塞世界（当前 window={0}）".format(
                    state.window,
                )
            )
        decisions = []
        if state.window == "draw":
            decision_seats = (state.turn_seat,)
        else:
            decision_seats = state.responding
        for seat in decision_seats:
            decisions.append(SimulationDecision(
                window_key=projection.window_key(world, seat),
                observation=projection.observation(world, seat),
                timeout_seconds=projection.timeout_for(world, state.window),
            ))
        return SimulationFrame(
            revision=world.revision,
            decisions=tuple(decisions),
            completed_hands=world.completed_hands,
            final_scores=None,
            blocked_reason=None,
        )

    def resample_future_drawable_wall(
        self, world: WorldState, *, sample_key: str
    ) -> WorldState:
        """为离线成对续打重排当前局尚未摸取的可摸区。

        只允许在决策边界调用。方法保留已经发生的牌墙前缀、四家当前暗手、
        公开事件、牌张多重集和固定保留区；同一世界与 ``sample_key`` 逐字
        可复现。返回新 ``WorldState``，原世界不变。它只隔离未来摸牌顺序
        方差，不是对未知他家手牌的后验采样，也不向策略暴露完整世界。
        """

        if not isinstance(world, WorldState):
            raise ValueError("resample_future_drawable_wall 需要 WorldState")
        if world.blocked_reason is not None or world.progression.window not in _DECISION_WINDOWS:
            raise ValueError("未来牌墙只可在未阻塞的决策边界重排")
        resampled = shuffle.resample_future_drawable(
            world.wall,
            wall_front=world.wall_front,
            wall_back=world.wall_back,
            scenario_id=world.scenario_id,
            seed=world.seed,
            round_no=world.round_no,
            sample_key=sample_key,
        )
        # round_start_wall 用于最终 RoundRecord；同步尚未消费区，确保导出记录
        # 与实际续打牌墙一致。已消费前缀及当前游标均不变。
        return replace(world, wall=resampled, round_start_wall=resampled)

    def resample_public_consistent_hidden_world(
        self,
        world: WorldState,
        *,
        focal_seat: int,
        sample_key: str,
    ) -> WorldState:
        """重采样焦点玩家不可见的三家暗手与未消费牌墙。

        本入口只供离线教师在焦点座位自己的摸牌或响应窗口使用。它固定焦点暗手、
        当前摸牌、全部公开事件/牌河/副露、各家手牌张数、积分、链状态、墙
        游标和牌张总多重集；三家暗手与尚未消费的牌墙（含保留区）共同洗牌
        后按原张数重新分配。返回世界的焦点 ``PlayerObservation`` 必须与输入
        逐字段相等，否则 fail-closed。

        这是假设“所有满足当前公开状态的隐藏分配等权”的稳健性样本。它未按
        历史动作策略似然加权，因此不是历史一致后验，不得用于线上决策输入，
        也不得把样本均值表述为真实对手 belief 下的无偏期望。返回世界明确
        标记为非历史一致，禁止导出成 ``full_world`` 牌谱。
        """

        if not isinstance(world, WorldState):
            raise ValueError("隐藏世界重采样需要 WorldState")
        if (
            isinstance(focal_seat, bool)
            or not isinstance(focal_seat, int)
            or not 0 <= focal_seat < SEAT_COUNT
        ):
            raise ValueError("focal_seat 必须是 0..3 整数")
        state = world.progression
        if world.blocked_reason is not None or state.window not in _DECISION_WINDOWS:
            raise ValueError("隐藏世界只可在未阻塞的本人动作窗口重采样")
        if state.window == "draw" and state.turn_seat != focal_seat:
            raise ValueError("focal_seat 必须是当前摸牌窗口行动座位")
        if state.window in ("response_peng", "response_chi") and focal_seat not in state.responding:
            raise ValueError("focal_seat 必须是当前响应窗口的回应座位")
        if any(
            seat.drawn is not None
            for index, seat in enumerate(state.seats)
            if index != focal_seat
        ):
            raise ValueError("非焦点座位存在当前摸牌，拒绝隐藏世界重采样")

        before = projection.observation(world, focal_seat)
        # 杠上补牌从可摸区尾端取走后，底层不可变 wall 元组仍保留该牌，
        # 位置落在 wall_back..round_start_wall_back 的已消费间隙。它既不在
        # 可摸区也不在固定保留区；重采样时不能再次放进未知牌池。
        drawable_wall = world.wall[world.wall_front:world.wall_back]
        reserved_wall = world.wall[world.round_start_wall_back:]
        unseen_wall = drawable_wall + reserved_wall
        opponent_sizes = {
            index: len(seat.hand)
            for index, seat in enumerate(state.seats)
            if index != focal_seat
        }
        pool = tuple(
            tile
            for index, seat in enumerate(state.seats)
            if index != focal_seat
            for tile in seat.hand
        ) + tuple(unseen_wall)
        sampled = shuffle.resample_public_consistent_hidden_pool(
            pool,
            scenario_id=world.scenario_id,
            seed=world.seed,
            round_no=world.round_no,
            revision=world.revision,
            focal_seat=focal_seat,
            sample_key=sample_key,
        )
        cursor = 0
        seats = list(state.seats)
        for index in range(SEAT_COUNT):
            if index == focal_seat:
                continue
            count = opponent_sizes[index]
            hand = tuple(sampled[cursor:cursor + count])
            cursor += count
            old = seats[index]
            seats[index] = replace(
                old,
                hand=hand,
                baotou=recompute_baotou(
                    hand,
                    len(old.melds),
                    sum(tile.code == "白" for tile in hand),
                ),
            )
        sampled_wall_suffix = tuple(sampled[cursor:])
        if len(sampled_wall_suffix) != len(unseen_wall):
            raise ValueError("隐藏世界重采样内部张数不守恒")
        drawable_count = len(drawable_wall)
        wall = (tuple(world.wall[:world.wall_front])
                + sampled_wall_suffix[:drawable_count]
                + tuple(world.wall[world.wall_back:world.round_start_wall_back])
                + sampled_wall_suffix[drawable_count:])
        sampled_world = replace(
            world,
            progression=replace(
                state,
                seats=(seats[0], seats[1], seats[2], seats[3]),
            ),
            wall=wall,
            round_start_wall=wall,
            history_consistent=False,
        )
        if projection.observation(sampled_world, focal_seat) != before:
            raise ValueError("隐藏世界重采样改变了焦点 PlayerObservation")
        return sampled_world

    def advance(
        self,
        world: WorldState,
        revision: int,
        choices: Tuple[SimulationChoice, ...],
    ) -> WorldState:
        """完整收集本帧所需选择后推进，返回新世界，原世界保持不变。

        旧 revision、缺少/重复/多余窗口或非法动作抛 ValueError 且不修改
        原世界。同期响应全部来自推进前观察；choices 的数组排列不改变规则
        裁决。
        """
        if world.blocked_reason is not None:
            raise ValueError("世界已阻塞（{0}），不能继续推进".format(world.blocked_reason))
        if world.is_match_end:
            raise ValueError("桌赛已结束，不能继续推进")
        if revision != world.revision:
            raise ValueError(
                "revision {0} 已过期（当前 {1}）：旧状态的选择不能用于新状态".format(
                    revision, world.revision,
                )
            )
        frame = self.frame(world)
        expected = {decision.window_key for decision in frame.decisions}
        provided = [choice.window_key for choice in choices]
        if len(provided) != len(set(provided)):
            raise ValueError("choices 包含重复窗口键")
        if set(provided) != expected:
            raise ValueError(
                "choices 窗口集与当前帧不一致：期望 {0} 个窗口，得到 {1} 个".format(
                    len(expected), len(provided),
                )
            )
        choice_by_key = {choice.window_key: choice for choice in choices}
        validated = []
        for decision in frame.decisions:
            choice = choice_by_key[decision.window_key]
            try:
                key = action_key(choice.action)
            except TypeError as exc:
                raise ValueError("未知动作类型：{0}".format(exc)) from None
            analysis = self.rules.analyze(decision.observation)
            if not any(
                candidate.action_key == key for candidate in analysis.legal_candidates
            ):
                raise ValueError(
                    "动作 {0} 不在座位 {1} 的窗口合法候选中（phase={2}）".format(
                        key, decision.window_key.seat, decision.window_key.phase.value,
                    )
                )
            validated.append((decision.window_key.seat, choice.action))
        transition = resolve(world.progression, tuple(validated))
        if transition.blocked is not None:
            return replace(
                world,
                blocked_reason=transition.blocked,
                revision=world.revision + 1,
            )
        new_world = replace(
            world,
            progression=transition.state,
            events=world.events + transition.events,
            revision=world.revision + 1,
        )
        return self._settle(new_world)

    def export_hand_settlement(self, world: WorldState, round_no: int) -> dict:
        """仅导出已完成单局的结算，供离线非历史一致世界配对比较。

        输入是模拟器拥有的完整世界及单局号；返回四座顺序的起止积分、分差、
        赢家、番数和结算说明。不导出起手、暗手、牌墙或事件，也不宣称该世界
        能由局初历史重放。目标单局未完成、身份或积分不守恒时抛出 ValueError；
        本方法不修改世界，不能代替 ``export_hand`` 生成正式牌谱。
        """
        if not isinstance(world, WorldState):
            raise ValueError("export_hand_settlement 需要 WorldState")
        if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
            raise ValueError("round_no 必须是正整数")
        records = [record for record in world.round_records if record.round_no == round_no]
        if len(records) != 1:
            raise ValueError("round_no 无唯一已完成单局记录")
        record = records[0]
        if (
            any(record.scores_before[i] + record.score_delta[i] != record.scores_after[i]
                for i in range(SEAT_COUNT))
            or sum(record.score_delta) != 0
        ):
            raise ValueError("单局结算积分不守恒")
        return {
            "coverage": "settlement_only",
            "round_no": record.round_no,
            "dealer_seat": record.dealer_seat,
            "scores_before": list(record.scores_before),
            "scores_after": list(record.scores_after),
            "score_delta": list(record.score_delta),
            "winner_seat": record.winner_seat,
            "is_draw": record.is_draw,
            "fan": record.fan,
            "details": list(record.details),
        }

    def export_hand(
        self, world: WorldState, round_no: int, *, match_id: Optional[str] = None
    ) -> dict:
        """导出单局行和可导入 world_payload；未完成结果明确为空。

        match_id 缺省沿用世界身份；另存反事实轨迹时由实验方提供独立非空 ID，
        导出器同步更换游戏键及世界元数据，保留 parent_hand_id/scenario_id。
        不修改原世界，不因新身份改变牌墙或随机状态。
        """
        if isinstance(round_no, bool) or not isinstance(round_no, int):
            raise ValueError("round_no 必须是整数")
        if not world.history_consistent:
            raise ValueError(
                "公开状态一致隐藏分配不是历史一致世界，禁止导出 full_world 牌谱"
            )
        # from_replay 导入的单局世界 rounds_per_game=1 但 round_no 保留原局号：
        # 可导出上限取 max(rounds_per_game, world.round_no)。
        upper = max(world.rounds_per_game, world.round_no)
        if round_no < 1 or round_no > upper:
            raise ValueError("round_no {0} 超出 1..{1}".format(round_no, upper))
        if round_no > world.round_no:
            raise ValueError("round_no {0} 尚未开始（当前第 {1} 局）".format(round_no, world.round_no))
        if round_no != world.round_no and round_no > len(world.round_records):
            raise ValueError(
                "round_no {0} 无可用记录（仅可导出已完成局或当前局）".format(round_no)
            )
        if match_id is not None and (not isinstance(match_id, str) or not match_id):
            raise ValueError("match_id 必须是非空字符串或 None")
        # 按 round_no 查记录（from_replay 单局世界的记录局号与列表下标不对齐，
        # 按下标取会静默把第 N 局数据标成请求的旧局号导出——身份错标）。
        record = next(
            (r for r in world.round_records if r.round_no == round_no), None
        )
        if record is None and round_no != world.round_no:
            raise ValueError(
                "round_no {0} 无可用记录（仅可导出已完成局或当前局）".format(round_no)
            )
        eff_match_id = world.match_id if match_id is None else match_id
        original_hand_id = identity.simulation_hand_id(
            world.scenario_id, world.match_id, round_no
        )
        parent_hand_id = None
        if eff_match_id != world.match_id:
            parent_hand_id = original_hand_id
        hand_id = identity.simulation_hand_id(world.scenario_id, eff_match_id, round_no)
        if record is not None:
            scores_before = record.scores_before
            scores_after = record.scores_after
            score_delta = record.score_delta
            winner_seat = record.winner_seat
            is_draw = record.is_draw
            fan = record.fan
            details = record.details
            initial_hands = record.initial_hands
            hands13 = _hands13_from_initial(initial_hands, record.dealer_drawn_tile, record.dealer_seat)
            drawn_tile = record.dealer_drawn_tile
            wall = record.wall
            wall_back = record.wall_back
            events = record.events
            dealer_seat = record.dealer_seat
            start_seq = record.events[0].seq - 1 if record.events else 0
        else:
            scores_before = world.round_scores_before
            scores_after = None
            score_delta = None
            winner_seat = None
            is_draw = None
            fan = None
            details = ()
            hands13 = world.round_initial_hands
            initial_hands = _initial_hands_14(
                world.round_initial_hands, world.round_dealer_drawn, world.dealer_seat
            )
            drawn_tile = world.round_dealer_drawn
            wall = world.round_start_wall
            wall_back = world.round_start_wall_back
            events = world.events
            dealer_seat = world.dealer_seat
            start_seq = world.round_start_seq
        payload = _world_payload(
            world,
            match_id=eff_match_id,
            round_no=round_no,
            dealer_seat=dealer_seat,
            hands13=hands13,
            drawn_tile=drawn_tile,
            wall=wall,
            wall_back=wall_back,
            scores_before=scores_before,
            start_seq=start_seq,
            parent_hand_id=parent_hand_id,
        )
        row = {
            "replay_schema_version": 1,
            "hand_id": hand_id,
            "split_group_id": identity.simulation_split_group_id(world.scenario_id),
            "origin": "simulated",
            "parent_hand_id": parent_hand_id,
            "coverage": "full_world",
            "game_key": {
                "source_namespace": "hangma-simulation",
                "tournament_id": world.scenario_id,
                "game_id": eff_match_id,
            },
            "round_no": round_no,
            "rule_config": {
                "ruleset_version": world.ruleset_version,
                "base_score": world.base_score,
                "you_cai_bi_kao": world.you_cai_bi_kao,
            },
            "rules_hash": world.rules_hash,
            "guide_version": GUIDE_VERSION,
            "guide_captured_at": GUIDE_CAPTURED_AT,
            "initial": {
                "dealer_seat": dealer_seat,
                "hands": [[t.code for t in hand] for hand in initial_hands],
                "drawn_tile": drawn_tile.code,
                "drawn_seat": dealer_seat,
                "draw_identity_known": True,
                "wall": [t.code for t in wall],
                "world_schema": WORLD_SCHEMA,
                "world_payload": payload,
                "source_refs": [],
            },
            "events": [_event_to_dict(event) for event in events],
            "scores_before": list(scores_before),
            "scores_after": None if scores_after is None else list(scores_after),
            "score_delta": None if score_delta is None else list(score_delta),
            "winner_seat": winner_seat,
            "is_draw": is_draw,
            "fan": fan,
            "details": list(details),
            "attempt_status": "valid" if scores_after is not None else "unknown",
            "result_confirmed": scores_after is not None,
            "missing_fields": [],
            "source_refs": [],
        }
        return row

    def from_replay(self, hand: Mapping[str, object]) -> WorldState:
        """只导入匹配 world_schema 的 full_world 起点；资料不足或版本不兼容
        抛 ValueError。

        起点为该单局而非原完整赛事；导入后的目标为完成这一单局。
        full_history 的历史路径核对另由 replay-check 命令执行，不冒充完整
        世界导入。
        """
        if not isinstance(hand, Mapping):
            raise ValueError("hand 必须是 Mapping")
        replay_version = hand.get("replay_schema_version")
        if replay_version != 1:
            raise ValueError(
                "replay_schema_version 必须是 1，得到 {0!r}".format(replay_version)
            )
        coverage = hand.get("coverage")
        if coverage != "full_world":
            raise ValueError(
                "只能导入 full_world 起点（coverage={0!r}）；full_history 缺墙必须拒绝".format(
                    coverage,
                )
            )
        initial = hand.get("initial")
        payload = None
        if isinstance(initial, Mapping):
            schema = initial.get("world_schema")
            if schema is not None and schema != WORLD_SCHEMA:
                raise ValueError(
                    "未知世界版本 {0!r}（本引擎支持 {1}）".format(schema, WORLD_SCHEMA)
                )
            payload = initial.get("world_payload")
        if not isinstance(payload, Mapping):
            raise ValueError(
                "缺少可导入的 world_payload（world_schema 必须为 {0}）".format(WORLD_SCHEMA)
            )
        world = self._world_from_payload(payload, hand)
        return self._settle(world)

    # ------------------------------------------------------------------
    # 内部：发牌、结算推进、导出组装
    # ------------------------------------------------------------------

    def _validate_spec(self, spec: MatchSpec) -> None:
        if spec.config.rules != self.rules.config:
            raise ValueError(
                "MatchSpec.config.rules 与注入规则引擎配置不一致；必须由组合根装配同一 RuleConfig"
            )

    def _deal_round(
        self,
        *,
        match_id: str,
        scenario_id: str,
        seed: int,
        rounds_per_game: int,
        round_no: int,
        dealer_seat: int,
        initial_dealer: int,
        timing: TimingConfig,
        scores: ScoreVector,
        seq: int,
        parent_hand_id: Optional[str],
    ) -> WorldState:
        """发新局到庄家直抽落地（决策边界）；牌墙物理事实在此组装。"""
        shuffled = shuffle.wall_for_round(scenario_id, seed, round_no)
        hands13, direct, wall = shuffle.deal_hands(shuffled, dealer_seat)
        wall_total = len(wall)
        wall_back = wall_total - RESERVE_TILES
        state = deal_state(
            round_no, dealer_seat, hands13, scores, seq, self.rules.config.base_score,
            wall_back, wall_total,
        )
        state = attach_draw(state, direct).state
        return WorldState(
            match_id=match_id,
            scenario_id=scenario_id,
            seed=seed,
            initial_dealer=initial_dealer,
            timing=timing,
            ruleset_version=self.rules.config.ruleset_version,
            base_score=self.rules.config.base_score,
            you_cai_bi_kao=self.rules.config.you_cai_bi_kao,
            rules_hash=self.rules_hash,
            parent_hand_id=parent_hand_id,
            rounds_per_game=rounds_per_game,
            round_no=round_no,
            dealer_seat=dealer_seat,
            round_scores_before=scores,
            round_start_seq=seq,
            revision=0,
            completed_hands=0,
            progression=state,
            wall=wall,
            wall_front=0,
            wall_back=wall_back,
            round_initial_hands=hands13,
            round_dealer_drawn=direct,
            round_start_wall=wall,
            round_start_wall_back=wall_back,
            events=(),
            round_records=(),
            history_consistent=True,
            blocked_reason=None,
        )

    def _settle(self, world: WorldState) -> WorldState:
        """自动推进非决策步骤，直到决策边界/终局/阻塞。"""
        while True:
            state = world.progression
            if state.window == "pending_draw":
                request = state.pending_draw
                drawable = world.wall_back - world.wall_front
                if not request.replacement and drawable <= 0:
                    state = end_as_draw(state)
                    world = replace(world, progression=state)
                    continue
                if drawable <= 0:
                    raise ValueError(
                        "杠上补牌请求但可摸区已耗尽（合法性验证应已拦截）"
                    )
                if request.replacement:
                    # 杠上补牌从可摸区尾端取：只移动补牌端游标，普通摸牌端不动
                    # （此前误把补牌也计入 front 消耗，会把可摸区牌滞留或摸进保留区）。
                    tile = world.wall[world.wall_back - 1]
                    wall_back = world.wall_back - 1
                    wall_front = world.wall_front
                else:
                    tile = world.wall[world.wall_front]
                    wall_back = world.wall_back
                    wall_front = world.wall_front + 1
                transition = attach_draw(state, tile)
                world = replace(
                    world,
                    progression=_apply_wall_counts(transition.state, drawable - 1),
                    wall_front=wall_front,
                    wall_back=wall_back,
                    events=world.events + transition.events,
                )
                continue
            if state.window == "ended":
                world = self._finalize_hand(world)
                continue
            return world

    def _finalize_hand(self, world: WorldState) -> WorldState:
        """单局收尾：轮次记录、round_ended/game_ended 事件、下一局或终局。"""
        result = world.progression.hand_result
        if result is None:
            raise ValueError("ended 状态缺少 HandResult（内部不一致）")
        state = world.progression
        seq = state.seq + 1
        scores_after = tuple(
            state.scores[i] + result.score_delta[i] for i in range(SEAT_COUNT)
        )
        round_ended = _round_ended_event(seq, result)
        initial_hands = _initial_hands_14(
            world.round_initial_hands, world.round_dealer_drawn, world.dealer_seat
        )
        record = RoundRecord(
            round_no=world.round_no,
            dealer_seat=world.dealer_seat,
            scores_before=world.round_scores_before,
            scores_after=scores_after,
            score_delta=result.score_delta,
            winner_seat=result.winner_seat,
            is_draw=result.is_draw,
            fan=result.fan,
            details=result.details,
            initial_hands=initial_hands,
            dealer_drawn_tile=world.round_dealer_drawn,
            wall=world.round_start_wall,
            wall_back=world.round_start_wall_back,
            events=world.events + (round_ended,),
        )
        completed_hands = world.completed_hands + 1
        if world.round_no >= world.rounds_per_game:
            game_ended = EventRecord(
                seq=seq + 1,
                kind=EVENT_KIND_GAME_ENDED,
                seat=None,
                tile=None,
                data=(("final_scores", tuple(scores_after)),),
            )
            final_state = replace(
                state,
                window="match_end",
                scores=scores_after,
                seq=seq + 1,
                turn_seat=None,
                responding=(),
                last_discard=None,
                pending_draw=None,
            )
            # 末局 record.events 必须含 game_ended（官方夹具末块 =
            # round_ended + game_ended；累计积分唯一载体 final_scores 只经它进入
            # 导出产物），与 RoundRecord docstring「末局含 game_ended」一致。
            final_record = replace(record, events=record.events + (game_ended,))
            return replace(
                world,
                progression=final_state,
                events=final_record.events,
                round_records=world.round_records + (final_record,),
                completed_hands=completed_hands,
            )
        next_round = world.round_no + 1
        new_dealer = next_dealer(world.dealer_seat, result.winner_seat, result.is_draw)
        next_world = self._deal_round(
            match_id=world.match_id,
            scenario_id=world.scenario_id,
            seed=world.seed,
            rounds_per_game=world.rounds_per_game,
            round_no=next_round,
            dealer_seat=new_dealer,
            initial_dealer=world.initial_dealer,
            timing=world.timing,
            scores=scores_after,
            seq=seq,
            parent_hand_id=world.parent_hand_id,
        )
        return replace(
            next_world,
            round_records=world.round_records + (record,),
            completed_hands=completed_hands,
            # 任一已完成局来自当前状态隐藏重排时，整张桌赛都不能再冒充
            # 可从局初事实完整重放；跨局继续保留 fail-closed 标记。
            history_consistent=world.history_consistent,
        )

    def _world_from_payload(self, payload: Mapping, hand: Mapping) -> WorldState:
        """world_payload → 单局世界；校验冗余字段与规则配置一致性。"""
        deal_algorithm = payload.get("deal_algorithm")
        if deal_algorithm != DEAL_ALGORITHM:
            raise ValueError(
                "不支持的发牌算法 {0!r}（本引擎 {1}）".format(deal_algorithm, DEAL_ALGORITHM)
            )
        rule_config = payload.get("rule_config")
        if not isinstance(rule_config, Mapping):
            raise ValueError("world_payload 缺少 rule_config")
        expected_config = {
            "ruleset_version": self.rules.config.ruleset_version,
            "base_score": self.rules.config.base_score,
            "you_cai_bi_kao": self.rules.config.you_cai_bi_kao,
        }
        if dict(rule_config) != expected_config:
            raise ValueError(
                "world_payload.rule_config 与引擎规则配置不一致：{0} != {1}".format(
                    dict(rule_config), expected_config,
                )
            )
        for field in ("match_id", "scenario_id", "seed", "round_no", "dealer_seat"):
            if field not in payload:
                raise ValueError("world_payload 缺少 {0}".format(field))
        hands_raw = payload.get("hands")
        drawn_raw = payload.get("dealer_drawn_tile")
        wall_raw = payload.get("wall")
        wall_front = payload.get("wall_front")
        wall_back = payload.get("wall_back")
        if (
            not isinstance(hands_raw, list)
            or len(hands_raw) != 4
            or not all(isinstance(hand, list) and len(hand) == 13 for hand in hands_raw)
        ):
            raise ValueError("world_payload.hands 必须是 4×13 张起手")
        if not isinstance(drawn_raw, str):
            raise ValueError("world_payload 缺少 dealer_drawn_tile")
        if not isinstance(wall_raw, list) or not wall_raw:
            raise ValueError("world_payload.wall 缺失")
        if wall_front != 0:
            raise ValueError("world_payload.wall_front 必须为 0（单局起点）")
        if (
            isinstance(wall_back, bool)
            or not isinstance(wall_back, int)
            or not 0 <= wall_back <= len(wall_raw)
        ):
            raise ValueError("world_payload.wall_back 非法")
        if len(wall_raw) - wall_back != RESERVE_TILES:
            raise ValueError(
                "保留区必须恰为 {0} 张（得到 {1}）".format(
                    RESERVE_TILES, len(wall_raw) - wall_back,
                )
            )
        if wall_back < 0:
            raise ValueError("可摸区张数不能为负")
        hands13 = tuple(tuple(Tile(code) for code in hand) for hand in hands_raw)
        drawn_tile = Tile(drawn_raw)
        wall = tuple(Tile(code) for code in wall_raw)
        dealer_seat = payload["dealer_seat"]
        if isinstance(dealer_seat, bool) or not isinstance(dealer_seat, int) or not 0 <= dealer_seat <= 3:
            raise ValueError("world_payload.dealer_seat 必须是 0-3")
        initial = hand.get("initial")
        if isinstance(initial, Mapping):
            _validate_initial_consistency(initial, hands13, drawn_tile, wall, dealer_seat)
        hand_id_raw = hand.get("hand_id")
        if isinstance(hand_id_raw, str) and hand_id_raw:
            expected_hand_id = identity.simulation_hand_id(
                payload["scenario_id"], payload["match_id"], payload["round_no"]
            )
            if hand_id_raw != expected_hand_id:
                raise ValueError(
                    "hand.hand_id 与 world_payload 身份不一致：{0} != {1}".format(
                        hand_id_raw, expected_hand_id,
                    )
                )
        scores_raw = payload.get("initial_scores")
        if (
            not isinstance(scores_raw, list)
            or len(scores_raw) != 4
            or not all(isinstance(x, int) and not isinstance(x, bool) for x in scores_raw)
        ):
            raise ValueError("world_payload.initial_scores 必须是四家整数向量")
        scores: ScoreVector = (scores_raw[0], scores_raw[1], scores_raw[2], scores_raw[3])
        timing_raw = payload.get("timing")
        try:
            timing = TimingConfig(**dict(timing_raw)) if isinstance(timing_raw, Mapping) else None
        except (TypeError, ValueError):
            timing = None
        if timing is None:
            raise ValueError("world_payload.timing 缺失或非法")
        parent_hand_id = payload.get("parent_hand_id")
        round_no = payload["round_no"]
        if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
            raise ValueError("world_payload.round_no 必须是正整数")
        seq = payload.get("seq", 0)
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            raise ValueError("world_payload.seq 必须是非负整数")
        state = deal_state(
            round_no, dealer_seat, hands13, scores, seq, self.rules.config.base_score,
            wall_back, len(wall),
        )
        state = attach_draw(state, drawn_tile).state
        return WorldState(
            match_id=payload["match_id"],
            scenario_id=payload["scenario_id"],
            seed=payload["seed"],
            initial_dealer=dealer_seat,
            timing=timing,
            ruleset_version=self.rules.config.ruleset_version,
            base_score=self.rules.config.base_score,
            you_cai_bi_kao=self.rules.config.you_cai_bi_kao,
            rules_hash=payload.get("rules_hash"),
            parent_hand_id=parent_hand_id if isinstance(parent_hand_id, str) else None,
            rounds_per_game=1,
            round_no=round_no,
            dealer_seat=dealer_seat,
            round_scores_before=scores,
            round_start_seq=seq,
            revision=0,
            completed_hands=0,
            progression=state,
            wall=wall,
            wall_front=0,
            wall_back=wall_back,
            round_initial_hands=hands13,
            round_dealer_drawn=drawn_tile,
            round_start_wall=wall,
            round_start_wall_back=wall_back,
            events=(),
            round_records=(),
            history_consistent=True,
            blocked_reason=None,
        )


def _apply_wall_counts(state, drawable: int):
    """摸牌落地后同步牌墙张数（可摸区 -1；总剩余 = 可摸 + 保留 20）。"""
    return replace(state, wall_drawable=drawable, wall_total=drawable + RESERVE_TILES)


def _initial_hands_14(hands13, dealer_drawn: Tile, dealer_seat: int):
    """按座位 0—3 保存起手，实际庄家直抽置尾，其余仍为 13 张。

    换庄后庄家不一定是座位 0；此处须与导入时按实际庄家移除直抽牌对应，
    否则导出会错配起手，甚至在庄家恰有同码牌时静默损坏世界起点。
    """
    return tuple(
        hand + (dealer_drawn,) if index == dealer_seat else hand
        for index, hand in enumerate(hands13)
    )


def _hands13_from_initial(initial_hands, dealer_drawn: Tile, dealer_seat: int):
    """14/13/13/13 → 4×13 起手（移除庄家第 14 张同码实例，保持顺序）。"""
    out = []
    for index, hand in enumerate(initial_hands):
        if index == dealer_seat:
            for pos in range(len(hand) - 1, -1, -1):
                if hand[pos].code == dealer_drawn.code:
                    out.append(hand[:pos] + hand[pos + 1:])
                    break
            else:
                raise ValueError("initial.hands 庄家 14 张中找不到直抽牌")
        else:
            out.append(hand)
    return tuple(out)


def _round_ended_event(seq: int, result) -> EventRecord:
    """round_ended 事件：官方字段语义（winner 座位 / draw / fan / detail / scores）。

    scores 是四家增量（delta），不是累计积分——官方夹具 t_714a 实测
    data.scores=[-8,-1,10,-1] 即该局增量；累计积分在 game_ended.final_scores。
    """
    if result.is_draw:
        return EventRecord(
            seq=seq,
            kind=EVENT_KIND_ROUND_ENDED,
            seat=None,
            tile=None,
            data=(("draw", True), ("scores", result.score_delta)),
        )
    return EventRecord(
        seq=seq,
        kind=EVENT_KIND_ROUND_ENDED,
        seat=result.winner_seat,
        tile=None,
        data=(
            ("draw", False),
            ("fan", result.fan),
            ("detail", result.details),
            ("scores", result.score_delta),
        ),
    )


def _jsonify(value):
    """事件 data 值递归归一：内存 tuple → JSON 数组语义（list）。"""
    if isinstance(value, (tuple, list)):
        return [_jsonify(item) for item in value]
    return value


def _event_to_dict(event: EventRecord) -> dict:
    """事件 → hands 行事件对象（官方字段语义；模拟无墙上时钟，ts=null）。

    data 值统一为 JSON 数组语义（list，而非内存 tuple）：进程内 check_hand
    复用同一行时与 JSON 落盘后行为一致（回归见 test_check_hand_in_memory_*）。
    """
    data = {key: _jsonify(value) for key, value in event.data} if event.data else None
    # seat=None 的事件只有流局 round_ended 与 game_ended：官方字段语义用 -1
    # 表示无获胜者（夹具 t_714a seq345/346、t_cee1 seq407/408），导出对齐官方。
    seat = event.seat if event.seat is not None else -1
    return {
        "seq": event.seq,
        "type": event.kind,
        "seat": seat,
        "tile": event.tile.code if event.tile is not None else "",
        "data": data,
        "ts": None,
        "source_refs": [],
    }


def _world_payload(
    world: WorldState,
    *,
    match_id: str,
    round_no: int,
    dealer_seat: int,
    hands13,
    drawn_tile: Tile,
    wall,
    wall_back: int,
    scores_before: ScoreVector,
    start_seq: int,
    parent_hand_id: Optional[str],
) -> dict:
    """构造 simulation-world/1 世界初始序列化（导出/导入的唯一载体）。"""
    return {
        "world_schema": WORLD_SCHEMA,
        "deal_algorithm": DEAL_ALGORITHM,
        "seed": world.seed,
        "scenario_id": world.scenario_id,
        "match_id": match_id,
        "round_no": round_no,
        "rounds_per_game": world.rounds_per_game,
        "parent_hand_id": parent_hand_id,
        "dealer_seat": dealer_seat,
        "initial_scores": list(scores_before),
        "rule_config": {
            "ruleset_version": world.ruleset_version,
            "base_score": world.base_score,
            "you_cai_bi_kao": world.you_cai_bi_kao,
        },
        "timing": {
            "peng_timeout_sec": world.timing.peng_timeout_sec,
            "chi_timeout_sec": world.timing.chi_timeout_sec,
            "discard_timeout_sec": world.timing.discard_timeout_sec,
        },
        "rules_hash": world.rules_hash,
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "hands": [[t.code for t in hand] for hand in hands13],
        "dealer_drawn_tile": drawn_tile.code,
        "wall": [t.code for t in wall],
        "wall_front": 0,
        "wall_back": wall_back,
        "seq": start_seq,
    }


def _validate_initial_consistency(initial, hands13, drawn_tile: Tile, wall, dealer_seat: int) -> None:
    """from_replay 冗余校验：initial.hands/wall 必须与 world_payload 一致。"""
    hands_raw = initial.get("hands")
    if isinstance(hands_raw, list) and len(hands_raw) == 4:
        expected = []
        for index, hand in enumerate(hands13):
            with_drawn = list(hand) + ([drawn_tile] if index == dealer_seat else [])
            expected.append([t.code for t in with_drawn])
        if hands_raw != expected:
            raise ValueError("initial.hands 与 world_payload 不一致（14/13/13/13 冗余校验失败）")
    wall_raw = initial.get("wall")
    if isinstance(wall_raw, list):
        if wall_raw != [t.code for t in wall]:
            raise ValueError("initial.wall 与 world_payload 不一致")
