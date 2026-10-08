"""重签候选准入门禁记录（`evidence/2.3-gates/gates-*.json`）以匹配**当前候选绑定身份**。

背景（R9-FINAL-CLOSURE-2026-09-19 §1）：投影修复 `4d9f3c7b` 与 V2 参数批次改变了候选
绑定身份的源码依赖摘要 `src…` 段，已存准入记录的 `bound_identity` 与当前候选对不上，
于是 `step_admission` 报 `no_admission_record`（5 条测试失败的**具名原因**）。

纪律：
  * **不手改字段**：四道门禁（G-0/G-1/G-2/G-3）在**同一真实准入语料**上重跑；
  * 语料身份必须先核对与旧记录逐字一致（sha256/行数/字节数），否则拒绝重签；
  * 旧记录字节先归档到本目录 `gate-records/prior/`，改动可逐字节复核；
  * 重跑结果不如旧记录（例如由 PASS 变 FAIL）时**照实写"未通过"**，不放宽任何门槛。

用法：
    python resign_gate_records.py            # 只重跑到 staging，不落盘到既有 evidence
    python resign_gate_records.py --apply    # 全部成功且身份核对通过后原地重签
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
GATE_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates')
PRIOR_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/gate-records/prior')
STAGING = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/gate-records/reissued')
CORPUS = _project_file(_PROJECT_ROOT, REPO / "datasets" / "derived" / "auto-match-2026-09-06" / "decisions.jsonl")
REGISTRATIONS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates/candidate-registrations.json')

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))
_spec = importlib.util.spec_from_file_location("sitin_gates", _project_file(_PROJECT_ROOT, TOOLS / "sitin_gates.py"))
gates = importlib.util.module_from_spec(_spec)
sys.modules["sitin_gates"] = gates
_spec.loader.exec_module(gates)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="身份核对与四道门禁全部完成后，原地重签既有记录")
    args = parser.parse_args()
    PRIOR_DIR.mkdir(parents=True, exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)
    current_corpus_sha = sha256_file(CORPUS)
    rows = []
    ok_all = True
    for path in sorted(GATE_DIR.glob("gates-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        candidate = record["candidate"]
        weights = record.get("weights") or {}
        recorded_corpus = record.get("corpus") or {}
        prepared = gates.supervised_prepare(candidate, weights)
        row = {
            "record": path.name,
            "candidate": candidate,
            "weights": weights,
            "prior_sha256": sha256_file(path),
            "prior_bound_identity": record.get("bound_identity"),
            "current_bound_identity": prepared.get("bound_identity"),
            "prior_admitted": record.get("admitted"),
            "corpus_identity_matches": (recorded_corpus.get("sha256") == current_corpus_sha
                                        and recorded_corpus.get("path")
                                        == str(CORPUS.relative_to(REPO))),
        }
        # 旧记录字节归档（只在首次重签时留一份原始副本）。
        prior_copy = _project_file(_PROJECT_ROOT, PRIOR_DIR / path.name)
        if not prior_copy.exists():
            shutil.copyfile(path, prior_copy)
        if not row["corpus_identity_matches"]:
            row["status"] = "REFUSED_CORPUS_MISMATCH"
            ok_all = False
            rows.append(row)
            continue
        if row["prior_bound_identity"] == row["current_bound_identity"]:
            row["status"] = "ALREADY_CURRENT"
            rows.append(row)
            continue
        report = gates.run_all(candidate, weights, CORPUS,
                               json.loads(REGISTRATIONS.read_text(encoding="utf-8")),
                               evidence_kind="admission")
        (_project_file(_PROJECT_ROOT, STAGING / path.name)).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        row.update({
            "status": "REISSUED",
            "new_bound_identity": report.get("bound_identity"),
            "new_admitted": report.get("admitted"),
            "new_all_pass": report.get("all_pass"),
            "new_failed": report.get("failed"),
            "new_insufficient": report.get("insufficient"),
            "identity_ok": report.get("bound_identity") == prepared.get("bound_identity"),
            "gates": [{"gate": g["gate"], "status": g["status"]}
                      for g in report.get("gates", [])],
            "staged_sha256": sha256_file(_project_file(_PROJECT_ROOT, STAGING / path.name)),
        })
        ok_all = ok_all and bool(row["identity_ok"])
        rows.append(row)
    payload = {
        "schema": "sitin-candidate-admission-resign/1",
        "purpose": "投影/V2 参数批次改变候选绑定身份后，按当前身份在同一真实准入语料上重跑"
                   "四道门禁并重签记录（不手改字段、不放宽门槛）",
        "corpus": {"path": str(CORPUS.relative_to(REPO)), "sha256": current_corpus_sha},
        "rows": rows,
        "applied": False,
        "ok": bool(ok_all),
    }
    if args.apply and ok_all:
        for row in rows:
            if row["status"] == "REISSUED":
                shutil.copyfile(_project_file(_PROJECT_ROOT, STAGING / row["record"]), _project_file(_PROJECT_ROOT, GATE_DIR / row["record"]))
        payload["applied"] = True
    (_project_file(_PROJECT_ROOT, HERE / "gate-records" / "resign-report.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in rows:
        print(row["record"], row["status"], "| prior admitted=%s" % row["prior_admitted"],
              "| new admitted=%s" % row.get("new_admitted"),
              "| identity_ok=%s" % row.get("identity_ok"),
              "| failed=%s" % row.get("new_failed"))
    print("ok", payload["ok"], "applied", payload["applied"])
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
