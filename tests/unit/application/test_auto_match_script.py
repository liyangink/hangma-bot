"""run_auto_match.py 入口行为测试：配置解析/校验、退出码与装配指引。

脚本只解析配置并调用组合根（scripts/AGENTS.md）；本测试不建立任何网络
连接：装配入口用 stub 注入，校验失败路径只到退出码为止。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict

import pytest

from hangma_bot.application.contracts import (
    ParticipantTerminal,
    ParticipantTerminalReason,
)

SCRIPT_PATH = Path(__file__).resolve().parents[2] / ".." / "scripts" / "run_auto_match.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_auto_match_test_module", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_auto_match = _load_script_module()


def _base_config(**overrides) -> Dict:
    doc: Dict = {
        "mode": "auto_match",
        "base_url": "https://10.240.169.190:18080",
        "known_guide_version": 15,
        "token_kind": "official",
        "token_env": "HM_AUTO_MATCH_TOKEN",
        "audit_root": "runs",
        "strategy": "weighted_heuristic",
        "insecure_hosts": ["10.240.169.190"],
        "sse_enabled": True,
        "source_namespace": "hangma-official",
        "auto_match": {
            "declared_max_games": 10,
            "declared_rounds": 8,
            "drain_grace_seconds": 45.0,
        },
    }
    doc.update(overrides)
    return doc


def _write_config(tmp_path: Path, doc: Dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_load_config_auto_match_minimal(tmp_path) -> None:
    """auto_match 配置解析：空目标（null=尚未发现）、声明上限与源命名空间。"""

    path = _write_config(tmp_path, _base_config())
    config, settings = run_auto_match.load_config(
        path, environ={"HM_AUTO_MATCH_TOKEN": "tok-minimal"}
    )
    assert config.mode.value == "auto_match"
    assert config.expected_tournament_id == ""  # 空目标：match 发现
    assert config.token_kind.value == "official"
    assert settings.source_namespace == "hangma-official"
    assert settings.declared_max_games == 10
    assert settings.declared_rounds == 8
    assert settings.drain_grace_seconds == 45.0


def test_load_config_resume_room_and_defaults(tmp_path) -> None:
    """非空 expected_tournament_id = 恢复已知自动房；auto_match 可缺省。"""

    doc = _base_config(expected_tournament_id="r_auto_known", auto_match={})
    path = _write_config(tmp_path, doc)
    config, settings = run_auto_match.load_config(
        path, environ={"HM_AUTO_MATCH_TOKEN": "tok-2"}
    )
    assert config.expected_tournament_id == "r_auto_known"
    assert settings.declared_max_games == 0  # 缺省 = 不声明
    assert settings.declared_rounds == 0
    assert settings.match_min_interval_sec == run_auto_match.AutoMatchSettings().match_min_interval_sec


def test_load_config_rejects_unknown_keys_and_bad_auto(tmp_path) -> None:
    """未知键与 auto_match 非法字段在组装前拒绝（配置即安全边界）。"""

    with pytest.raises(ValueError):
        run_auto_match.load_config(
            _write_config(tmp_path, _base_config(bogus_key=1)),
            environ={"HM_AUTO_MATCH_TOKEN": "t"},
        )
    with pytest.raises(ValueError):
        bad_auto = _base_config()
        bad_auto["auto_match"] = {"not_a_field": 1}
        run_auto_match.load_config(
            _write_config(tmp_path, bad_auto), environ={"HM_AUTO_MATCH_TOKEN": "t"}
        )
    with pytest.raises(ValueError):
        no_ns = _base_config()
        del no_ns["source_namespace"]
        run_auto_match.load_config(
            _write_config(tmp_path, no_ns), environ={"HM_AUTO_MATCH_TOKEN": "t"}
        )


def test_load_config_token_file_single_line_only(tmp_path) -> None:
    """--token-file 单行约定：多行文件拒绝，单行注入不进入任何输出面。"""

    doc = _base_config()
    del doc["token_env"]
    token_file = tmp_path / "token.txt"
    token_file.write_text("multi\nline-token\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run_auto_match.load_config(_write_config(tmp_path, doc), token_file=str(token_file))
    token_file.write_text("single-token-line\n", encoding="utf-8")
    config, _ = run_auto_match.load_config(
        _write_config(tmp_path, doc), token_file=str(token_file)
    )
    assert config.token == "single-token-line"
    assert "single-token-line" not in repr(config)


def test_load_config_rejects_wrong_mode(tmp_path) -> None:
    """非 auto_match 模式配置被本入口拒绝（防止误用正式/测试模式）。"""

    doc = _base_config(mode="official_tournament", expected_tournament_id="t_x")
    with pytest.raises(ValueError):
        run_auto_match.load_config(
            _write_config(tmp_path, doc), environ={"HM_AUTO_MATCH_TOKEN": "t"}
        )


def test_build_composed_pre_integration_hint(tmp_path, monkeypatch, capsys) -> None:
    """组合根集成前：明确指引主审差异，退出码 2（不崩溃、不联网）。"""

    monkeypatch.setattr(run_auto_match.bootstrap_module, "build_auto_match_runtime", None, raising=False)
    doc = _base_config()
    del doc["token_env"]
    doc["token"] = "tok-pre-integration"
    path = _write_config(tmp_path, doc)
    code = run_auto_match.main(["--config", str(path)])
    assert code == run_auto_match.EXIT_USAGE
    assert "build_auto_match_runtime" in capsys.readouterr().err


def test_main_with_stub_composition_reports_capacity_exit(
    tmp_path, monkeypatch, capsys
) -> None:
    """stub 装配端到端：RESULT 行含终态 reason，capacity_limit 退出码 10。"""

    terminal = ParticipantTerminal(
        reason=ParticipantTerminalReason.CAPACITY_LIMIT,
        last_snapshot=None,
        detail="MATCH_LIMIT_REACHED：达到同时 16 场上限（测试桩）",
    )

    class StubAssembled:
        def __init__(self, config, settings) -> None:
            self.config = config
            self.settings = settings
            self.run_id = "run-stub"
            self.sink = SimpleNamespace(run_dir=Path("runs/run-stub"))
            self.participant_id = "u_auto_player_1"
            self.audit_degraded = False
            self.last_audit_summary = None

        async def run(self):
            return terminal

    doc = _base_config()
    del doc["token_env"]
    doc["token"] = "tok-stub"
    path = _write_config(tmp_path, doc)
    config, settings = run_auto_match.load_config(path)
    monkeypatch.setattr(
        run_auto_match.bootstrap_module,
        "build_auto_match_runtime",
        lambda cfg, st: StubAssembled(cfg, st),
        raising=False,
    )
    code = run_auto_match.main(["--config", str(path)])
    assert code == run_auto_match.EXIT_PERMANENT
    captured = capsys.readouterr()
    last_line = captured.out.strip().splitlines()[-1]
    assert last_line.startswith(run_auto_match.RESULT_PREFIX)
    result = json.loads(last_line[len(run_auto_match.RESULT_PREFIX):])
    assert result["terminal_reason"] == "capacity_limit"
    assert result["run_id"] == "run-stub"
    assert result["participant_id_prefix"] == "u_au"
    assert "tok-stub" not in captured.out  # Token 绝不进入输出


def test_terminal_exit_code_mapping() -> None:
    """自动匹配新增终态（matching_unavailable/capacity_limit）映射到 10。"""

    for reason in (
        ParticipantTerminalReason.MATCHING_UNAVAILABLE,
        ParticipantTerminalReason.CAPACITY_LIMIT,
    ):
        terminal = ParticipantTerminal(reason=reason, last_snapshot=None, detail="d")
        assert run_auto_match.terminal_exit_code(terminal, None) == run_auto_match.EXIT_PERMANENT
    normal = ParticipantTerminal(
        reason=ParticipantTerminalReason.TOURNAMENT_FINISHED, last_snapshot=None, detail="d"
    )
    assert run_auto_match.terminal_exit_code(normal, None) == run_auto_match.EXIT_COMPLETED
    assert run_auto_match.terminal_exit_code(None, 2) == run_auto_match.EXIT_SIGINT
