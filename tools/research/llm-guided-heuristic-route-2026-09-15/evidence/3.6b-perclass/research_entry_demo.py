"""perclass 包：受控研究执行入口的**拒绝路径回归**（用真实门禁记录，不用合成件）。

做法：读一份带 perclass 段的真实门禁记录（新基线冻结子集），按它现算：
  ① 结论类 = 逐类判定为 reliable 的类；
  ② 研究类 = 有窗口但未达 reliable 的类（研究的目的就是补它）；
  ③ 面板/候选身份 = 记录里的 bound_identity 与 corpus 身份。
然后生成**一个许可请求 + 若干拒绝请求**，逐个调用 CLI（真退出码），并把结果写成 raw。

**这不是效果证据**：这里只验证入口的拒绝路径与身份绑定，不含任何强度结论。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import subprocess
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
TOOL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools/sitin_gates.py')
GATE_RECORD = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/new-baseline/gates-four_component_path_value-perclass.json')
OUTDIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/research-entry')
PYTHON = sys.executable


def run(argv: list) -> tuple:
    result = subprocess.run([PYTHON, str(TOOL), *argv], capture_output=True, text=True,
                            cwd=str(ROOT))
    return result.returncode, (result.stdout + result.stderr).strip()


def main() -> int:
    record = json.loads(GATE_RECORD.read_text(encoding="utf-8"))
    perclass = record["perclass"]["detail"]
    verdicts = {entry["id"]: entry["verdict"] for entry in perclass["classes"]}
    declared = list(perclass["declared_classes"])
    reliable = [cid for cid in declared if verdicts[cid] == "reliable"]
    pending = [cid for cid in declared if verdicts[cid] != "reliable"]
    assert reliable and pending, (reliable, pending)

    base = {
        "schema": "sitin-gates-research-request/1",
        "entry_version": "perclass-research/1",
        "candidate": record["candidate"],
        "bound_identity": record["bound_identity"],
        "panel": {"path": record["corpus"]["path"], "rows": record["corpus"]["rows"],
                  "sha256": record["corpus"]["sha256"],
                  "constructed_trigger_set": record["corpus"]["constructed_trigger_set"]},
        "sampler": {"id": "scenario-visible-sampler", "version": "1.0.0",
                    "frozen_before_run": True, "seeds": [20260916, 20260917, 20260918],
                    "unit": "scenario_root"},
        "scope": {"research_classes": pending[:3], "claim_classes": reliable[:2],
                  "claim_kinds": ["behavior"]},
    }
    variants = {
        "permitted.json": base,
        "refused-admission-claim.json": dict(
            base, admission=True,
            scope=dict(base["scope"], claim_kinds=["behavior", "admission"])),
        "refused-claim-without-evidence.json": dict(
            base, scope=dict(base["scope"], claim_classes=[pending[0]])),
        "refused-identity-mismatch.json": dict(base, bound_identity="not-the-bound-identity"),
        "refused-sampler-not-frozen.json": dict(
            base, sampler=dict(base["sampler"], frozen_before_run=False)),
        "refused-unbounded-research-scope.json": dict(
            base, scope=dict(base["scope"], research_classes=[])),
        "refused-panel-mismatch.json": dict(base, panel=dict(base["panel"], rows=1)),
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    transcript = [
        "# 受控研究执行入口：拒绝路径回归（真实门禁记录 " + GATE_RECORD.name + "）",
        "",
        "候选 = {0}".format(record["candidate"]),
        "结论类（reliable）= {0}".format(reliable),
        "研究类（未达 reliable，正是研究要补的）= {0}".format(pending),
        "",
    ]
    codes = {}
    for name, payload in variants.items():
        request_path = _project_file(_PROJECT_ROOT, OUTDIR / name)
        request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        out_path = _project_file(_PROJECT_ROOT, OUTDIR / name.replace(".json", "-record.json"))
        code, output = run(["--research-entry", "--gate-record", str(GATE_RECORD),
                            "--research-request", str(request_path), "--out", str(out_path)])
        codes[name] = code
        transcript += ["## {0} ⇒ 退出码 {1}".format(name, code),
                       "", "\u0060\u0060\u0060", output or "(无输出)", "\u0060\u0060\u0060",
                       "记录内 permitted = {0}；refusals = {1}".format(
                           json.loads(out_path.read_text(encoding="utf-8"))["permitted"],
                           [item["code"] for item in
                            json.loads(out_path.read_text(encoding="utf-8"))["refusals"]]),
                       ""]
    # 校验器：许可记录必须过；把它改写成"准入了"必须判死。
    permitted_record = _project_file(_PROJECT_ROOT, OUTDIR / "permitted-record.json")
    code_ok, output_ok = run(["--verify-research", str(permitted_record)])
    forged_path = _project_file(_PROJECT_ROOT, OUTDIR / "forged-admission-record.json")
    forged = json.loads(permitted_record.read_text(encoding="utf-8"))
    forged.update({"admitted": True, "gate_level_admitted": True, "evidence_kind": "admission"})
    forged_path.write_text(json.dumps(forged, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    code_bad, output_bad = run(["--verify-research", str(forged_path)])
    transcript += [
        "## 校验器：许可记录 ⇒ 退出码 {0}".format(code_ok), "", "\u0060\u0060\u0060", output_ok, "\u0060\u0060\u0060", "",
        "## 校验器：改写成准入的伪造记录 ⇒ 退出码 {0}".format(code_bad), "",
        "\u0060\u0060\u0060", output_bad, "\u0060\u0060\u0060", "",
        "## 退出码汇总", "", json.dumps(codes, ensure_ascii=False), "",
        "**读法**：许可=0、被拒=2。被拒时记录仍然落盘（含全部拒绝理由），",
        "且任何研究记录的 admitted 恒为 false —— 触发集/研究执行资格**不是**准入。",
        "",
    ]
    (_project_file(_PROJECT_ROOT, HERE / "raw/20-research-entry-refusals.txt")).write_text("\n".join(transcript) + "\n",
                                                             encoding="utf-8")
    print("\n".join(transcript[:8]))
    print("退出码：", codes, "| 校验器:", code_ok, code_bad)
    return 0 if codes["permitted.json"] == 0 and code_ok == 0 and code_bad == 2 else 1


if __name__ == "__main__":
    sys.exit(main())
