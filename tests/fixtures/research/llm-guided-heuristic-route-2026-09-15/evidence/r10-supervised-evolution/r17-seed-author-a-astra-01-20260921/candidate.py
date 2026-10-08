def score_actions(view):
    """按规则给出的单叶向听与逐牌公开容量评分，不产生动作或副作用。"""
    leaf = view["next"]
    support = leaf["support_remaining"]
    breadth = 0.0
    # 每个规范牌码是一个替代进张来源；同码的追加容量递减计入宽度。
    # 不推断牌形或牌墙位置，零容量仍是已知耗尽，不是未知值。
    for code, capacity in leaf["useful_tiles"]:
        breadth += capacity / (1.0 + capacity)
    # 容量短缺与牌码集中分别产生有界负担，均不是概率或预计摸牌次数。
    distance = max(0, leaf["shanten_after"])
    distance += 4.0 / (4.0 + support) + 1.0 / (1.0 + breadth)
    if leaf["replacement_draw_unknown"]:
        # 杠叶是补牌前事实；不给尚未观察到的补牌任何确定推进奖励。
        distance += 0.5
    # 同一评分尺度适用于双包络；包络下界、上界和根聚合由骨架决定。
    return 2.0 / (1.0 + distance) - 1.0
