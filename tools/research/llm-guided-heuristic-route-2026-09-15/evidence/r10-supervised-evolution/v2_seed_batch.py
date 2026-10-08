"""V2相近种子的有界I1作者入口；复用受监管通道，评价必须显式推进。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "evidence/r9-takeover-2026-09-19")))
import pilot as channel
import sitin_real_behavior as behavior

OLD = channel.PILOT
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-seed-batch-03')
channel.PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-seed-batch-03')
channel.RUN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-seed-batch-03/run')
search = channel.search


def prepare():
    """冻结作者任务及费用；本阶段不隐式执行自然面板。"""
    if BATCH.exists():
        raise SystemExit("批次已存在；不得覆盖")
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")))
    from p12_authorization import unified_document
    feedback = (_project_file(_PROJECT_ROOT, HERE / "v2-seed-author-task-v2.md")).read_text()
    if len(feedback) > 12000:
        raise SystemExit("监督任务超过公共合同上界")
    panel = _project_file(_PROJECT_ROOT, HERE / "batch03-known-root-diagnostic/panel.json")
    auth = unified_document(batch_label="r10-v2-seed-03", authorization_id="r10-v2-seed-03",
        accounts={"tokens_input": 4 * 196608, "tokens_output": 4 * 32768,
                  "tables_full": 512, "tables_partial": 16, "prefix_generation": 16},
        issued_by="lead", issued_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        legacy_alias=False)
    auth.update({"generation_call_limits": {"tokens_input":196608,"tokens_output":32768},
        "max_model_calls":4,"max_proposals":4,"repair_calls_count_in_total":True,
        "wall_clock_limit_seconds":14400,"route":"supervised_candidate_development",
        "autonomous_admission":False,
        "issuance_basis":"用户授权候选/合同/反馈外发zai-coding-cn GLM5.3并由root持续安排；四次有界尝试",
        "scope":"离线V2相近种子；先合法性及差分；显式评价才运行自然开发；不确认、不发布",
        "development_behavior_panel":{"path":str(panel),"panel_digest":behavior.load_panel(panel)[0]},
        "supervisor_feedback":feedback})
    for op in auth["allowed_operations"]:
        assert search.av_authorization_audit(auth, operation=op)["ok"]
    BATCH.mkdir()
    channel.write(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), auth)
    settings=(OLD / "settings.yaml").read_text()
    if settings.count('reasoningEffort: max') != 1:
        raise SystemExit('设置模板与已核对结构不符，不猜测替换')
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings.replace('reasoningEffort: max','reasoningEffort: medium'))
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text("- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")) +
        "\n    watch: false\n- id: agent-default-model\n  config:\n    provider: zai-coding-cn\n    model: glm-5.3\n")
    manifest=json.loads((OLD / "manifest.json").read_text())
    manifest['expected_request_config']['reasoningEffort']='medium'
    manifest['supervised_note']='上批max-tokens无正文；修正宿主/受限API说明并请求medium，是否实际生效只认协议记录，不推定供应商推理预算'
    channel.write(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"),manifest)
    names = ["heuristic_v2.py","evaluation_v1.py","evaluation_v2.py","weights_v1.py","action_value.py"]
    channel.write(_project_file(_PROJECT_ROOT, BATCH / "source-context.json"), {
        "task_sha256":hashlib.sha256(feedback.encode()).hexdigest(),
        "source_sha256":{n:hashlib.sha256((_project_file(_PROJECT_ROOT, REPO / "src/hangma_bot/policy" / n)).read_bytes()).hexdigest() for n in names},
        "parity_scope":"限定正常生产首次窗口；不是完整V2等价声明",
        "confirmation_roots":0})
    print("种子作者批次已冻结，零调用")


def advance(stop):
    """推进现有提案，保留失败及停止状态，不隐式创建下一份。"""
    path=search.av_latest_state_path(channel.RUN)
    if path is None:
        raise SystemExit("尚无提案")
    result=search.av_iteration_advance(path,channel.RUN,authorization=channel.authorization(),stop_after=stop)
    print(json.dumps({k:result.get(k) for k in ("status","advanced","terminal","refused","waiting_for_reply")},ensure_ascii=False))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["prepare","start","call","ingest","evaluate"])
    a=p.parse_args()
    if (_project_file(_PROJECT_ROOT, BATCH / "batch-closure.json")).exists():
        raise SystemExit("批次已关闭")
    if a.action=="prepare":
        prepare()
    elif a.action=="start":
        if search.av_latest_state_path(channel.RUN):
            raise SystemExit("已有提案，不自动重开")
        state=search.av_start_iteration(channel.RUN,operator="i1",generation_mode="delegate",
            predicate="branch_open",opponent="H",natural_roots=2,natural_seats=4,
            prefix_source="v2_behavior",panel_seed=2026091914,authorization=channel.authorization(),
            archive_in={"source":"empty","path":None,"applied_operator":"i1",
                        "note":"默认V2基础排序的独立初始种子；不继承任何历史效果成绩"})
        if state.get("stop_reason"):
            raise SystemExit(state["stop_reason"])
        advance("BEHAVIOR_CHECKED")
    elif a.action=="call":
        ok,reason,_=search.av_verify_run_identity(channel.state())
        if not ok:
            raise SystemExit(reason)
        channel.call()
    else:
        advance("BEHAVIOR_CHECKED" if a.action=="ingest" else None)
