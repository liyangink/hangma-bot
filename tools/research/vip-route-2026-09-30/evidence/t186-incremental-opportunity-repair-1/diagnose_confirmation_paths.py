"""四进程读取已闭T185确认的首分歧；只做路径诊断，不生成新牌局。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import asyncio
import fcntl
import gzip
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, OLD, canonical, pin, save
from diagnose_prior_first_divergences import first_divergence, compact_candidate
from analyze_prior_diverging_hands import hand_account
from t185_prepare_confirmation import background_priority


def require(condition, message):
    """证据缺口时保留失败，不补造原评分或结算。"""
    if not condition:
        raise ValueError(message)


def read_inputs():
    """核本次只读输入身份；母来源与桌数仍沿用原确认。"""
    files = [_project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json"), _project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-CLOSED.json"),
             _project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json"), Path(__file__),
             _project_file(_PROJECT_ROOT, PRIOR / "diagnose_prior_first_divergences.py"), _project_file(_PROJECT_ROOT, PRIOR / "analyze_prior_diverging_hands.py")]
    pins = {str(p): pin(p) for p in files}
    plan, closed, dispatch = (json.loads(p.read_text()) for p in files[:3])
    require(closed["complete"] and closed["source_stable"] and dispatch["complete"] and
            dispatch["resources_released"] and closed["actual_table_instances"] == 1024 and
            closed["comparison"]["candidate_id"] == plan["selected_candidate_id"], "原确认未闭合或身份不对应")
    require(dispatch["confirmation_closed_pin"] == pins[str(files[1])], "原确认闭合摘要不同")
    return plan, closed, pins


def worker(slot):
    """每槽读128对原桌；沿用研究槽0/1并增加2/3，不占自由赛owner。"""
    background_priority()
    plan, closed, pins = read_inputs()
    ordinals = list(range(slot, 512, 4))
    directory = _project_file(_PROJECT_ROOT, HERE / "confirmation-paths" / f"worker-{slot}")
    lock_path = OLD / f".resource-scheduling-worker-{slot}.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory.mkdir(parents=True, exist_ok=False)
        save(directory / "START.json", {"pid": os.getpid(), "slot": slot, "ordinals": ordinals,
            "files": pins, "nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io": True,
            "cpu_slot_lock": str(lock_path), "new_scores_worlds_tables_models_HTTP": 0})
        failure, rows, actual_bytes = None, [], 0
        started = time.monotonic()
        try:
            with (directory / "rows.jsonl").open("x") as output, \
                    gzip.open(directory / "public-first-rows.jsonl.gz", "xb") as public:
                for ordinal in ordinals:
                    index, rotation = divmod(ordinal, 4)
                    root, source = plan["roots"][index], closed["comparison"]["sources"][index]
                    pair = source["paired_tables"][rotation]
                    require(source["root_id"] == root["root_id"] and pair["rotation"] == rotation,
                            "原来源或换座不对应")
                    directories = [_project_file(_PROJECT_ROOT, PRIOR / "natural-confirmation" / f"root-{index + 1:03d}" /
                                   f"seat-{rotation}-arm-{arm}") for arm in (0, 1)]
                    paths = [d / "focal-decisions.jsonl.gz" for d in directories]
                    closures = []
                    for d, p in zip(directories, paths):
                        for q in (p, d / "CLOSURE.json"):
                            h = pin(q)
                            require(closed["files"].get(str(q)) == h, "原桌文件未绑定确认闭合")
                            pins[str(q)] = h
                        c = json.loads((d / "CLOSURE.json").read_text())
                        require(c["complete"] and c["failure"] is None and c["focal_seat"] == rotation
                                and len(c["settlements"]) == len(c["pairing_proofs"]) == 8,
                                "原桌或单局不完整")
                        closures.append(c)
                    status, originals = first_divergence(*paths)
                    row = {"ordinal": ordinal, "root_id": root["root_id"], "root_index": index + 1,
                           "rotation": rotation, **status, "table_delta": pair["delta"],
                           "path_comparison_not_isolated_action_effect": True}
                    if originals is not None:
                        a, b = originals
                        round_no = a["window_key"]["round_no"]
                        proofs = [c["pairing_proofs"][round_no - 1] for c in closures]
                        require(proofs[0]["physical_wall_sha256"] == proofs[1]["physical_wall_sha256"] and
                                proofs[0]["actual_initial_sha256"] == proofs[1]["actual_initial_sha256"] and
                                proofs[0]["dealer_seat"] == proofs[1]["dealer_seat"], "首分歧起手不同")
                        accounts = [hand_account(c["settlements"][round_no - 1]["settlement"], rotation)
                                    for c in closures]
                        pa, ca = a["selected_action_key"], b["selected_action_key"]
                        require(a["white_count"] == b["white_count"], "首分歧当前白数不同")
                        row.update(round_no=round_no, trigger_seq=a["window_key"]["trigger_seq"],
                            parent_action=pa, child_action=ca, switch=pa.split(":")[0] + "->" + ca.split(":")[0],
                            white_count=a["white_count"], remaining_tile_count=a["observation"]["remaining_tile_count"],
                            is_dealer=a["observation"]["dealer_seat"] == rotation,
                            parent_hand=accounts[0], child_hand=accounts[1],
                            hand_delta={k: accounts[1][k] - accounts[0][k] for k in
                                        ("net", "ordinary_income", "large_income", "payments")},
                            parent_scores=[compact_candidate(a, k) for k in (pa, ca)],
                            child_scores=[compact_candidate(b, k) for k in (pa, ca)])
                        raw = canonical({"ordinal": ordinal, "root_id": root["root_id"],
                            "rotation": rotation, "parent_original_row": a, "child_original_row": b}) + b"\n"
                        actual_bytes += len(raw)
                        require(actual_bytes <= 33554432, "每槽公开首行超过32MiB预算")
                        public.write(raw)
                    elif status["status"] == "all_focal_choices_same":
                        require(pair["delta"]["net"] == 0 and
                                closures[0]["settlements"] == closures[1]["settlements"], "同选择不同结算")
                    rows.append(row)
                    output.write(canonical(row).decode() + "\n")
                    output.flush()
                require(all(pin(Path(p)) == h for p, h in pins.items()), "读取期间原件漂移")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        save(directory / "CLOSE.json", {"complete": failure is None and len(rows) == len(ordinals),
            "failure": failure, "pid": os.getpid(), "slot": slot, "actual_ordinals": [r["ordinal"] for r in rows],
            "start_pin": pin(directory / "START.json"), "files": pins,
            "rows_pin": pin(directory / "rows.jsonl"), "public_rows_pin": pin(directory / "public-first-rows.jsonl.gz"),
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_scores_worlds_tables_models_HTTP": 0})
        require(failure is None, "只读诊断失败，原尝试不自动覆盖重跑")


async def dispatch():
    """四个真实读回进程自然结束后合并；不把读回并发冒称跑桌并发。"""
    background_priority()
    _, closed, pins = read_inputs()
    directory = _project_file(_PROJECT_ROOT, HERE / "confirmation-paths")
    directory.mkdir(exist_ok=False)
    save(directory / "START.json", {"pid": os.getpid(), "files": pins, "cpu_workers": 4,
        "expected_pairs": 512, "new_scores_worlds_tables_models_HTTP": 0,
        "not_actual_four_worker_table_dispatch": True})
    children, streams, failure, rows = [], [], None, []
    try:
        for slot in range(4):
            stream = (directory / f"WORKER-{slot}.log").open("x")
            streams.append(stream)
            command = [sys.executable, str(Path(__file__)), "--slot", str(slot)]
            child = await asyncio.create_subprocess_exec(*command, cwd=ROOT, stdout=stream, stderr=asyncio.subprocess.STDOUT)
            children.append(child)
            save(directory / f"WORKER-{slot}-DISPATCH.json", {"pid": child.pid, "slot": slot, "command": command})
        codes = await asyncio.gather(*(child.wait() for child in children))
        require(codes == [0] * 4, "读回worker失败，全部等待自然退出")
        for slot, child in enumerate(children):
            d = directory / f"worker-{slot}"
            end = json.loads((d / "CLOSE.json").read_text())
            require(end["complete"] and end["pid"] == child.pid and
                    end["actual_ordinals"] == list(range(slot, 512, 4)), "读回收据缺项")
            require(end["rows_pin"] == pin(d / "rows.jsonl"), "读回行摘要漂移")
            rows.extend(json.loads(line) for line in (d / "rows.jsonl").read_text().splitlines())
        rows.sort(key=lambda r: r["ordinal"])
        require([r["ordinal"] for r in rows] == list(range(512)) and
                sum(r["table_delta"]["net"] for r in rows) == closed["comparison"]["net_delta_sum_512_tables"],
                "四进程唯一覆盖或总净分不对账")
        for slot in range(4):
            with (OLD / f".resource-scheduling-worker-{slot}.lock").open("a+") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        groups = defaultdict(Counter)
        for row in rows:
            group = groups[row.get("switch", row["status"])]
            group["pairs"] += 1
            for key in ("net", "ordinary_hu_income", "large_hu_income", "payments"):
                group["associated_table_" + key] += row["table_delta"][key]
            for key, value in row.get("hand_delta", {}).items():
                group["first_hand_" + key] += value
        save(directory / "SUMMARY.json", {"complete": True, "status_counts": dict(Counter(r["status"] for r in rows)),
            "by_first_switch": dict(groups), "paired_tables_read": 512, "net_delta_sum": 2515,
            "path_observation_not_single_action_causal_estimate": True, "new_scores_worlds_tables_models_HTTP": 0})
        with (directory / "rows.jsonl").open("x") as stream:
            for row in rows:
                stream.write(canonical(row).decode() + "\n")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        # 已启动进程必须自然收尾；未知输出不重做。
        await asyncio.gather(*(child.wait() for child in children))
    finally:
        for stream in streams:
            stream.close()
        save(directory / "CLOSED.json", {"complete": failure is None, "failure": failure,
            "child_pids": [c.pid for c in children], "returncodes": [c.returncode for c in children],
            "actual_pairs": len(rows), "files": pins,
            "resources_released": failure is None, "new_scores_worlds_tables_models_HTTP": 0,
            "not_actual_four_worker_table_dispatch": True})
    require(failure is None, "诊断失败，保留原件")
    print(json.dumps({"complete": True, "paired_tables_read": len(rows), "new_table_calls": 0}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, choices=range(4))
    args = parser.parse_args()
    if args.slot is None:
        asyncio.run(dispatch())
    else:
        worker(args.slot)
