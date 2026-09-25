"""钉死四臂配对研究的可配置臂接口：注册臂路径不得变化、研究候选臂可装载。

为什么单独测这几条纯函数：`paired_study.py` 的臂名同时参与**文件名**与**清单身份**。
2026-09-25 为跑消融实验把臂改成可配置时，风险有两个——一是给注册臂改名会让历史批次
的阶段文件路径漂移、无法续跑；二是研究候选臂名含路径分隔符，直接拼文件名会把阶段
文件写进嵌套子目录。这里把两条都钉死。

本测试只导入模块与调用纯函数，不跑任何完整桌。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "review/r18-four-arm-evaluation-2026-09-23/paired_study.py"
CANDIDATE = ROOT / ("review/wiring-queue-rootcause-2026-09-25/"
                    "candidates/OPTY-R18-C03-RIVER0.py")
CANDIDATE_ARM = "candidate@review/wiring-queue-rootcause-2026-09-25/candidates/OPTY-R18-C03-RIVER0.py"


def _load():
    for entry in (ROOT / "src", ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    spec = importlib.util.spec_from_file_location("paired_study", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["paired_study"] = module
    spec.loader.exec_module(module)
    return module


study = _load()


def test_registered_arm_names_are_never_rewritten():
    """注册臂必须原样进文件名：改名会让历史批次的阶段路径漂移。"""

    for arm in study.ARMS:
        assert study.safe_arm_name(arm) == arm


def test_candidate_arm_name_loses_path_separators():
    safe = study.safe_arm_name(CANDIDATE_ARM)
    assert "/" not in safe and "\\" not in safe
    assert safe.startswith("candidate@review_wiring-queue-rootcause")
    assert safe.endswith("OPTY-R18-C03-RIVER0.py")


def test_unit_path_is_flat_for_candidate_arms(tmp_path):
    unit = ("H", 1, 0, CANDIDATE_ARM, 2026102501)
    path = study.unit_path(tmp_path, unit)
    assert path.parent == tmp_path / "stages", "阶段文件必须直接落在 stages 下，不再嵌套子目录"
    assert path.name.count(".") >= 1 and path.name.endswith(".json")


def test_unit_path_matches_history_for_registered_arms(tmp_path):
    unit = ("M", 3, 2, "r18_v2", 2026102501)
    assert study.unit_path(tmp_path, unit).name == "M-r0003-s2-r18_v2.json"


def test_default_arms_are_unchanged():
    assert study.parse_arms(None) == study.ARMS
    assert study.parse_arms(None) == ("weighted_heuristic_v2", "v2_hu_upgrade_v1",
                                      "r18_v1", "r18_v2")


def test_custom_arms_accept_registered_and_candidate(tmp_path):
    assert CANDIDATE.is_file(), "消融候选应已由 make_p3a_candidate.py 生成"
    arms = study.parse_arms("r18_v2," + CANDIDATE_ARM)
    assert arms == ("r18_v2", CANDIDATE_ARM)


@pytest.mark.parametrize("spec", [
    "r18_v2",                      # 只有一个臂
    "r18_v2,r18_v2",               # 重复
    "r18_v2,not_a_registered_arm",  # 未知注册臂
    "r18_v2,candidate@review/does/not/exist.py",  # 候选文件不存在
])
def test_bad_arm_specs_are_rejected(spec):
    with pytest.raises(SystemExit):
        study.parse_arms(spec)


def test_candidate_sources_records_only_candidate_arms():
    assert study.candidate_sources(("r18_v2", "r18_v1")) == {}
    sources = study.candidate_sources(("r18_v2", CANDIDATE_ARM))
    assert list(sources) == [CANDIDATE_ARM]
    import hashlib
    assert sources[CANDIDATE_ARM] == hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()
