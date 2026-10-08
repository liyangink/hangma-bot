"""R10 有界监督批次：复用已审计 headless 通道，显式启动/调用/推进，不自动重试。"""
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
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "evidence/r9-takeover-2026-09-19")))
import pilot as channel
import sitin_real_behavior as behavior

OLD_PILOT = channel.PILOT
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/mechanism-batch-01')
channel.PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/mechanism-batch-01')
channel.RUN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/mechanism-batch-01/run')
search = channel.search


def prepare() -> None:
    """按明确用户授权冻结有界开发批次；零确认权限，不改写历史批次。"""
    if BATCH.exists():
        raise SystemExit("批次目录已存在，保留冻结配置")
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")))
    from p12_authorization import unified_document

    BATCH.mkdir()
    panel = _project_file(_PROJECT_ROOT, HERE / ("batch03-known-root-diagnostic/panel.json" if BATCH.name in ("mechanism-batch-04", "mechanism-batch-05")
                    else "real-behavior-panel-v1/panel.json"))
    continued = BATCH.name in ("mechanism-batch-03", "mechanism-batch-04", "mechanism-batch-05")
    attempts = 4 if continued else 2
    input_limit = 196608 if continued else 131072
    auth = unified_document(batch_label="r10-" + BATCH.name,
        authorization_id="r10-supervised-" + BATCH.name,
        accounts={"tokens_input": attempts * input_limit, "tokens_output": attempts * 32768,
                  "tables_full": 512 if continued else 160,
                  "tables_partial": 16 if continued else 8,
                  "prefix_generation": 16 if continued else 8},
        issued_by="lead", issued_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        legacy_alias=False)
    auth.update({"generation_call_limits": {"tokens_input": input_limit, "tokens_output": 32768},
        "max_model_calls": attempts, "max_proposals": attempts, "repair_calls_count_in_total": True,
        "wall_clock_limit_seconds": 7200 if continued else 3600, "route": "supervised_candidate_development",
        "autonomous_admission": False,
        "issuance_basis": ("用户明确授权项目源码/合同/反馈发往zai-coding-cn GLM5.3 API，API限额前由root安排持续推进；本批四次有界作者尝试"
                            if continued else "用户授权root监督持续进化；按保守两次传输尝试实施"),
        "scope": "离线开发；先一份M1；历史父代仅提供机制与反馈，不继承旧效果成绩参与新选留；不确认、不发布",
        "development_behavior_panel": {"path": str(panel), "panel_digest": behavior.load_panel(panel)[0]},
        "supervisor_feedback": (_project_file(_PROJECT_ROOT, HERE / ("next-claim-cost-task.md" if BATCH.name == "mechanism-batch-05"
                                  else "next-support-resolution-task.md" if BATCH.name == "mechanism-batch-04"
                                  else "next-compatible-branch-task.md" if continued
                                  else "next-mechanism-task.md"))).read_text().split("## 监督者后续裁定")[0],
        "natural_panel_note": "H/M各2个开发来源根，每根4座位2臂2桌；每候选64桌，另计条件续打；固定样本非显著性确认"})
    for operation in auth["allowed_operations"]:
        assert search.av_authorization_audit(auth, operation=operation)["ok"]
    channel.write(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), auth)
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text((OLD_PILOT / "settings.yaml").read_text())
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")) +
        "\n    watch: false\n- id: agent-default-model\n  config:\n    provider: zai-coding-cn\n    model: glm-5.3\n")
    channel.write(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), json.loads((OLD_PILOT / "manifest.json").read_text()))
    print("新批次配置已冻结；尚未调用模型或模拟")


def advance(stop=None) -> None:
    """只推进已有状态；终态不隐式启动新提案。"""
    path = search.av_latest_state_path(channel.RUN)
    if path is None:
        raise SystemExit("尚无提案")
    result = search.av_iteration_advance(path, channel.RUN,
              authorization=channel.authorization(), stop_after=stop)
    print(json.dumps({key: result.get(key) for key in
                      ("status", "advanced", "terminal", "refused", "waiting_for_reply")}, ensure_ascii=False))


def start() -> None:
    """监督者显式选择历史候选作首份M1父代；不继承不同批次的选留成绩。"""
    if search.av_latest_state_path(channel.RUN) is not None:
        raise SystemExit("已有提案；必须先审阅终态和选留结果，不能自动再开")
    parent = (_project_file(_PROJECT_ROOT, HERE / "mechanism-batch-04/run/iterations/iter-01/generation") if BATCH.name == "mechanism-batch-05"
              else _project_file(_PROJECT_ROOT, HERE / "mechanism-batch-03/run/iterations/iter-02/generation")
              if BATCH.name == "mechanism-batch-04" else OLD_PILOT / "run/iterations/iter-02/generation")
    state = search.av_start_iteration(channel.RUN, operator="m1", parent_dir=parent,
        generation_mode="delegate", predicate="branch_open", opponent="H",
        natural_roots=2, natural_seats=4, prefix_source="v2_behavior",
        panel_seed=2026091913 if BATCH.name == "mechanism-batch-05" else 2026091912 if BATCH.name == "mechanism-batch-04" else 2026091911 if BATCH.name == "mechanism-batch-03" else 2026091910,
        authorization=channel.authorization(),
        archive_in={"source": "empty", "path": None, "applied_operator": "m1",
                    "note": "root显式选择已合法交付的历史候选作机制父代；新档案为空，不继承历史效果成绩"})
    if state.get("stop_reason"):
        raise SystemExit(state["stop_reason"])
    advance("RESERVED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "start", "next", "call", "ingest", "evaluate"])
    parser.add_argument("--batch", choices=["mechanism-batch-01", "mechanism-batch-02", "mechanism-batch-03", "mechanism-batch-04", "mechanism-batch-05"], default="mechanism-batch-02")
    args = parser.parse_args()
    BATCH = _project_file(_PROJECT_ROOT, HERE / args.batch)
    channel.PILOT = BATCH
    channel.RUN = _project_file(_PROJECT_ROOT, BATCH / "run")
    if (_project_file(_PROJECT_ROOT, BATCH / "batch-closure.json")).exists():
        raise SystemExit("批次已关闭")
    if args.action == "prepare":
        prepare()
    elif args.action == "start":
        start()
    elif args.action == "next":
        # 仅显式 next 开新提案；调用公共调度入口继承当前档案和真实反馈。
        previous = channel.state()
        if previous.get("status") not in search.AV_TERMINAL_STATES and previous.get("status") != "ITERATION_COMPLETE":
            raise SystemExit("前一提案未结束，不能开新提案")
        result = search.run_av_evolution(channel.RUN, generation_mode="delegate",
            authorization=channel.authorization(), natural_roots=2, natural_seats=4,
            prefix_source="v2_behavior", panel_seed=2026091913 if BATCH.name == "mechanism-batch-05" else 2026091912 if BATCH.name == "mechanism-batch-04" else 2026091911 if BATCH.name == "mechanism-batch-03" else 2026091910,
            stop_after="RESERVED")
        print({key: result.get(key) for key in ("status", "terminal", "refused", "stopped_after")})
    elif args.action == "call":
        state = channel.state()
        ok, reason, _ = search.av_verify_run_identity(state)
        if not ok:
            raise SystemExit(reason)
        channel.call()
    else:
        advance("BEHAVIOR_CHECKED" if args.action == "ingest" else None)
