"""启动脚本契约：配置解析、模式/Token 类别核对、Token 掩码与四身份编排校验。

只验证脚本的纯函数路径（配置加载、派生配置、结果解析、汇总渲染），
不启动任何网络连接或真实子进程（官方路径由测试房间 C5/C6 验收）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location("hangma_scripts_" + name, SCRIPTS_DIR / name)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[spec.name] = module  # dataclass 注解求值需要模块已注册
    spec.loader.exec_module(module)
    return module


participant = _load_script("run_participant.py")
room = _load_script("run_test_room.py")

SECRET_A = "room-secret-token-A-0123456789abcdef"
SECRET_B = "room-secret-token-B-0123456789abcdef"
SECRET_C = "room-secret-token-C-0123456789abcdef"
SECRET_D = "room-secret-token-D-0123456789abcdef"


def _participant_config(tmp_path: Path, **overrides) -> dict:
    data = {
        "mode": "test_room",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t1",
        "known_guide_version": 8,
        "token_env": "HM_PARTICIPANT_TOKEN",
        "token_kind": "test",
        "audit_root": str(tmp_path / "audit"),
        "strategy": "weighted_heuristic",
    }
    data.update(overrides)
    return data


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _room_config(**overrides) -> dict:
    data = {
        "mode": "test_room",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t1",
        "known_guide_version": 8,
        "audit_root": "./room-audit",
        "identities": [
            {"slot": "A", "token_env": "HM_ROOM_A"},
            {"slot": "B", "token_env": "HM_ROOM_B"},
            {"slot": "C", "token": SECRET_C},
            {"slot": "D", "token": SECRET_D},
        ],
    }
    data.update(overrides)
    return data


class TestRunParticipantScript:
    def test_load_config_resolves_token_env(self, tmp_path):
        path = _write_config(tmp_path, _participant_config(tmp_path))
        config = participant.load_config(
            path, environ={"HM_PARTICIPANT_TOKEN": "env-secret-abcdef1234567890"}
        )
        assert config.token == "env-secret-abcdef1234567890"
        assert config.token_kind.value == "test"

    def test_banner_masks_token(self, tmp_path):
        path = _write_config(tmp_path, _participant_config(tmp_path))
        config = participant.load_config(
            path, environ={"HM_PARTICIPANT_TOKEN": "env-secret-abcdef1234567890"}
        )
        assembled = participant.build_runtime(config, session_factory=lambda: _StubSession())
        lines = "\n".join(participant.banner_lines(assembled))
        assert "env-secret" not in lines
        assert config.mode.value in lines
        assert config.expected_tournament_id in lines
        assert config.strategy in lines
        assert assembled.run_id in lines

    def test_main_reports_usage_error_without_network(self, capsys):
        code = participant.main(["--config", "/nonexistent/config.json"])
        assert code == participant.EXIT_USAGE
        assert "配置错误" in capsys.readouterr().err

    def test_main_rejects_mode_token_mismatch_before_network(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("HM_PARTICIPANT_TOKEN", "env-secret-abcdef1234567890")
        path = _write_config(
            tmp_path,
            _participant_config(
                tmp_path, mode="official_tournament", token_kind="test"
            ),
        )
        code = participant.main(["--config", str(path)])
        assert code == participant.EXIT_USAGE
        assert "不匹配" in capsys.readouterr().err

    def test_terminal_exit_code_mapping(self):
        assert participant.terminal_exit_code(None, 2) == participant.EXIT_SIGINT
        assert participant.terminal_exit_code(None, 15) == participant.EXIT_SIGTERM
        assert participant.terminal_exit_code(None, None) == participant.EXIT_FATAL

        terminal = _terminal(participant, "eliminated")
        assert participant.terminal_exit_code(terminal, None) == participant.EXIT_COMPLETED
        terminal = _terminal(participant, "authentication_failed")
        assert participant.terminal_exit_code(terminal, None) == participant.EXIT_PERMANENT
        terminal = _terminal(participant, "fatal_protocol_error")
        assert participant.terminal_exit_code(terminal, None) == participant.EXIT_FATAL


class TestRunTestRoomScript:
    def test_load_room_config(self, tmp_path):
        room_config = room.load_room_config(
            _write_room_json(tmp_path, _room_config()),
            environ={"HM_ROOM_A": SECRET_A, "HM_ROOM_B": SECRET_B},
        )
        assert len(room_config.identities) == 4
        assert [i.slot for i in room_config.identities] == ["A", "B", "C", "D"]
        assert room_config.identities[0].token == SECRET_A
        assert room_config.identities[2].token == SECRET_C
        assert "env:HM_ROOM_A" == room_config.identities[0].token_source
        assert SECRET_A not in repr(room_config.identities[0])

    def test_room_requires_exactly_four_identities(self, tmp_path):
        with pytest.raises(ValueError, match="四个身份"):
            room.load_room_config(_write_room_json(tmp_path, _room_config(identities=[{"slot": "A", "token": SECRET_A}])))

    def test_room_requires_test_room_mode(self, tmp_path):
        with pytest.raises(ValueError, match="test_room"):
            room.load_room_config(
                _write_room_json(tmp_path, _room_config(mode="official_tournament"))
            )

    def test_room_rejects_duplicate_slots(self, tmp_path):
        identities = [
            {"slot": "A", "token": SECRET_A},
            {"slot": "A", "token": SECRET_B},
            {"slot": "C", "token": SECRET_C},
            {"slot": "D", "token": SECRET_D},
        ]
        with pytest.raises(ValueError, match="互不相同"):
            room.load_room_config(_write_room_json(tmp_path, _room_config(identities=identities)))

    def test_room_rejects_identity_without_token(self, tmp_path):
        identities = [
            {"slot": "A", "token": SECRET_A},
            {"slot": "B"},
            {"slot": "C", "token": SECRET_C},
            {"slot": "D", "token": SECRET_D},
        ]
        with pytest.raises(ValueError, match="只能提供一个"):
            room.load_room_config(_write_room_json(tmp_path, _room_config(identities=identities)))

    def test_child_config_never_contains_token(self, tmp_path):
        room_config = room.load_room_config(
            _write_room_json(tmp_path, _room_config()),
            environ={"HM_ROOM_A": SECRET_A, "HM_ROOM_B": SECRET_B},
        )
        identity = room_config.identities[0]
        child = room.child_config_mapping(room_config, identity)
        assert "token" not in child
        assert child["token_env"] == room.TOKEN_ENV_VAR
        assert child["token_kind"] == "test"
        assert child["audit_root"].endswith("slot-A")
        serialized = json.dumps(child, ensure_ascii=False)
        assert SECRET_A not in serialized
        assert SECRET_C not in serialized

    def test_room_rejects_invalid_finished_restart_delay(self, tmp_path):
        with pytest.raises(ValueError, match="finished_restart_delay_seconds"):
            room.load_room_config(
                _write_room_json(
                    tmp_path,
                    _room_config(restart={"finished_restart_delay_seconds": 0}),
                ),
                environ={"HM_ROOM_A": SECRET_A, "HM_ROOM_B": SECRET_B},
            )

    @pytest.mark.parametrize(
        "restart_patch,field",
        [
            ({"base_delay_seconds": 0}, "base_delay_seconds"),
            ({"base_delay_seconds": -1.5}, "base_delay_seconds"),
            ({"max_delay_seconds": 0}, "max_delay_seconds"),
            ({"max_delay_seconds": "abc"}, "max_delay_seconds"),
            ({"factor": 0.5}, "factor"),
            ({"factor": -2.0}, "factor"),
        ],
    )
    def test_room_rejects_invalid_backoff_fields(self, tmp_path, restart_patch, field):
        """NF2：base_delay_seconds/max_delay_seconds 须为正，factor 须 >= 1；
        全部在配置期拒绝（exit 2 配置错误口径）。"""

        with pytest.raises(ValueError, match=field):
            room.load_room_config(
                _write_room_json(tmp_path, _room_config(restart=restart_patch)),
                environ={"HM_ROOM_A": SECRET_A, "HM_ROOM_B": SECRET_B},
            )

    def test_room_rejects_nan_backoff_fields(self, tmp_path):
        """NaN 不是有限秒数：not > 0 判定兜底拒绝（json.loads 接受 NaN 字面量）。"""

        raw = json.dumps(_room_config(), ensure_ascii=False)
        raw = raw.replace(
            '"identities":',
            '"restart": {"base_delay_seconds": NaN}, "identities":',
        )
        path = tmp_path / "room-nan.json"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError, match="base_delay_seconds"):
            room.load_room_config(
                path, environ={"HM_ROOM_A": SECRET_A, "HM_ROOM_B": SECRET_B}
            )

    def test_result_line_parsing(self):
        parsed = room._parse_result(
            "普通日志\nRESULT " + json.dumps({"run_id": "run-1", "terminal_reason": "eliminated"}) + "\n",
        )
        assert parsed["run_id"] == "run-1"
        assert room._parse_result("没有结果行") == {}

    def test_report_lines_cover_all_identities(self):
        reports = [
            room.IdentityReport(slot="A", outcome="completed", terminal_reason="eliminated"),
            room.IdentityReport(slot="B", outcome="completed", terminal_reason="tournament_finished"),
            room.IdentityReport(slot="C", outcome="failed", terminal_reason="authentication_failed"),
            room.IdentityReport(slot="D", outcome="restart_exhausted"),
        ]
        rendered = "\n".join(room.report_lines(reports))
        for report in reports:
            assert report.slot in rendered
            assert report.outcome in rendered
        assert SECRET_A not in rendered


def _write_room_json(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "room.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _terminal(participant_module, reason: str):
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
    )

    return ParticipantTerminal(
        reason=ParticipantTerminalReason(reason),
        last_snapshot=None,
        detail="测试终态",
    )


class _StubSession:
    async def initialize(self, target):
        raise NotImplementedError

    async def register(self):
        raise NotImplementedError

    async def ready(self, expected_stage):
        raise NotImplementedError

    async def next_update(self):
        raise NotImplementedError

    def open_game(self, game_id):
        raise NotImplementedError

    async def aclose(self):
        return None


class TestTokenFileAndLeakScan:
    def _config_without_token(self, tmp_path: Path) -> dict:
        data = _participant_config(tmp_path)
        del data["token_env"]
        return data

    def test_load_config_token_file(self, tmp_path):
        token_file = tmp_path / "private-token.txt"
        token_file.write_text("  file-secret-token-0000000000000000  \n", encoding="utf-8")
        path = _write_config(tmp_path, self._config_without_token(tmp_path))
        config = participant.load_config(path, token_file=str(token_file))
        assert config.token == "file-secret-token-0000000000000000"

    def test_token_file_conflicts_with_config_token(self, tmp_path):
        token_file = tmp_path / "private-token.txt"
        token_file.write_text("file-secret-token-0000000000000000\n", encoding="utf-8")
        path = _write_config(tmp_path, _participant_config(tmp_path))  # 内含 token_env
        with pytest.raises(ValueError, match="互斥"):
            participant.load_config(
                path,
                environ={"HM_PARTICIPANT_TOKEN": "env-secret-abcdef1234567890"},
                token_file=str(token_file),
            )

    def test_multiline_token_file_rejected_without_leaking_content(self, tmp_path):
        token_file = tmp_path / "multi.txt"
        token_file.write_text(
            "secret-line-one-0000000000000000\nsecret-line-two-0000000000000000\n",
            encoding="utf-8",
        )
        path = _write_config(tmp_path, self._config_without_token(tmp_path))
        with pytest.raises(ValueError, match="多行") as excinfo:
            participant.load_config(path, token_file=str(token_file))
        assert "secret-line-one" not in str(excinfo.value)

    def test_banner_and_result_never_contain_token(self, tmp_path):
        secret = "leak-check-token-0123456789abcdef"
        path = _write_config(tmp_path, _participant_config(tmp_path))
        config = participant.load_config(path, environ={"HM_PARTICIPANT_TOKEN": secret})
        assembled = participant.build_runtime(config, session_factory=lambda: _StubSession())
        terminal = _terminal(participant, "eliminated")
        for text in (
            "\n".join(participant.banner_lines(assembled)),
            participant._result_line(assembled, terminal, None),
            repr(config),
        ):
            assert secret not in text
        assert participant.mask_participant("p123456789") == "p123"

    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            participant.main(["--help"])
        assert excinfo.value.code == 0
        assert "--token-file" in capsys.readouterr().out

    async def test_identity_announcement_prints_masked_prefix(self, capsys):
        import asyncio

        class _Probe:
            def __init__(self):
                self._pid = None

            @property
            def participant_id(self):
                return self._pid

        probe = _Probe()
        stop = asyncio.Event()
        task = asyncio.ensure_future(participant._announce_identity(probe, stop))
        await asyncio.sleep(0.06)
        probe._pid = "p1234567890abcdef"
        await asyncio.sleep(0.1)
        stop.set()
        await task
        assert "p123*" in capsys.readouterr().out


class TestRoomTokenFile:
    def test_identity_token_file_resolved_and_masked(self, tmp_path):
        token_file = tmp_path / "slot-a-token.txt"
        token_file.write_text("room-file-token-A-0123456789abcdef\n", encoding="utf-8")
        identities = [
            {"slot": "A", "token_file": str(token_file)},
            {"slot": "B", "token": SECRET_B},
            {"slot": "C", "token": SECRET_C},
            {"slot": "D", "token": SECRET_D},
        ]
        room_config = room.load_room_config(
            _write_room_json(tmp_path, _room_config(identities=identities))
        )
        identity_a = room_config.identities[0]
        assert identity_a.token == "room-file-token-A-0123456789abcdef"
        assert identity_a.token_source == "file:" + str(token_file)
        assert "room-file-token-A" not in repr(identity_a)

    def test_identity_must_provide_exactly_one_token_source(self, tmp_path):
        identities = [
            {"slot": "A", "token": SECRET_A, "token_env": "HM_ROOM_A"},
            {"slot": "B", "token": SECRET_B},
            {"slot": "C", "token": SECRET_C},
            {"slot": "D", "token": SECRET_D},
        ]
        with pytest.raises(ValueError, match="只能提供一个"):
            room.load_room_config(_write_room_json(tmp_path, _room_config(identities=identities)))


if __name__ == "__main__":
    pytest.main([__file__])


@pytest.mark.parametrize('candidate', ['weighted_heuristic_v1', 'weighted_heuristic_v2', 'weighted_heuristic_v2_white_guard', 'v2_hu_upgrade_v1', 'catch_play_probe'])
def test_room_can_mix_v1_with_default_v0(tmp_path, candidate):
    """身份覆盖透传 V1，其余身份继续继承 V0；Token 和审计目录保持隔离。"""
    data = _room_config()
    data['identities'][0]['strategy'] = candidate
    cfg = room.load_room_config(_write_config(tmp_path,data),environ={'HM_ROOM_A':SECRET_A,'HM_ROOM_B':SECRET_B})
    children = [room.child_config_mapping(cfg, identity) for identity in cfg.identities]
    assert [c['strategy'] for c in children] == [candidate] + ['weighted_heuristic']*3
    assert len({c['audit_root'] for c in children}) == 4
    assert all('token' not in c for c in children)
    assert all(secret not in json.dumps(children) for secret in (SECRET_A,SECRET_B,SECRET_C,SECRET_D))
    for child in children:
        # 派生配置还必须通过真正的组合根公开校验，防止两个白名单脱节。
        assert participant.runtime_config_from_mapping(child,environ={room.TOKEN_ENV_VAR:SECRET_A}).strategy == child['strategy']


def test_room_v1_default_can_override_one_identity_back_to_v0(tmp_path):
    data = _room_config(strategy='weighted_heuristic_v1')
    data['identities'][1]['strategy'] = 'weighted_heuristic'
    cfg = room.load_room_config(_write_config(tmp_path,data),environ={'HM_ROOM_A':SECRET_A,'HM_ROOM_B':SECRET_B})
    assert [room.child_config_mapping(cfg,i)['strategy'] for i in cfg.identities] == [
        'weighted_heuristic_v1','weighted_heuristic','weighted_heuristic_v1','weighted_heuristic_v1',
    ]


@pytest.mark.parametrize('strategy', ['typo',None,True,42])
def test_room_rejects_bad_identity_strategy_before_launch(tmp_path,strategy):
    data = _room_config()
    data['identities'][0]['strategy'] = strategy
    with pytest.raises(ValueError,match='策略'):
        room.load_room_config(_write_config(tmp_path,data),environ={'HM_ROOM_A':SECRET_A,'HM_ROOM_B':SECRET_B})


def _available_strategies() -> tuple:
    """组合根声明的全部可配置策略名；启动器白名单的唯一真源。"""
    from hangma_bot.bootstrap import AVAILABLE_STRATEGIES
    return AVAILABLE_STRATEGIES


@pytest.mark.parametrize('strategy', _available_strategies())
def test_room_launcher_accepts_every_available_strategy(tmp_path, strategy):
    """启动器白名单必须覆盖组合根的全部可用策略。

    2026-09-14 序列策略网络候选接入后，本启动器仍保留一份手写策略名副本，
    于是出现「组合根已支持、启动器报未知策略名并在起子进程前拒绝」的静默
    脱节。此用例把两份清单不脱节固化成契约：组合根新增策略时自动覆盖。
    """
    data = _room_config(strategy=strategy)
    if strategy == 'r18_integrated_positive_v1':
        # R18 冻结包绑定当前已适配的官方指南 v34；通用启动器夹具仍保留
        # 较早版本以覆盖普通策略，因此这里只提升该发布包所需的版本声明。
        data['known_guide_version'] = 34
        data['expected_policy_release_id'] = (
            room.R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID
        )
    cfg = room.load_room_config(
        _write_config(tmp_path, data), environ={'HM_ROOM_A': SECRET_A, 'HM_ROOM_B': SECRET_B}
    )
    assert cfg.strategy == strategy
    children = [room.child_config_mapping(cfg, identity) for identity in cfg.identities]
    assert all(child['strategy'] == strategy for child in children)
    for child in children:
        # 派生配置必须同时通过组合根公开校验，证明两份清单真正一致。
        assert participant.runtime_config_from_mapping(
            child, environ={room.TOKEN_ENV_VAR: SECRET_A}
        ).strategy == strategy


def test_room_r18_release_binding_is_required_and_reaches_every_child(tmp_path):
    data = _room_config(
        strategy='r18_integrated_positive_v1',
        known_guide_version=34,
        expected_policy_release_id=room.R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
    )
    cfg = room.load_room_config(
        _write_config(tmp_path, data),
        environ={'HM_ROOM_A': SECRET_A, 'HM_ROOM_B': SECRET_B},
    )
    children = [room.child_config_mapping(cfg, identity) for identity in cfg.identities]
    assert all(
        child['expected_policy_release_id']
        == room.R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID
        for child in children
    )

    for bad in (None, '0' * 64):
        broken = dict(data)
        if bad is None:
            broken.pop('expected_policy_release_id')
        else:
            broken['expected_policy_release_id'] = bad
        with pytest.raises(ValueError, match='发布包'):
            room.load_room_config(
                _write_config(tmp_path, broken),
                environ={'HM_ROOM_A': SECRET_A, 'HM_ROOM_B': SECRET_B},
            )


def test_room_passes_sequence_model_dir_to_every_child(tmp_path):
    """模型类策略的部署包根目录必须透传到每个身份子进程。

    组合根用 sequence_model_dir 定位权重；不透传时子进程会静默回退到仓库内
    预置目录——测试房读不到外部部署包却不报错，属于难以察觉的实验偏差。
    """
    model_dir = str(tmp_path / "models")
    data = _room_config(strategy='sequence_model_4096_projected_v1', sequence_model_dir=model_dir)
    cfg = room.load_room_config(
        _write_config(tmp_path, data), environ={'HM_ROOM_A': SECRET_A, 'HM_ROOM_B': SECRET_B}
    )
    assert cfg.sequence_model_dir == model_dir
    children = [room.child_config_mapping(cfg, identity) for identity in cfg.identities]
    assert all(child['sequence_model_dir'] == model_dir for child in children)
    for child in children:
        assert participant.runtime_config_from_mapping(
            child, environ={room.TOKEN_ENV_VAR: SECRET_A}
        ).sequence_model_dir == Path(model_dir)


def test_room_omits_sequence_model_dir_when_unset(tmp_path):
    """未配置时不写派生字段，保持「缺省取仓库内预置目录」的原语义。"""
    data = _room_config()
    cfg = room.load_room_config(
        _write_config(tmp_path, data), environ={'HM_ROOM_A': SECRET_A, 'HM_ROOM_B': SECRET_B}
    )
    assert cfg.sequence_model_dir is None
    assert all(
        'sequence_model_dir' not in room.child_config_mapping(cfg, identity)
        for identity in cfg.identities
    )
