"""官方测试房间赛后数据的解析与分块转换（仅离线使用）。

依据：指南 v14 §2.5（2026-09-05 抓取）——GET
/api/test-rooms/{id}/games/{batch}/events 返回完整赛后数据：blocks
（按块保存的完整事件流，含四家开局手牌 start_hands）、rounds（结果
摘要，需与事件核对；原始scores不能直接作为累计积分）。本模块只做解析与结构转换：不猜牌墙、
不重算规则；统一牌谱的组装（身份、来源引用、缺失评级）由
offline/replay.py 完成。

关键口径（parallel-contracts §4、contract-vectors 真实分块形态）：

- 同一 round_no 的 blocks 按 seq 范围拼接；后续 block 的
  start_hands=[null,null,null,null] 表示"不重复起点"，不是四家手牌变空；
- 首块起手张数实测为 14/13/13/13（庄家含一张已摸牌），首事件已是
  弃牌：没有额外牌身份时不猜 drawn_tile（draw_identity_known=false）；
- 官方事件字段（seq/type/seat/tile/data/ts）原样保留并容忍未知字段，
  不把公开事件当全信息事件格式；
- 文档缺少关键字段或字段类型非法抛 ValueError（未知主版本/形态拒绝，
  保留原文件供诊断，不伪造空牌谱）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OfficialBlock:
    """官方下载中的一个事件块；start_hands 为 None 表示缺起点证据。"""

    round_no: int
    seq_start: int
    seq_end: int
    truncated: bool
    dealer: int | None
    start_hands: tuple[tuple[str | None, ...], ...] | None
    events: tuple[Mapping[str, Any], ...]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class OfficialRoundResult:
    """官方每局结果；winner 的官方 -1 已规范为 None（无获胜者）。"""

    round_no: int
    dealer: int | None
    is_draw: bool | None
    winner_seat: int | None
    scores: tuple[int, ...] | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class OfficialRoomDocument:
    """已校验的测试房间赛后文档；unknown 顶层字段保留在 raw 中。"""

    room_id: str
    game_id: str
    batch: int
    status: str
    seats: tuple[Mapping[str, Any], ...]
    blocks: tuple[OfficialBlock, ...]
    rounds: tuple[OfficialRoundResult, ...]
    raw: Mapping[str, Any]


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(label + " 必须是 JSON 对象，得到 {!r}".format(value))
    return value


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " 必须是非空字符串，得到 {!r}".format(value))
    return value


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + " 必须是整数，得到 {!r}".format(value))
    return value


def _parse_round_result(value: object) -> OfficialRoundResult:
    data = _require_mapping(value, "rounds 元素")
    round_no = _require_int(data.get("round_no"), "round.round_no")
    dealer_raw = data.get("dealer")
    dealer = None if dealer_raw is None else _require_int(dealer_raw, "round.dealer")
    if dealer is not None and dealer not in range(4):
        raise ValueError("round.dealer 必须是座位 0—3")
    is_draw_raw = data.get("is_draw")
    is_draw: bool | None
    if is_draw_raw is None:
        is_draw = None
    elif isinstance(is_draw_raw, bool):
        is_draw = is_draw_raw
    elif isinstance(is_draw_raw, int) and is_draw_raw in (0, 1):
        is_draw = bool(is_draw_raw)
    else:
        raise ValueError("round.is_draw 必须是 0/1/布尔，得到 {!r}".format(is_draw_raw))
    winner_raw = data.get("winner")
    winner: int | None
    if winner_raw is None:
        winner = None
    else:
        winner_int = _require_int(winner_raw, "round.winner")
        # 官方 -1 规范为无获胜者（契约 §5.2），原响应保留在 raw。
        if winner_int not in (-1, 0, 1, 2, 3):
            raise ValueError("round.winner 必须是座位 0—3 或无胡家 -1")
        winner = None if winner_int == -1 else winner_int
    scores_raw = data.get("scores")
    scores: tuple[int, ...] | None
    if scores_raw is None:
        scores = None
    else:
        if not isinstance(scores_raw, list) or len(scores_raw) != 4:
            raise ValueError("round.scores 必须是座位 0—3 的四元数组")
        scores = tuple(_require_int(item, "round.scores 元素") for item in scores_raw)
    return OfficialRoundResult(
        round_no=round_no,
        dealer=dealer,
        is_draw=is_draw,
        winner_seat=winner,
        scores=scores,
        raw=data,
    )


def _parse_block(value: object) -> OfficialBlock:
    data = _require_mapping(value, "blocks 元素")
    round_no = _require_int(data.get("round_no"), "block.round_no")
    seq_start = _require_int(data.get("seq_start"), "block.seq_start")
    seq_end = _require_int(data.get("seq_end"), "block.seq_end")
    truncated = data.get("truncated")
    if not isinstance(truncated, bool):
        raise ValueError("block.truncated 必须是布尔值，得到 {!r}".format(truncated))
    dealer_raw = data.get("dealer")
    dealer = None if dealer_raw is None else _require_int(dealer_raw, "block.dealer")
    if dealer is not None and dealer not in range(4):
        raise ValueError("block.dealer 必须是座位 0—3")
    hands_raw = data.get("start_hands")
    hands: tuple[tuple[str | None, ...], ...] | None
    if hands_raw is None:
        hands = None
    else:
        if not isinstance(hands_raw, list) or len(hands_raw) != 4:
            raise ValueError("block.start_hands 必须是四家数组")
        rows: list[tuple[str | None, ...]] = []
        for row in hands_raw:
            # 实测形态：后续 block 的 start_hands=[null,null,null,null]，
            # 每行为 null 表示"不重复起点"；首块行是四家牌码数组。
            if row is None:
                rows.append((None, None, None, None))
                continue
            if not isinstance(row, list):
                raise ValueError("block.start_hands 行必须是数组或 null")
            rows.append(
                tuple(None if item is None else str(item) for item in row)
            )
        hands = tuple(rows)
    events_raw = data.get("events")
    if not isinstance(events_raw, list):
        raise ValueError("block.events 必须是数组")
    events = tuple(_require_mapping(item, "block.events 元素") for item in events_raw)
    return OfficialBlock(
        round_no=round_no,
        seq_start=seq_start,
        seq_end=seq_end,
        truncated=truncated,
        dealer=dealer,
        start_hands=hands,
        events=events,
        raw=data,
    )


def parse_room_document(document: object) -> OfficialRoomDocument:
    """解析并校验测试房间赛后文档；非法形态抛 ValueError。"""

    data = _require_mapping(document, "房间文档")
    room_id = _require_str(data.get("room_id"), "room_id")
    game_id = _require_str(data.get("game_id"), "game_id")
    batch = _require_int(data.get("batch"), "batch")
    status = _require_str(data.get("status"), "status")
    seats_raw = data.get("seats")
    if seats_raw is None:
        seats: tuple[Mapping[str, Any], ...] = ()
    else:
        if not isinstance(seats_raw, list):
            raise ValueError("seats 必须是数组")
        seats = tuple(_require_mapping(item, "seats 元素") for item in seats_raw)
    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        raise ValueError("blocks 必须是非空数组")
    blocks = tuple(_parse_block(item) for item in blocks_raw)
    rounds_raw = data.get("rounds", [])
    if not isinstance(rounds_raw, list):
        raise ValueError("rounds 必须是数组")
    rounds = tuple(_parse_round_result(item) for item in rounds_raw)
    return OfficialRoomDocument(
        room_id=room_id,
        game_id=game_id,
        batch=batch,
        status=status,
        seats=seats,
        blocks=blocks,
        rounds=rounds,
        raw=data,
    )


def merge_round_events(doc: OfficialRoomDocument, round_no: int) -> dict[str, Any]:
    """把同一 round_no 的块按 seq 范围拼接为有序事件流。

    返回：events（按 seq 升序的原事件对象数组）、seq_ranges（各块
    [start,end]）、block_count、truncated_any、issues（缺块/重叠/块内
    重复/范围不符的描述）。重复 seq 保留首条并报告，不覆盖原记录；
    缺块与重叠都降低完整性，由 coverage_grade 综合评级。
    """

    # 跨局文档的 JSON Pointer 必须指向**原文档** blocks 数组的下标：
    # 按 round_no 过滤后重新排序的局部下标会与文档错位（审查返工项）。
    located = [
        (doc_index, block)
        for doc_index, block in enumerate(doc.blocks)
        if block.round_no == round_no
    ]
    if not located:
        raise ValueError("round_no={} 没有任何事件块".format(round_no))
    located.sort(key=lambda pair: pair[1].seq_start)
    blocks = [block for _, block in located]
    issues: list[str] = []
    events: dict[int, Mapping[str, Any]] = {}
    # 每条保留事件在原文档块内的 JSON Pointer（供 source_refs 引用）。
    pointers: dict[int, str] = {}
    seq_ranges: list[list[int]] = []
    expected_next: int | None = None
    truncated_any = False
    for doc_index, block in located:
        seq_ranges.append([block.seq_start, block.seq_end])
        truncated_any = truncated_any or block.truncated
        if block.truncated:
            issues.append("block seq {}-{} 标记 truncated".format(block.seq_start, block.seq_end))
        if expected_next is not None and block.seq_start > expected_next:
            issues.append(
                "seq 缺口：期望 {} 实际块起点 {}".format(expected_next, block.seq_start)
            )
        elif expected_next is not None and block.seq_start < expected_next:
            issues.append(
                "seq 重叠：期望 {} 实际块起点 {}".format(expected_next, block.seq_start)
            )
        if block.seq_end - block.seq_start + 1 != len(block.events):
            issues.append(
                "块范围与事件数不符：seq {}-{} 有 {} 条事件".format(
                    block.seq_start, block.seq_end, len(block.events)
                )
            )
        expected_next = block.seq_end + 1
        for event_index, event in enumerate(block.events):
            seq = event.get("seq")
            if isinstance(seq, bool) or not isinstance(seq, int):
                issues.append("事件缺少整数 seq: {!r}".format(event))
                continue
            if not block.seq_start <= seq <= block.seq_end:
                issues.append("事件 seq={} 超出声明块范围".format(seq))
            if seq in events:
                issues.append("重复事件 seq={}，保留首条".format(seq))
                continue
            events[seq] = event
            pointers[seq] = "/blocks/{}/events/{}".format(doc_index, event_index)
    first = blocks[0]
    start_hands = first.start_hands
    complete_deal = (start_hands is not None and sorted(map(len, start_hands)) == [13, 13, 13, 14]
                     and all(tile is not None for row in start_hands for tile in row))
    previous_end = any(block.round_no == round_no - 1 and
                       any(e.get("type") == "round_ended" and e.get("seq") == first.seq_start - 1
                           for e in block.events) for block in doc.blocks)
    return {
        "round_no": round_no,
        "events": [events[seq] for seq in sorted(events)],
        "event_pointers": [pointers[seq] for seq in sorted(events)],
        "seq_ranges": seq_ranges,
        "block_count": len(blocks),
        "truncated_any": truncated_any,
        "issues": issues,
        "history_origin_known": first.seq_start == 1 or (complete_deal and previous_end),
    }


def coverage_grade(merge: Mapping[str, Any]) -> str:
    """按拼接质量评级：完整轨迹 full_history，否则 observed。

    full_world 绝不会由官方下载得出（无完整未来牌墙）；缺块、重叠、
    范围不符或截断都只能给 observed——已发生轨迹都无法证明完整时，
    不能声称 full_history。
    """

    issues = merge["issues"]
    if merge.get("truncated_any") or issues:
        return "observed"
    events = merge["events"]
    if not events:
        return "observed"
    seqs = [event["seq"] for event in events if isinstance(event.get("seq"), int)]
    if not seqs or seqs != list(range(seqs[0], seqs[-1] + 1)):
        return "observed"
    # 官方 seq 跨单局累加。已证明的本手起点无需重新从 1 编号。
    if seqs[0] != 1 and not merge.get("history_origin_known"):
        return "observed"
    return "full_history"


def _result_consistency(
    result: OfficialRoundResult,
    blocks: list[OfficialBlock],
    events: list[Mapping[str, Any]],
    *, summary_diagnostic: bool = False,
) -> dict[str, Any]:
    """核对同单局结果摘要与事件事实；冲突拒绝，缺证据标记未检查。

    依据 2026-09-06 测试房原始下载：round_ended.seat 为胡家（流局为 -1），
    data.draw/fan/scores 是终局结果；rounds.multiplier 对应 data.fan。
    本函数只比较官方事实，不用本地规则重算，也不把终局事件改写成摘要。
    """
    prefix = "official_result_conflict:round_no={}:".format(result.round_no)
    checks: dict[str, str] = {}

    def conflict(field: str) -> None:
        raise ValueError(prefix + field)

    def compare(field: str, left: Any, right: Any, *, known: bool) -> None:
        if not known:
            checks[field] = "not_checked"
        elif left != right:
            if summary_diagnostic:
                checks[field] = "conflict"
            else:
                conflict(field)
        else:
            checks[field] = "passed"

    dealers = {block.dealer for block in blocks if block.dealer is not None}
    if len(dealers) > 1:
        conflict("block.dealer")
    compare("dealer", result.dealer, next(iter(dealers), None),
            known=result.dealer is not None and bool(dealers))
    # merge_round_events 为缺块诊断保留首份重复 seq，不能因此隐藏原块内
    # 同一终局事件的矛盾副本，再把首份与摘要的一致性写成通过。
    terminal_by_seq: dict[int, Mapping[str, Any]] = {}
    for block in blocks:
        for raw_event in block.events:
            if raw_event.get("type") != "round_ended":
                continue
            seq = _require_int(raw_event.get("seq"), "round_ended.seq")
            if seq in terminal_by_seq and terminal_by_seq[seq] != raw_event:
                conflict("conflicting_round_ended_copy")
            terminal_by_seq[seq] = raw_event
    terminal = [event for event in events if event.get("type") == "round_ended"]
    if len(terminal) > 1:
        conflict("multiple_round_ended")
    event = terminal[0] if terminal else {}
    raw_data = event.get("data")
    data = {} if raw_data is None else _require_mapping(raw_data, "round_ended.data")

    # 终局 seat=-1 是明确无胡家，字段缺失/null 才是没有可核对证据。
    winner_raw = event.get("seat")
    if winner_raw is not None:
        winner_raw = _require_int(winner_raw, "round_ended.seat")
        if winner_raw not in (-1, 0, 1, 2, 3):
            conflict("round_ended.seat")
    event_winner = None if winner_raw == -1 else winner_raw
    summary_winner_known = result.raw.get("winner") is not None
    compare("winner", result.winner_seat, event_winner,
            known=summary_winner_known and winner_raw is not None)

    event_draw = data.get("draw")
    if event_draw is not None:
        if isinstance(event_draw, bool):
            pass
        elif isinstance(event_draw, int) and event_draw in (0, 1):
            event_draw = bool(event_draw)
        else:
            raise ValueError("round_ended.data.draw 必须是 0/1/布尔")
    compare("is_draw", result.is_draw, event_draw,
            known=result.is_draw is not None and event_draw is not None)
    if result.is_draw is not None and summary_winner_known:
        if result.is_draw != (result.winner_seat is None):
            if summary_diagnostic:
                checks["summary.winner_draw"] = "conflict"
            else:
                conflict("summary.winner_draw")
    if event_draw is not None and winner_raw is not None:
        if event_draw != (event_winner is None):
            conflict("round_ended.winner_draw")

    event_scores = data.get("scores")
    if event_scores is not None:
        if not isinstance(event_scores, list) or len(event_scores) != 4:
            raise ValueError("round_ended.data.scores 必须是座位 0—3 四元数组")
        event_scores = tuple(_require_int(value, "round_ended.data.scores 元素") for value in event_scores)
    compare("scores", result.scores, event_scores,
            known=result.scores is not None and event_scores is not None)

    multiplier = result.raw.get("multiplier")
    summary_fan = result.raw.get("fan")
    event_fan = data.get("fan")
    for label, value in (("round.multiplier", multiplier), ("round.fan", summary_fan),
                         ("round_ended.data.fan", event_fan)):
        if value is not None:
            _require_int(value, label)
            if value < 0:
                raise ValueError(label + " 不能为负数")
    if multiplier is not None and summary_fan is not None and multiplier != summary_fan:
        if summary_diagnostic:
            checks["summary.multiplier_fan"] = "conflict"
        else:
            conflict("summary.multiplier_fan")
    expected_fan = multiplier if multiplier is not None else summary_fan
    compare("fan", expected_fan, event_fan, known=expected_fan is not None and event_fan is not None)
    return {
        "status": ("conflict" if "conflict" in checks.values() else
                   "passed" if all(value == "passed" for value in checks.values()) else "not_checked"),
        "checks": checks,
    }


def _score_context(
    doc: OfficialRoomDocument, events: list[Mapping[str, Any]],
) -> tuple[list[int] | None, list[int] | None, list[int] | None]:
    """用场次终态及连续尾事件还原单局前后累计积分，不假定起始分为0。

    2026-09-07指南v18实测：round_ended.data.scores为单次变化，实时
    snapshot.scores与game_ended.final_scores为累计值。必须有终态锚点且
    本单局结束至场终的事件连续，才能反向扣除后续变化；否则返回三个None。
    顶层rounds.scores保留原义，不直接写入统一牌谱的scores_after。
    """
    unknown = (None, None, None)
    current = [event for event in events if event.get("type") == "round_ended"]
    if len(current) != 1:
        return unknown
    start = current[0]["seq"]
    by_seq = {}
    for block in doc.blocks:
        for event in block.events:
            seq = _require_int(event.get("seq"), "event.seq")
            if seq < start:
                continue
            if seq in by_seq and by_seq[seq] != event:
                raise ValueError("official_result_conflict:conflicting_score_context_event")
            by_seq[seq] = event
    finals = [event for event in by_seq.values() if event.get("type") == "game_ended"]
    if len(finals) != 1:
        return unknown
    end = finals[0]["seq"]
    if end < start or any(block.truncated and block.seq_end >= start and block.seq_start <= end
                          for block in doc.blocks):
        return unknown
    suffix = sorted(seq for seq in by_seq if start <= seq <= end)
    if len(suffix) != end - start + 1:
        return unknown  # 缺口中可能有未收到的积分变化，不凭现存结算条目猜累计值。

    def vector(event, field):
        if event.get("data") is None:
            return None
        data = _require_mapping(event["data"], "结算事件data")
        raw = data.get(field)
        if raw is None:
            return None
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            raise ValueError(field + " 必须是座位0—3的四元数组")
        return [_require_int(value, field + " 元素") for value in raw]

    after = vector(finals[0], "final_scores")
    delta = vector(current[0], "scores")
    if after is None or delta is None:
        return unknown
    for seq in suffix:
        event = by_seq[seq]
        if seq == start or event.get("type") != "round_ended":
            continue
        later_delta = vector(event, "scores")
        if later_delta is None:
            return unknown
        after = [value - change for value, change in zip(after, later_delta)]
    before = [value - change for value, change in zip(after, delta)]
    return before, after, delta


def round_data(
    doc: OfficialRoomDocument,
    round_no: int,
    *,
    file_sha256: str,
    json_pointer: str,
) -> dict[str, Any]:
    """把官方文档中一个 round_no 转成单局行数据（不含身份字段）。

    返回结构对应统一牌谱 §5.2 的 initial/events/scores/winner 部分；
    hand_id、split_group_id、game_key 与 source_refs 由 offline/replay.py
    按身份契约补齐。真实样本没有未来牌墙与额外牌身份：wall/drawn 全空。
    单局胡家/流局/积分变化取 round_ended，累计积分由场终锚点反推。
    顶层摘要差异以 result_consistency 标记；原事件自身冲突仍抛 ValueError。
    缺少结算事件不从摘要猜单局结果；原报文保留，不改写官方原值。
    """

    merge = merge_round_events(doc, round_no)
    results = [item for item in doc.rounds if item.round_no == round_no]
    # 起点块按最小 seq_start 选取：官方下载可能块乱序，按文档序取首块
    # 会拿错起点（审查收尾 F3）。
    round_blocks = [block for block in doc.blocks if block.round_no == round_no]
    first_block = min(round_blocks, key=lambda block: block.seq_start) if round_blocks else None
    if first_block is None:
        raise ValueError("round_no={} 没有事件块".format(round_no))
    # 单局事实由该事件块中的结算事件决定。顶层 rounds 是独立摘要，
    # 编号/条目/积分含义不可靠时只记录差异，不能覆盖胡家或丢掉完整单局。
    terminal = [event for event in merge["events"] if event.get("type") == "round_ended"]
    if len(terminal) > 1:
        raise ValueError("official_result_conflict:multiple_round_ended")
    event = terminal[0] if terminal else {}
    event_data = _require_mapping(event.get("data") or {}, "round_ended.data")
    result = _parse_round_result({
        "round_no": round_no, "dealer": first_block.dealer,
        "winner": event.get("seat"), "is_draw": event_data.get("draw"),
        "scores": event_data.get("scores"), "fan": event_data.get("fan"),
    })
    # 同一原事件的矛盾副本、多个终局、块庄家冲突仍是错误，不被诊断模式放行。
    _result_consistency(result, round_blocks, merge["events"])
    summary = results[0] if len(results) == 1 else OfficialRoundResult(round_no, None, None, None, None, {})
    consistency = _result_consistency(summary, round_blocks, merge["events"], summary_diagnostic=True)
    if len(results) > 1:
        consistency["status"] = "conflict"
        consistency["checks"]["duplicate_summary"] = "conflict"
    dealer = first_block.dealer
    if dealer is None and result.dealer is not None:
        dealer = result.dealer
    hands: tuple[tuple[str | None, ...], ...] | None
    later_null = True
    if first_block.start_hands is None:
        hands = None
        later_null = False
    else:
        hands = first_block.start_hands
    for block in doc.blocks:
        if block.round_no != round_no or block is first_block:
            continue
        if block.start_hands is not None and any(
            tile is not None for row in block.start_hands for tile in row
        ):
            later_null = False
    missing: list[str] = [
        "result_consistency:not_checked:" + field
        for field, status in consistency["checks"].items() if status == "not_checked"
    ]
    if hands is None:
        missing.append("start_hands")
    if result.scores is None:
        missing.append("scores")
    if result.is_draw is None and result.winner_seat is None:
        # 胜负未知才算缺失；is_draw=true 且 winner=None 是已确认的流局
        # （官方 -1 规范为无获胜者），不是缺失。
        missing.append("winner")
    if not merge["issues"]:
        missing.append("wall")
        missing.append("draw_identity")
    else:
        missing.extend("events:" + issue for issue in merge["issues"])
        missing.append("wall")
        missing.append("draw_identity")
    missing = sorted(set(missing))
    scores_before, scores_after, score_delta = _score_context(doc, merge["events"])
    if scores_after is None:
        missing.append("cumulative_score_context")
    return {
        "round_no": round_no,
        "initial": {
            "dealer_seat": dealer,
            "hands": None if hands is None else [list(row) for row in hands],
            "drawn_tile": None,
            "drawn_seat": None,
            "draw_identity_known": False,
            "wall": None,
            "world_schema": None,
            "world_payload": None,
            "start_hand_lengths": (
                None if hands is None else [len(row) for row in hands]
            ),
            "later_start_hands_are_null": later_null,
        },
        "events": list(merge["events"]),
        "event_pointers": list(merge["event_pointers"]),
        "scores_before": scores_before,
        "scores_after": scores_after,
        "score_delta": score_delta,
        "winner_seat": result.winner_seat,
        "is_draw": result.is_draw,
        "coverage": coverage_grade(merge),
        "result_confirmed": (doc.status == "finished" and bool(terminal)
                             and result.is_draw is not None and event.get("seat") is not None),
        "result_source": "round_ended" if terminal else "unknown",
        "result_consistency": consistency,  # 字段缺失为 not_checked，不能当 passed
        "block_count": merge["block_count"],
        "seq_ranges": merge["seq_ranges"],
        "truncated_any": merge["truncated_any"],
        "missing_fields": missing,
        "file_sha256": file_sha256,
        "json_pointer": json_pointer,
    }


__all__ = [
    "OfficialBlock",
    "OfficialRoomDocument",
    "OfficialRoundResult",
    "coverage_grade",
    "merge_round_events",
    "parse_room_document",
    "round_data",
]
