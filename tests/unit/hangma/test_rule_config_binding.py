"""官方房规经公开装配入口绑定；有财必拷响不能硬编码或跨实例串线。

这里的配置是协议形态测试数据，不冒充官方对拍结果。牌型与胡牌资格的
专项金例由 test_engine 及官方 fan-calc 夹具覆盖；本文件验证配置边界。
"""

from dataclasses import replace

import pytest

from hangma_bot import bootstrap
from hangma_bot.adapters.official import dto, projector
from hangma_bot.adapters.official.errors import DtoError
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.application.contracts import (
    GuideVersion,
    ParticipantTerminalReason,
    RuntimeMode,
    SessionBootstrap,
)
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Hu, Tile
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState


def official_config(enabled):
    """构造官方 rules/detail 共用配置形态；开关故意允许坏值以测严格解析。"""
    return {
        "tournament_id": "t-config-binding",
        "status": "closed",
        "config": {
            "M": 4,
            "Rounds": 8,
            "BaseScore": 3,
            "YouCaiBiKao": enabled,
            "PengTimeoutSec": 1,
            "ChiTimeoutSec": 1,
            "DiscardTimeoutSec": 3,
        },
    }


def projected_config(enabled):
    return projector.rules_config(dto.parse_rules_config(official_config(enabled)), "binding-test")


def plain_wealth_win():
    """需要特定进张的有财普通型；白配旧单张，摸牌只补顺子，非爆头。"""
    return PlayerObservation(
        game_id="g-config-binding",
        seat=0,
        round_no=1,
        snapshot_seq=10,
        consumed_seq=10,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(c) for c in "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 东 白".split()),
        drawn_tile=Tile("3b"),
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=50,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
        chain_piao=0,
        gang_draw=False,
    )


@pytest.mark.parametrize("invalid", [None, 0, 1, "false", "true"])
def test_official_youcai_requires_explicit_boolean(invalid):
    with pytest.raises(DtoError, match="YouCaiBiKao"):
        dto.parse_rules_config(official_config(invalid))


def test_missing_official_youcai_is_not_defaulted():
    doc = official_config(False)
    del doc["config"]["YouCaiBiKao"]
    with pytest.raises(DtoError, match="YouCaiBiKao"):
        dto.parse_rules_config(doc)


def test_rule_instances_keep_independent_room_configuration():
    """交错复核两个赛事实例，同一手牌随各自官方开关变化。"""
    opened = HangmaRules(projected_config(False).rules)
    restricted = HangmaRules(projected_config(True).rules)
    observation = plain_wealth_win()
    for rules, allowed in ((opened, True), (restricted, False), (opened, True), (restricted, False)):
        for game_id in ("g1", "g2", "g3", "g4"):
            assert rules.validate(replace(observation, game_id=game_id), Hu()).legal is allowed


class ClosedSession:
    """只返回已关闭赛事的公开端口替身，验证装配绑定而不启动动作或计时等待。"""

    def __init__(self, config):
        snapshot = projector.tournament_snapshot(
            dto.parse_tournament_detail({"status": "closed", "my_games": [], "ranking": []}),
            tournament_id="t-config-binding",
            participant_id="p-config-binding",
            active_games=(),
            observed_revision=1,
            observed_at_unix_ms=0,
        ).snapshot
        self.result = SessionBootstrap(
            guide=GuideVersion(18, "2026-09-06", False),
            participant_id=snapshot.participant_id,
            tournament_id=snapshot.tournament_id,
            config=config,
            initial_snapshot=snapshot,
        )
        self.closed = False

    async def initialize(self, target):
        return self.result

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("mode", list(RuntimeMode))
async def test_public_bootstrap_binds_discovered_rule_config(mode, enabled, tmp_path, monkeypatch):
    """测试房、测试赛事、正式赛事、自由赛都只使用初始化发现的房规。"""
    discovered = projected_config(enabled)
    session = ClosedSession(discovered)
    created = []

    def capture_rules(config):
        rules = HangmaRules(config)
        created.append(rules)
        return rules

    # 替换组合根的公开工厂名以记录输入，仍返回真实 HangmaRules。
    monkeypatch.setattr(bootstrap, "HangmaRules", capture_rules)
    local = bootstrap.runtime_config_from_mapping({
        "mode": mode.value,
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t-config-binding",
        "known_guide_version": 18,
        "token": "test-only-config-binding-token",
        "token_kind": "test" if mode in (RuntimeMode.TEST_ROOM, RuntimeMode.TEST_TOURNAMENT) else "official",
        "audit_root": str(tmp_path),
    })
    if mode is RuntimeMode.AUTO_MATCH:
        assembled = bootstrap.build_auto_match_runtime(
            local, AutoMatchSettings(), session_factory=lambda: session,
        )
    else:
        assembled = bootstrap.build_runtime(local, session_factory=lambda: session)
    terminal = await assembled.run()
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_CLOSED
    assert session.closed
    assert len(created) == 1
    assert created[0].config is discovered.rules
    assert created[0].config.you_cai_bi_kao is enabled
    assert created[0].config.base_score == 3
    assert created[0].validate(plain_wealth_win(), Hu()).legal is (not enabled)
