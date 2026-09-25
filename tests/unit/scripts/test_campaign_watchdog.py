"""通过模块级函数验证对比战役 watchdog 的纯逻辑：配置形状、会话防重、提升分片、降级统计。

这些步骤本身要连官方平台，不能进单元测试；但真正会出错的判断都在纯函数里——
配置文件形状、把新批次打进旧会话、数据池分片的落盘结构、降级率的口径。这里逐个钉死，
跑不依赖网络与数据库。
"""

import gzip
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load():
    spec = importlib.util.spec_from_file_location(
        "campaign_watchdog", ROOT / "scripts" / "test_room_campaign_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["campaign_watchdog"] = module
    spec.loader.exec_module(module)
    return module


watchdog = _load()

SLOTS = ("qinglong", "baihu", "zhuque", "xuanwu")


def _campaign():
    return {
        "room_id": "t_demo00000001",
        "base_url": watchdog.BASE_URL,
        "known_guide_version": 30,
        "m": 10,
        "rounds": 16,
        "pool": "demo-pool",
        "arms": dict(zip(SLOTS, ("v2_hu_upgrade_v1", "sequence_model_2048_projected_v1",
                                 "sequence_model_4096_direct_v1", "sequence_model_4096_projected_v1"))),
        "identities": {},
    }


def test_runtime_config_is_one_identity_per_slot_with_its_own_strategy(tmp_path):
    campaign = _campaign()
    config, session = watchdog._runtime_config(tmp_path / "demo-campaign", 3, campaign)

    assert config["mode"] == "test_room"
    assert config["expected_tournament_id"] == campaign["room_id"]
    assert [item["slot"] for item in config["identities"]] == list(SLOTS)
    for item in config["identities"]:
        assert item["strategy"] == campaign["arms"][item["slot"]]
        assert item["token_file"].endswith(item["slot"] + ".token")
    assert session == watchdog.REPO_ROOT / "artifacts" / "sessions" / "demo-campaign-r3"
    assert config["audit_root"] == str(session / "audit")
    assert config["restart"]["max_restarts"] == 2
    assert config["sse_enabled"] is False
    assert config["discard_pacing_enabled"] is True


def test_runtime_config_uses_campaign_sse_for_every_arm(tmp_path):
    campaign = _campaign()
    campaign["sse_enabled"] = True
    campaign["discard_pacing_enabled"] = False
    config, _ = watchdog._runtime_config(tmp_path / "sse-campaign", 1, campaign)
    assert config["sse_enabled"] is True
    assert config["discard_pacing_enabled"] is False
    assert config["ordinary_long_poll_min_interval_ms"] == 0
    assert watchdog.build_arg_parser().parse_args([
        "open", "--campaign", "sse-campaign", "--sse-enabled",
    ]).sse_enabled is True
    assert watchdog.build_arg_parser().parse_args([
        "open", "--campaign", "sse-campaign",
    ]).sse_enabled is True
    assert watchdog.build_arg_parser().parse_args([
        "open", "--campaign", "sse-campaign", "--no-sse",
    ]).sse_enabled is False


def test_r18_runtime_config_binds_each_approved_release(tmp_path):
    """正式测试房入口不得因战役脚本漏传发布包摘要而拒绝候选启动。"""
    campaign = _campaign()
    campaign["arms"]["zhuque"] = "r18_integrated_positive_v1"
    campaign["arms"]["xuanwu"] = "r18_integrated_positive_v2"
    config, _ = watchdog._runtime_config(tmp_path / "r18-campaign", 1, campaign)
    identities = {item["slot"]: item for item in config["identities"]}
    assert "expected_policy_release_id" not in identities["qinglong"]
    assert identities["zhuque"]["expected_policy_release_id"] == watchdog._release_id_for_strategy(
        "r18_integrated_positive_v1")
    assert identities["xuanwu"]["expected_policy_release_id"] == watchdog._release_id_for_strategy(
        "r18_integrated_positive_v2")


def test_register_identities_is_idempotent_and_keeps_file_layout(tmp_path, monkeypatch):
    path = tmp_path / "strategy-map.json"
    path.write_text(json.dumps({
        "schema": "hangma-strategy-map-v1",
        "identities": {"u_old": "weighted_heuristic_v2"},
        "pools": {"demo-pool": "weighted_heuristic_v2"},
    }, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    monkeypatch.setattr(watchdog, "STRATEGY_MAP", path)
    before_lines = path.read_text(encoding="utf-8").count(chr(10))
    campaign = _campaign()
    campaign["identities"] = {"qinglong": "u_a", "baihu": "u_b", "zhuque": "u_c", "xuanwu": "u_d"}

    changed = watchdog._register_identities(campaign)
    assert sorted(user for user, _ in changed) == ["u_a", "u_b", "u_c", "u_d"]
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["identities"]["u_a"] == "v2_hu_upgrade_v1"
    assert written["identities"]["u_d"] == "sequence_model_4096_projected_v1"
    assert written["pools"] == {"demo-pool": "weighted_heuristic_v2"}  # 其它块不动
    assert path.read_text(encoding="utf-8").count(chr(10)) == before_lines + 4  # 只多出四行

    assert watchdog._register_identities(campaign) == []  # 幂等


def test_guard_refuses_to_launch_into_a_session_that_already_has_runs(tmp_path):
    session = tmp_path / "session"
    assert watchdog._existing_runs(session) == []
    assert watchdog._guard_fresh_session(session, 1, force=False) == 0

    run = session / "audit" / "slot-qinglong" / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    assert watchdog._existing_runs(session) == [run]
    assert watchdog._guard_fresh_session(session, 1, force=False) == 2
    assert watchdog._guard_fresh_session(session, 1, force=True) == 0


def _fake_postgame(tmp_path, rows, runs, tag="1"):
    job = tmp_path / ("job-" + tag)
    dataset = job / "derived" / ("dataset-" + tag)
    dataset.mkdir(parents=True, exist_ok=True)
    dataset.joinpath("hands.jsonl").write_text(
        "".join(json.dumps({"hand_id": "hand-%d" % index}) + chr(10) for index in range(rows)),
        encoding="utf-8")
    dataset.joinpath("manifest.json").write_text(
        json.dumps({"config": {"analysis_ruleset_version": "hangma-mvp-v10-public-counts"}}),
        encoding="utf-8")
    job.joinpath("audit-validation.json").write_text(
        json.dumps({"run-%d" % index: {"audit_complete": True} for index in range(runs)}),
        encoding="utf-8")
    return job


def test_promote_writes_append_only_shard_and_merges_validations(tmp_path, monkeypatch):
    monkeypatch.setattr(watchdog, "REPO_ROOT", tmp_path)
    session = tmp_path / "session"
    download = session / "official" / "dl-abc"
    download.mkdir(parents=True)
    download.joinpath("events.json").write_text("{}", encoding="utf-8")

    campaign = _campaign()
    first = watchdog._promote(campaign, 1, session, _fake_postgame(tmp_path, 3, 2, "1"))
    assert first == {"hands_shard": "t_demo00000001-r1.hands.jsonl.gz", "hands_rows": 3, "runs_merged": 2}

    pool = tmp_path / "datasets" / "derived" / "demo-pool"
    with gzip.open(pool / "hands" / first["hands_shard"], "rt", encoding="utf-8") as handle:
        assert len([line for line in handle if line.strip()]) == 3
    manifest = json.loads((pool / "manifests" / "t_demo00000001.json").read_text(encoding="utf-8"))
    assert manifest["config"]["analysis_ruleset_version"] == "hangma-mvp-v10-public-counts"
    assert len(json.loads((pool / "validations" / "t_demo00000001.audit.json").read_text(encoding="utf-8"))) == 2
    assert sorted(path.name for path in (pool / "official" / "t_demo00000001" / "official").iterdir()) == ["dl-abc"]

    # 第二轮：分片按轮追加，验证按 run_id 合并而不是覆盖
    second = watchdog._promote(campaign, 2, session, _fake_postgame(tmp_path, 5, 4, "2"))
    assert second["hands_shard"] == "t_demo00000001-r2.hands.jsonl.gz"
    merged = json.loads((pool / "validations" / "t_demo00000001.audit.json").read_text(encoding="utf-8"))
    assert sorted(merged) == ["run-0", "run-1", "run-2", "run-3"]
    assert len(sorted((pool / "hands").glob("*.gz"))) == 2


def test_degradation_summary_counts_decisions_not_reasons(tmp_path):
    session = tmp_path / "session"
    decisions = session / "audit" / "slot-baihu" / "runs" / "run-1" / "participants" / "u_1"
    decisions.mkdir(parents=True)
    records = [
        {"kind": "decision_planned", "payload": {"candidates": [{"action_key": "pass"}],
         "degraded_reasons": ["sequence_model:incomplete_history", "保底策略：不运行任何增强评分"]}},
        {"kind": "decision_planned", "payload": {"candidates": [{"action_key": "pass"}],
         "degraded_reasons": []}},
    ]
    decisions.joinpath("decisions.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + chr(10) for record in records), encoding="utf-8")

    rows = watchdog._degradation_summary(session)
    assert len(rows) == 1
    assert rows[0]["slot"] == "baihu"
    assert rows[0]["plans"] == 2
    assert rows[0]["degraded"] == 1                 # 按「决策」计，不按原因条数计
    assert rows[0]["degraded_rate"] == 50.0         # 两条原因不能算成 100%
    assert rows[0]["reasons"]["sequence_model"] == 1


def test_degradation_summary_does_not_count_successful_action_value_as_fallback(tmp_path):
    """实网 R18 成功评分会在说明字段留下“评分完成”，不能算回退。"""
    session = tmp_path / "session"
    decisions = session / "audit" / "slot-qinglong" / "runs" / "run-1" / "participants" / "u_1"
    decisions.mkdir(parents=True)
    records = [
        {"kind": "decision_planned", "payload": {"candidates": [{"action_key": "discard:1w"}],
         "degraded_reasons": ["action_value: r18_integrated_positive_v2 评分完成"]}},
        {"kind": "decision_planned", "payload": {"candidates": [{"action_key": "pass"}],
         "degraded_reasons": ["action_value: scorer 执行异常",
                              "action_value_failed: 降级为紧急候选 + 规则合法顺序，未拼 V2 分数"]}},
    ]
    decisions.joinpath("decisions.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")

    rows = watchdog._degradation_summary(session)
    assert rows[0]["plans"] == 2
    assert rows[0]["degraded"] == 1
    assert rows[0]["degraded_rate"] == 50.0
    assert rows[0]["reasons"] == {"action_value_failed": 1}
