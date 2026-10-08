#!/usr/bin/env python3
"""G108：全新 H/M 父代表逐单局取首个宽面冲突，结果盲测 G106 路线暴露。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import g95_wider_discard_same_hand_preflight as g95
import g106_local_claim_surface as g106
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G108-FRESH-HM-ROUTE-EXPOSURE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g108-fresh-hm-route-exposure-20260928')
PANEL_SEED = 2026111201
ROOTS = tuple(range(1, 17))


def sha(path: Path) -> str:
    """对程序、合同和输入原文做字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    """按规范 JSON 对依法可见观察生成稳定身份。"""
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


class CaptureEveryHandPolicy(g95.CaptureWiderPolicy):
    """同 G95 结果盲判据，每个完整单局只保存首次命中的不透明世界。"""

    def __init__(self, inner, capture_engine):
        super().__init__(inner, capture_engine)
        self.records = {}

    async def choose(self, request, budget):
        """新单局清除旧的首次命中标记；决策仍由冻结父代给出。"""
        round_no = request.window_key.round_no
        if round_no not in self.records and self.world is not None:
            self.world = None
            self.request = None
            self.parent_key = None
            self.alternate_key = None
            self.facts = {}
        plan = await super().choose(request, budget)
        if self.world is not None and round_no not in self.records:
            self.records[round_no] = SimpleNamespace(
                world=self.world, request=self.request,
                parent_key=self.parent_key,
                alternate_key=self.alternate_key,
                facts=self.facts,
            )
        return plan


def plans(contract: dict) -> list[tuple[str, int, int, object]]:
    """交错 H/M 根顺序，避免部分批次只覆盖单一对手池。"""
    result = []
    natural = g95.g93.natural
    for root_index in ROOTS:
        for mix in ("H", "M"):
            for seat in range(4):
                plan = natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=seat, panel_seed=PANEL_SEED,
                )[0]
                result.append((mix, root_index, seat, plan))
    return result


def describe_arm(observation, action_key: str) -> dict:
    """局部机会仅做存在性/物理上界账，不产生策略分数。"""
    surface = g106.arm_surface(observation, action_key)
    entries = surface["entries"]
    def opportunities(field: str) -> list[tuple]:
        return sorted({
            (entry["trigger_code"], entry["discarder_offset"], entry["kind"])
            for entry in entries if entry[field]
        })
    return {
        "claim_entries": len(entries),
        "plain_opportunities": opportunities("any_plain"),
        "high_opportunities": opportunities("any_high"),
    }


def target_row(captured) -> dict:
    """一个合法已选窗口的两臂只读特征；未知状态保留理由。"""
    request = captured.request
    observation = request.observation
    target = request.window_key
    row = {
        "round_no": target.round_no,
        "window_key": window_key_to_json(target),
        "observation_sha256": canonical_sha(observation_to_json(observation)),
        "parent_action": captured.parent_key,
        "alternate_action": captured.alternate_key,
        "visible_action_facts": captured.facts,
        "white_before": sum(tile.code == "白" for tile in observation.my_hand)
        + int(observation.drawn_tile is not None and observation.drawn_tile.code == "白"),
        "catch_play": observation.rule_state.catch_play,
        "chain_count": observation.rule_state.chain_count,
    }
    if captured.parent_key is None or captured.alternate_key is None:
        raise ValueError("G95 首次冲突动作缺失")
    try:
        parent = describe_arm(observation, captured.parent_key)
        alternate = describe_arm(observation, captured.alternate_key)
        row["status"] = "complete"
        row["arms"] = {"parent": parent, "alternate": alternate}
        row["delta"] = {}
        for field in ("plain_opportunities", "high_opportunities"):
            left = {tuple(item) for item in parent[field]}
            right = {tuple(item) for item in alternate[field]}
            row["delta"][field] = {
                "parent_only": sorted(left - right),
                "alternate_only": sorted(right - left),
                "shared": len(left & right),
            }
    except (ValueError, TypeError) as exc:
        row["status"] = "unavailable"
        row["reason"] = type(exc).__name__ + ": " + str(exc)[:250]
    return row


def run_table(mix: str, root_index: int, seat: int, plan, contract: dict,
              versions: dict) -> dict:
    """完成整张父代表；不读取成绩给目标窗或局部机会作标签。"""
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = CaptureEveryHandPolicy
    try:
        captured, _, _, _, hands, outcome = g95.run_full(
            plan, contract, versions, mix,
        )
    finally:
        g95.CaptureWiderPolicy = original
    if not isinstance(captured, CaptureEveryHandPolicy):
        raise ValueError("G108 首冲突采集器装配错误")
    if len(hands) != int(versions["rounds_per_game"]):
        raise ValueError("G108 父代表单局数不完整")
    targets = [target_row(captured.records[r]) for r in sorted(captured.records)]
    return {
        "mix": mix, "root_index": root_index, "focal_seat": seat,
        "table_id": plan.table_id, "seed": plan.seed,
        "status": "complete", "hands": len(hands),
        "target_windows": targets,
    }


def manifest(contract_path: Path) -> dict:
    """记录整批结果盲选择所依赖的代码和面板合同。"""
    return {
        "schema": "g108-fresh-hm-route-exposure-manifest/1",
        "panel_seed": PANEL_SEED, "roots": list(ROOTS),
        "tables_planned": len(ROOTS) * 2 * 4,
        "input_sha256": {
            "prereg": sha(PREREG), "script": sha(Path(__file__)),
            "contract": sha(contract_path),
            "g95": sha(Path(g95.__file__)),
            "g106": sha(Path(g106.__file__)),
            "g93": sha(Path(g95.g93.__file__)),
        },
        "boundary": "父代完整桌只用于结果盲窗口选择；机会面不是收益标签。",
    }


def read_existing(expected: dict) -> list[dict]:
    """仅在清单完全一致时从已完成整桌行继续，不重启已完成计划。"""
    if not OUT.exists():
        return []
    recorded = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if recorded != expected:
        raise ValueError("G108 已有批次清单不一致，拒绝混写")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    if not rows_path.exists():
        return []
    return [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]


def summary(rows: list[dict], expected_tables: int) -> dict:
    """按根/对手池保留相关性，不把四座或同手多窗冒充独立样本。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        targets = [t for row in group for t in row["target_windows"]]
        high = [t for t in targets if t["status"] == "complete" and
                (t["delta"]["high_opportunities"]["parent_only"] or
                 t["delta"]["high_opportunities"]["alternate_only"])]
        by_mix[mix] = {
            "tables": len(group), "roots": len({row["root_index"] for row in group}),
            "target_windows": len(targets),
            "opportunity_complete": sum(t["status"] == "complete" for t in targets),
            "opportunity_unavailable": sum(t["status"] == "unavailable" for t in targets),
            "high_difference_windows": len(high),
            "high_difference_roots": len({row["root_index"] for row in group
                                           if any(t in high for t in row["target_windows"])}),
            "high_alt_only_windows": sum(bool(t["delta"]["high_opportunities"]["alternate_only"])
                                         for t in high),
            "high_parent_only_windows": sum(bool(t["delta"]["high_opportunities"]["parent_only"])
                                            for t in high),
        }
    return {
        "schema": "g108-fresh-hm-route-exposure-summary/1",
        "status": "complete" if len(rows) == expected_tables else "in_progress",
        "tables_completed": len(rows), "tables_planned": expected_tables,
        "by_mix": by_mix,
        "boundary": "行动前局部机会，不是完整可达事件链或整桌收益。",
    }


def main() -> None:
    """按冻结顺序执行；支持整桌级续跑和少量试运行。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-first", action="store_true")
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    contract_path = g95.g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    all_plans = plans(contract)
    expected = manifest(contract_path)
    if len(all_plans) != expected["tables_planned"]:
        raise ValueError("G108 计划数不守恒")
    if args.dry_run_first:
        mix, root_index, seat, plan = all_plans[0]
        row = run_table(mix, root_index, seat, plan, contract, versions)
        print(json.dumps({"mix": mix, "root": root_index, "seat": seat,
                          "targets": len(row["target_windows"]),
                          "statuses": [t["status"] for t in row["target_windows"]]},
                         ensure_ascii=False))
        return
    rows = read_existing(expected)
    for old, (mix, root_index, seat, plan) in zip(rows, all_plans):
        if (old["mix"], old["root_index"], old["focal_seat"], old["table_id"]) != (
            mix, root_index, seat, plan.table_id,
        ):
            raise ValueError("G108 已有整桌行不是冻结计划前缀")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
    added = 0
    with (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl")).open("a", encoding="utf-8") as stream:
        for mix, root_index, seat, plan in all_plans[len(rows):]:
            row = run_table(mix, root_index, seat, plan, contract, versions)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            print(json.dumps({"mix": mix, "root": root_index, "seat": seat,
                              "targets": len(row["target_windows"]),
                              "high_diff": sum(t["status"] == "complete" and
                                               bool(t["delta"]["high_opportunities"]["parent_only"] or
                                                    t["delta"]["high_opportunities"]["alternate_only"])
                                               for t in row["target_windows"]),
                              "done": len(rows)}, ensure_ascii=False), flush=True)
            if args.max_new and added >= args.max_new:
                break
    result = summary(rows, len(all_plans))
    (_project_file(_PROJECT_ROOT, OUT / "progress.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if len(rows) == len(all_plans):
        (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
