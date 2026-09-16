"""3.6d 运行级规则事实读取：``you_cai_bi_kao`` 的记录路径、未知语义与读取链路。

覆盖三件事：
1. **在场/缺场语义**：真实形态（RUN_MANIFEST 信封）读出布尔值；旧形态缺键 ⇒ None
   （未知 ≠ False，**不许用默认 false 冒充已接线**）；损坏/非布尔 ⇒ None + 原因；
2. **读取链路**：从运行清单读到的值注入评分上下文后，``EvaluationContext.you_cai_bi_kao``
   确实是该值——真实语料里没有 ``true`` 样本（已实测 100 份清单全为 False），
   因此本文件用**构造样本**证明 true 侧可读，并注明它不是真实对局；
3. **连接口径**：决策记录按 ``run_id`` 连接运行清单；清单不在场时明确写"未留存"。
"""

from __future__ import annotations

import json

from hangma_bot.adapters.recording.run_facts import (
    manifest_path,
    read_facts_for_run,
    read_run_facts,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import RulePublicState
from hangma_bot.policy.evaluation_v1 import build_context

from .support import WEALTH_CODE, make_observation


def _write_manifest(tmp_path, payload: dict):
    """写一份与记录器同形态的运行清单（``{"payload": {...}}``）。"""

    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "kind": "run_manifest",
                                "payload": payload}, ensure_ascii=False), encoding="utf-8")
    return path


def test_reads_switch_from_real_manifest_shape(tmp_path) -> None:
    """真实形态：清单在场且键为布尔值 ⇒ 读到位（False 是**已知值**，不是未知）。"""

    path = _write_manifest(tmp_path, {
        "you_cai_bi_kao": False, "ruleset_version": "hangma-mvp-v10-public-counts",
        "base_score": 1, "max_games": 10, "rounds_per_game": 8,
    })
    facts = read_run_facts(path)
    assert facts.you_cai_bi_kao is False
    assert facts.known is True
    assert facts.ruleset_version == "hangma-mvp-v10-public-counts"
    assert facts.base_score == 1
    assert facts.reason is None


def test_legacy_manifest_without_switch_is_unknown_not_false(tmp_path) -> None:
    """旧形态清单缺键 ⇒ None + 原因；**不得**读成 False。"""

    path = _write_manifest(tmp_path, {"ruleset_version": "hangma-mvp-v9"})
    facts = read_run_facts(path)
    assert facts.you_cai_bi_kao is None
    assert facts.known is False
    assert facts.reason and "you_cai_bi_kao" in facts.reason


def test_non_boolean_switch_is_refused(tmp_path) -> None:
    """键在场但类型不对 ⇒ None + 原因（不猜、不强制转换）。"""

    path = _write_manifest(tmp_path, {"you_cai_bi_kao": "true"})
    facts = read_run_facts(path)
    assert facts.you_cai_bi_kao is None
    assert facts.reason and "布尔值" in facts.reason


def test_missing_or_corrupt_manifest_never_raises(tmp_path) -> None:
    """文件不在场、内容损坏：都返回未知事实（审计/离线路径不得被抛异常打断）。"""

    absent = read_facts_for_run(tmp_path, "run-absent")
    assert absent.you_cai_bi_kao is None
    assert "不在场" in (absent.reason or "")

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    facts = read_run_facts(broken)
    assert facts.you_cai_bi_kao is None
    assert facts.reason and "不可读" in facts.reason


def test_manifest_path_is_the_recorded_location(tmp_path) -> None:
    """连接口径：``<audit_root>/runs/<run_id>/manifest.json``。"""

    assert manifest_path(tmp_path, "run-9") == tmp_path / "runs" / "run-9" / "manifest.json"


def test_switch_reaches_the_scoring_context_when_injected(tmp_path) -> None:
    """读取链路：清单里的值注入 ``build_context`` 后确实到达评分上下文。

    **构造样本**：真实语料实测 100 份运行清单全部为 ``False``、没有任何 ``true`` 房，
    因此这里手写一份 ``true`` 清单证明**可读性**——它**不是**真实对局记录。
    """

    path = _write_manifest(tmp_path, {"you_cai_bi_kao": True})
    facts = read_run_facts(path)
    assert facts.you_cai_bi_kao is True

    observation = make_observation(
        rule_state=RulePublicState(
            wealth_god=Tile(WEALTH_CODE), baotou=False, chain_count=0, catch_play=False
        ),
    )
    ctx = build_context(observation, you_cai_bi_kao=facts.you_cai_bi_kao)
    assert ctx.you_cai_bi_kao is True

    # 未注入 / 记录缺失时保持未知，不得落到 False。
    unknown = build_context(observation)
    assert unknown.you_cai_bi_kao is None
    assert build_context(observation, you_cai_bi_kao=read_run_facts(
        tmp_path / "absent.json").you_cai_bi_kao).you_cai_bi_kao is None
