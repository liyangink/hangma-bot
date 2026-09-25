"""新战役提升后的官方牌谱应保留四席身份归因。"""

import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _build_module():
    spec = importlib.util.spec_from_file_location("datamart_build", ROOT / "datamart" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_game_seats_reads_promoted_campaign_official_archive(tmp_path, monkeypatch):
    build = _build_module()
    monkeypatch.setattr(build, "REPO_ROOT", tmp_path)
    events = (tmp_path / "datasets" / "derived" / "campaign" / "official"
              / "t_demo" / "official" / "dl-001" / "events.json")
    events.parent.mkdir(parents=True)
    events.write_text(json.dumps({
        "game_id": "t_demo_r1_b0_t0",
        "seats": [{"user_id": "u_a", "name": "青龙"}, {"user_id": "u_b", "name": "白虎"},
                  {"user_id": "u_c", "name": "朱雀"}, {"user_id": "u_d", "name": "玄武"}],
    }, ensure_ascii=False), encoding="utf-8")

    seats = build.load_game_seats()
    assert [seats["t_demo_r1_b0_t0"]["seats"][seat]["user_id"] for seat in range(4)] == [
        "u_a", "u_b", "u_c", "u_d",
    ]


def test_late_official_identity_backfills_only_unattributed_seat():
    build = _build_module()
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE fact_hand_seat (hand_key TEXT, seat INTEGER, "
                "participant_key TEXT, strategy_key TEXT, is_self INTEGER)")
    con.executemany("INSERT INTO fact_hand_seat VALUES (?,?,?,?,?)", [
        ("hand", 0, None, "unknown", 0),
        ("hand", 1, "u_existing", "weighted_heuristic_v2", 1),
    ])
    build._backfill_unattributed_seats(con, [
        {"hand_key": "hand", "seat": 0, "participant_key": "u_new",
         "strategy_key": "r18_integrated_positive_v2", "is_self": 1},
        {"hand_key": "hand", "seat": 1, "participant_key": "u_other",
         "strategy_key": "r18_integrated_positive_v2", "is_self": 1},
    ])
    assert con.execute("SELECT seat,participant_key,strategy_key,is_self FROM fact_hand_seat "
                       "ORDER BY seat").fetchall() == [
        (0, "u_new", "r18_integrated_positive_v2", 1),
        (1, "u_existing", "weighted_heuristic_v2", 1),
    ]
