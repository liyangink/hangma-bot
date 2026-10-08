"""只读核验 T54 已保存的完整输入、评分、来源封条和源码补丁。

不导入业务模块、不重新评分或推进世界。首次 --write-receipt 只生成本目录
独立读回收据；以后只比较原收据。换机器按 review 后缀定位冻结原件，
T49 大原件须先按其归档指南恢复，不能跳过缺失的输入来源。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen_file_here(recorded_path):
    """原绝对路径是证据标签；只映射本仓 review 内原件，不读取外部路径。"""
    parts = Path(recorded_path).parts
    suffix = Path(*parts[parts.index("review"):])
    assert ".." not in suffix.parts
    return _project_file(_PROJECT_ROOT, REPO / suffix)


def normalized_scores(value):
    if type(value) is list:
        assert len({entry["action_key"] for entry in value}) == len(value)
        return {entry["action_key"]: {"score": entry["score"], "trace": entry["trace"]}
                for entry in value}
    assert type(value) is dict
    return value


def audit():
    """返回有限范围读回事实；完整等价来源仍是原真实执行及定向代码证明。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "SCORING-PLAN.json")).read_text())
    source_plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "PLAN.json")).read_text())
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / "SCORING-CLOSURE.json")).read_text())
    docs = json.loads((_project_file(_PROJECT_ROOT, HERE / "TEST-AND-DOCS-PROPOSAL.json")).read_text())
    public = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / "PUBLIC-PROBE-CLOSURE.json")).read_text())
    natural = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / "RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json")).read_text())
    assert public["complete_all_windows"] and natural["complete"] and closure["complete"]
    assert closure["source_identity_stable"] and closure["full_DTO_scores_traces_operations_equal"]
    assert closure["runtime_identity"] == plan["candidate_runtime_identity"]
    assert closure["reference_identity"] == plan["reference_runtime_identity"] == natural["candidate_identity"]
    current, reference = closure["runtime_identity"], closure["reference_identity"]
    assert current["candidate_id"] != reference["candidate_id"]
    assert current["params"] == reference["params"] and current["math_backend"] == reference["math_backend"]
    assert current["source_sha256"] == reference["source_sha256"] == plan["same_mathematical_source_sha256"]
    assert all(current["source_manifest"][name]["sha256"] == item["proposed_sha256"]
               for name, item in source_plan["files"].items())
    assert sha(_project_file(_PROJECT_ROOT, HERE / "SOURCE-PROPOSAL.patch")) == source_plan["source_patch_sha256"]
    assert sha(_project_file(_PROJECT_ROOT, HERE / "TEST-AND-DOCS-PROPOSAL.patch")) == docs["patch_sha256"]
    assert sha(_project_file(_PROJECT_ROOT, HERE / "edgecase-tests/test_public_count_result_scope.py")) == docs["files_sha256"]["tests/unit/hangma/test_public_count_result_scope.py"]
    for path, digest in plan["frozen_files"].items():
        assert sha(frozen_file_here(path)) == digest, path
    expected = {"public:" + str(index): row for index, row in enumerate(public["rows"])}
    expected.update({"natural:" + row["decision_id"]: row for row in natural["rows"]})
    assert len(expected) == 214 and len(public["rows"]) == 22 and len(natural["rows"]) == 192
    results = {row["label"]: row for row in closure["rows"]}
    assert len(results) == len(closure["rows"]) == 214 and set(results) == set(expected)
    seen = set()
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            label = item["label"]
            assert label not in seen
            seen.add(label)
            result, old, dto = results[label], expected[label], item["candidate_view"]
            assert result["status"] == "SCORED" and result["saved_before_score"]
            assert result["all_actual_input_scores_traces_operations_equal"]
            assert hashlib.sha256(canonical(dto)).hexdigest() == item["view_sha256"] == result["view_sha256"] == old["view_sha256"]
            assert canonical(normalized_scores(result["scores"])) == canonical(normalized_scores(old["scores"]))
            assert result["operations"] == old["operations"]
            assert result["nodes"] == len(dto["nodes"])
            assert len({node["node_key"] for node in dto["nodes"]}) == len(dto["nodes"])
            assert len({root["action_key"] for root in dto["actions"]}) == len(dto["actions"])
            assert set(result["scores"]) == {root["action_key"] for root in dto["actions"]}
            assert dto["schema_version"] == current["view_schema_version"]
            assert dto["graph_schema_version"] == current["graph_schema_version"]
    assert seen == set(expected)
    assert closure["actual_score_pipelines"] == closure["actual_full_inputs_readback"] == len(seen)
    files = ["PLAN.json", "SCORING-PLAN.json", "SCORING-CLOSURE.json",
             "ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz", "SOURCE-PROPOSAL.patch",
             "TEST-AND-DOCS-PROPOSAL.patch", "TEST-AND-DOCS-PROPOSAL.json",
             "SMOKE-STARTUP-FAILURE.json", "SMOKE-RECOVERY.json", "ROOT-TEST-RECEIPT.json",
             "verify_worktree.py", "readback.py", "proof-review/REVIEW.md",
             "edgecase-tests/REVIEW.md", "edgecase-tests/EXECUTION.json",
             "edgecase-tests/test_public_count_result_scope.py", "edgecase-tests/PYTEST-RUN-1.log"]
    return {"schema": "t54-root-independent-readback/1", "complete": True,
            "actual_public_inputs_and_scores": 22, "actual_natural_inputs_and_scores": 192,
            "all_legal_roots_scores_traces_operations_equal": True,
            "candidate_id": current["candidate_id"], "reference_id": reference["candidate_id"],
            "full_archive_sha256": {name: sha(_project_file(_PROJECT_ROOT, HERE / name)) for name in files},
            "new_scores_worlds_tables_in_readback": 0,
            "scope": "frozen input and full score readback, not a new performance or strength test"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    result = audit()
    receipt = _project_file(_PROJECT_ROOT, HERE / "ROOT-READBACK.json")
    if args.write_receipt:
        with receipt.open("xb") as stream:
            stream.write(canonical(result) + b"\n")
    else:
        assert result == json.loads(receipt.read_text())
    print({"verified": True, "public": 22, "natural": 192, "new_scores_worlds_tables": 0})
