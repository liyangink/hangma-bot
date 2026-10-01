"""显式开发公开输入来源；只读行动前字段，来源验证不调用规则、评分或世界。"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import ast
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER
from .scoring_sources import REPO_ROOT

SOURCE_SCHEMA = "vip-eoh-input-source/2"
PANEL_SCHEMA = "vip-eoh-development-panel/2"
NATURAL = "frozen_natural_A_R18_action_before/1"
CONDITIONED = "physical_conditioned_initial_public/1"
CLAIMS = {"development_only": True, "confirmation": False, "admitted": False,
          "complete_table_claim": False, "strength_claim": False, "release_claim": False}
SELECTION = {
    "version": "action_before_root_capped_strata/2",
    "strata": ["phase", "own_white_count", "own_natural_pair_count", "wall_band", "public_meld_count", "current_legal_hu"],
    "natural_pairs": "own_hand_plus_drawn_excluding_white_sum_floor_count_over_2_descriptive_only",
    "wall_bands": ["unknown", "0_to_20", "21_to_40", "41_plus"],
    "within_stratum": "unique_input_sha256_ascending",
    "across_strata": "own_white_count_phase_bucket_round_robin_one_selected_per_bucket_per_round",
    "bucket_order": "own_white_count_ascending_then_phase_ascending",
    "within_bucket": "stratum_canonical_json_sha256_ascending_round_robin_then_input_sha256_ascending",
    "dedup": "exact_public_payload_sha256;conditional_hidden_variants_share_one_root_input",
    "root_cap": "per_source_id_and_mother_root;explicit_positive_integer",
    "empty_rare_strata": "unknown_not_passed",
    "forbidden_selection_fields": ["candidate_score", "selected_action_key", "winner", "settlement", "status", "elapsed", "future_wall"],
}


def canonical(value: Any) -> bytes:
    """规范JSON无损保留None、空、0，非有限数拒绝。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fingerprint(path: Path) -> dict:
    """流式核字节，避免把完整自然日志及结果载荷同时装入内存。"""
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def checked_json(reference: dict, frozen: dict) -> dict:
    """调用方提供字面摘要；来源对象必须完整、不可用默认值补齐。"""
    if set(reference) != {"path", "sha256"}:
        raise ValueError("文件引用须显式path/sha256")
    path = Path(reference["path"]).resolve()
    expected = reference["sha256"]
    if type(expected) is not str or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("来源须显式64位小写SHA256")
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError("来源字节漂移:" + str(path))
    frozen[str(path)] = expected
    return json.loads(raw)


def seal_members(seal: dict) -> dict:
    """真实既封容器明确分支并复核原始计数，不转换历史schema。"""
    result = {}
    if isinstance(seal.get("files"), dict):
        items = [(str(Path(name).resolve()), value) for name, value in seal["files"].items()]
    elif type(seal.get("members")) is list:
        items = [(str((REPO_ROOT / item["path"]).resolve()), {k: item[k] for k in ("bytes", "sha256")}) for item in seal["members"]]
    else:
        raise ValueError("未知首封容器")
    for path, value in items:
        if path in result or set(value) != {"bytes", "sha256"} or type(value["bytes"]) is not int or value["bytes"] < 0 or type(value["sha256"]) is not str or len(value["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in value["sha256"]):
            raise ValueError("首封成员重复或字节摘要合同不完整")
        result[path] = value
    count = seal.get("file_count", seal.get("files") if type(seal.get("files")) is int else len(result))
    if not result or type(count) is not int or count != len(result) or "bytes" in seal and sum(v["bytes"] for v in result.values()) != seal["bytes"]:
        raise ValueError("首封成员原始分母不完整")
    return result


def verify_members(members: dict, frozen: dict, *, snapshot_map: dict | None = None) -> None:
    """所有原件核字节；仅明确封存映射中的原生产成员改用对应冻结快照。"""
    for name, expected in members.items():
        path = Path((snapshot_map or {}).get(name, name))
        if fingerprint(path) != expected:
            raise ValueError("首封成员缺失或漂移:" + str(path))
        frozen[str(path.resolve())] = expected["sha256"]


def producer_snapshot(reference: dict, producer_ref: dict, members: dict, frozen: dict) -> dict:
    """真快照首封逐项绑定原src/scripts/doc；候选及旧code_snapshot仍核原件。"""
    seal = checked_json(reference, frozen)
    if seal.get("schema") != "t10-pre-change-producer-snapshot/1":
        raise ValueError("不是真实生产变更前快照")
    source = {"path": str(Path(producer_ref["path"]).resolve()), "sha256": producer_ref["sha256"]}
    source_refs = [{"path": str((REPO_ROOT / r["path"]).resolve()), "sha256": r["sha256"]} for r in seal["source_seals"]]
    if source not in source_refs:
        raise ValueError("快照未绑定本条件producer首封")
    mapped = {}
    for item in seal["members"]:
        relative = Path(item["original_path"])
        original, snapshot = (REPO_ROOT / relative).resolve(), (REPO_ROOT / item["snapshot_path"]).resolve()
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] not in {"src", "scripts", "doc"} or str(original) in mapped:
            raise ValueError("快照重复或将普通RAW代码冒充生产源码")
        expected = {k: item[k] for k in ("bytes", "sha256")}
        if fingerprint(snapshot) != expected:
            raise ValueError("生产变更前快照缺失或漂移")
        frozen[str(snapshot)] = expected["sha256"]
        if str(original) in members:
            if members[str(original)] != expected:
                raise ValueError("快照不是原producer相同字节")
            mapped[str(original)] = str(snapshot)
    production = {name for name in members if Path(name).relative_to(REPO_ROOT).parts[0] in {"src", "scripts", "doc"}}
    if set(mapped) != production or len(seal["members"]) != seal["files"] or sum(i["bytes"] for i in seal["members"]) != seal["bytes"]:
        raise ValueError("producer生产成员冻结映射不完整")
    return mapped


def public_input(record: dict, origin: dict) -> dict:
    """只投影行动前观察、窗口键和完整合法键；不拷贝结果、选择或评分。"""
    observation, window = record["observation"], record["window_key"]
    visible, key = observation_from_json(observation), window_key_from_json(window)
    if (visible.game_id, visible.round_no, visible.seat, visible.phase) != (key.game_id, key.round_no, key.seat, key.phase):
        raise ValueError("观察和窗口绑定错误")
    legal = record["legal_action_keys"]
    if type(legal) is not list or not legal or any(type(k) is not str for k in legal) or len(set(legal)) != len(legal):
        raise ValueError("合法动作键不完整或重复")
    if not {k.split(":", 1)[0] for k in legal} <= {"discard", "chi", "peng", "gang", "hu", "pass"}:
        raise ValueError("未知动作族")
    counts = Counter(t.code for t in visible.my_hand + (() if visible.drawn_tile is None else (visible.drawn_tile,)))
    wall = visible.remaining_tile_count
    band = "unknown" if wall is None else "0_to_20" if wall <= 20 else "21_to_40" if wall <= 40 else "41_plus"
    stratum = [visible.phase, counts["白"], sum(n // 2 for c, n in counts.items() if c != "白"), band,
               sum(len(m) for m in visible.melds), "hu" in legal]
    payload = {"observation": observation, "window_key": window, "legal_action_keys": sorted(legal)}
    return {**payload, "observation_sha256": sha(canonical(observation)), "input_sha256": sha(canonical(payload)),
            "stratum": stratum, "origins": [origin], **CLAIMS}


def _natural(spec: dict, frozen: dict) -> tuple[list, dict]:
    directory = Path(spec["audit_dir"]).resolve()
    manifest_path = directory / "manifest.json"
    manifest = checked_json(spec["manifest"], frozen)
    if Path(spec["manifest"]["path"]).resolve() != manifest_path or manifest["schema"] not in ("vip-route-development-manifest/1", "vip-route-development-manifest/2"):
        raise ValueError("自然来源不得改名为smoke或假schema")
    if manifest["source_kind"] != "simulation" or manifest["development_only"] is not True or manifest["confirmation_claim"] is not False or manifest["published"] is not False:
        raise ValueError("自然来源不是未确认开发材料")
    baseline = manifest["policy_metadata"]["A"]
    if baseline["registered_name"] != "r18_integrated_positive_v2" or baseline["provider"] != "registered_offline_research_not_live_release":
        raise ValueError("A不是注册研究R18")
    raw = seal_members(checked_json(spec["raw_seal"], frozen))
    verify_members(raw, frozen)
    actual = {str(p.resolve()) for p in directory.rglob("*") if p.is_file() and p.resolve() != Path(spec["raw_seal"]["path"]).resolve()}
    if actual != {p for p in raw if Path(p).is_relative_to(directory)}:
        raise ValueError("自然RAW缺成员或含未知新增文件")
    verify_natural_producer(directory, manifest)
    verify_natural_baseline(directory, manifest, raw)
    for relative, expected in manifest["source_manifest"].items():
        snapshot = directory / "code_snapshot" / relative
        if str(snapshot.resolve()) not in raw or fingerprint(snapshot) != expected:
            raise ValueError("自然producer源码快照不完整")
    frame = {r["root_id"]: {tuple(p) for p in r["permutations"]} for r in manifest["frame"]}
    if len(frame) != len(manifest["frame"]) or not frame:
        raise ValueError("母根抽样框重复或为空")
    verify_natural_integrity(directory, manifest, raw, frame)
    rows, groups, windows = [], set(), set()
    for pool in sorted(manifest["pool_ids"]):
        log = directory / pool / "decisions.jsonl.gz"
        if str(log.resolve()) not in raw:
            raise ValueError("自然行动日志未被RAW绑定")
        with gzip.open(log, "rt", encoding="utf-8") as stream:
            for line, text in enumerate(stream, 1):
                record = json.loads(text)
                if record["policy_id"] != baseline["policy_id"]:
                    continue
                root, permutation = record["root_id"], tuple(record["permutation"])
                expected_match = f"{manifest['batch_id']}:{pool}:{root}:{''.join(map(str, permutation))}:{baseline['policy_id']}"
                if root not in frame or permutation not in frame[root] or record["pool"] != pool or record["match_id"] != expected_match or record["seat"] != permutation[0]:
                    raise ValueError("A轨迹越根、越换座或混入C轨迹")
                logical = (record["match_id"], canonical(record["window_key"]))
                if logical in windows:
                    raise ValueError("自然同一实际行动前窗口重复")
                windows.add(logical)
                groups.add((root, pool, permutation))
                observation = record["observation"]
                origin = {"source_id": spec["source_id"], "source_kind": NATURAL, "mother_root": root,
                          "mother_single_hand": [record["match_id"], observation["round_no"]], "permutation": list(permutation),
                          "hidden_variant": "natural", "policy_role": "A", "policy_id": baseline["policy_id"],
                          "source_file": str(log), "source_line": line, "pool": pool, **CLAIMS}
                rows.append(public_input(record, origin))
    expected_groups = {(root, pool, permutation) for root, ps in frame.items() for pool in manifest["pool_ids"] for permutation in ps}
    if groups != expected_groups:
        raise ValueError("自然A行动前抽样框缺根或换座")
    return rows, {"kind": NATURAL, "frame": manifest["frame"], "pool_ids": manifest["pool_ids"], "A_identity": baseline, "source_schema": manifest["schema"]}


def _conditioned(spec: dict, frozen: dict) -> tuple[list, dict]:
    prereg = checked_json(spec["prereg"], frozen)
    if prereg["schema"] != "t9-fresh-shape-paired-development-prereg/1" or prereg["result_blind_fixed_all_roots"] is not True or prereg["root_selection_uses_candidate_score_or_after_action_result"] is not False:
        raise ValueError("条件起点不是前定结果盲母体")
    roots = prereg["root_ids"]
    variants = prereg["variant_order"]
    if len(roots) != len(set(roots)) or len(roots) != prereg["root_count"] or variants != ["original", "public_consistent_hidden_1"]:
        raise ValueError("条件母根或隐藏变体分母错误")
    raw = seal_members(checked_json(spec["raw_seal"], frozen))
    verify_members(raw, frozen)
    producer = seal_members(checked_json(spec["producer_seal"], frozen))
    # 原条件批没有code_snapshot；必须在生产变化前另封相同代码快照，绝不信任变后的当前源。
    verify_members(producer, frozen, snapshot_map=producer_snapshot(spec["producer_snapshot"], spec["producer_seal"], producer, frozen))
    source_roots = verify_conditioned_inputs(prereg, producer)
    directory = Path(spec["audit_dir"]).resolve()
    actual = {str(p.resolve()) for p in directory.rglob("*") if p.is_file() and p.resolve() != Path(spec["raw_seal"]["path"]).resolve()}
    if actual != set(raw):
        raise ValueError("条件RAW不是完整实际目录")
    first = {}
    for path in sorted(directory.glob("R18-policy-*.json")):
        record = json.loads(path.read_bytes())
        if record["arm_id"].endswith(":A") and record["window_key"]["trigger_seq"] == 0 and record["window_key"]["seat"] == prereg["focal_seat"]:
            arm = record["arm_id"]
            if arm in first:
                raise ValueError("同根隐藏版本重复初始A行动")
            first[arm] = (path, record)
    rows = []
    for root in roots:
        original_sha = None
        for variant in variants:
            arm = f"{root}:{variant}:A"
            path, record = first.pop(arm)
            common_file = directory / f"{root}-{variant}-common-observations.json"
            common = json.loads(common_file.read_bytes())
            if canonical(record["observation"]) != canonical(source_roots[root]["observation"]):
                raise ValueError("实际条件起点不是前定母根公开观察")
            if [x["branch"] for x in common] != ["A", "C"] or canonical(common[0]["observation"]) != canonical(common[1]["observation"]) or canonical(record["observation"]) != canonical(common[0]["observation"]):
                raise ValueError("共同条件起点不等于A第一实际公开观察")
            origin = {"source_id": spec["source_id"], "source_kind": CONDITIONED, "mother_root": root,
                      "mother_single_hand": [root, record["observation"]["round_no"]], "permutation": [0, 1, 2, 3],
                      "hidden_variant": variant, "policy_role": "A", "policy_id": prereg["r18_name"],
                      "source_file": str(path), "common_observation_file": str(common_file), **CLAIMS}
            item = public_input(record, origin)
            if original_sha is not None and item["input_sha256"] != original_sha:
                raise ValueError("同母根hidden公开输入并非相同，不能冒充8输入")
            original_sha = item["input_sha256"]
            rows.append(item)
    if first:
        raise ValueError("条件初始A记录越出前定母根")
    return rows, {"kind": CONDITIONED, "mother_roots": roots, "variants": variants, "source_schema": prereg["schema"], "natural_prevalence": "unknown"}


def read_public_input_source(path: Path, expected_sha256: str) -> dict:
    """重核真实RAW全部字节与producer后返回行动前抽样框；仅I/O，无业务调用。"""
    frozen = {}
    spec = checked_json({"path": str(path), "sha256": expected_sha256}, frozen)
    common = {"schema", "source_id", "source_kind", "audit_dir", "raw_seal"}
    extras = {"manifest"} if spec.get("source_kind") == NATURAL else {"prereg", "producer_seal", "producer_snapshot"}
    if set(spec) != common | extras or spec.get("schema") != SOURCE_SCHEMA or spec.get("source_kind") not in (NATURAL, CONDITIONED) or not isinstance(spec["source_id"], str) or not spec["source_id"]:
        raise ValueError("必须显式声明严格source_kind及完整来源字段")
    rows, frame = (_natural if spec["source_kind"] == NATURAL else _conditioned)(spec, frozen)
    if not rows:
        raise ValueError("来源无行动前公开输入")
    return {"source": spec, "frame": frame, "records": rows, "frozen_files": frozen}


def select_public_inputs(materials: list, limits: dict) -> dict:
    """固定分层轮选并按每来源母根限额截断；完整抽样框与隐藏重复簇都保留。"""
    if set(limits) != {"per_stratum", "max_windows", "max_windows_per_source_root"} or any(type(v) is not int or v < 1 for v in limits.values()) or limits["max_windows"] > 128:
        raise ValueError("抽样限额必须显式正整数且总窗≤128")
    if not materials:
        raise ValueError("至少一个真实输入来源")
    if len({(m["source"]["source_kind"], str(Path(m["source"]["audit_dir"]).resolve())) for m in materials}) != len(materials):
        raise ValueError("同一来源不得改名重复纳入抽样框")
    if len({m["source"]["source_id"] for m in materials}) != len(materials):
        raise ValueError("source_id重复")
    unique = {}
    for material in materials:
        for record in material["records"]:
            key = record["input_sha256"]
            if key not in unique:
                unique[key] = json.loads(canonical(record))
            else:
                prior = unique[key]
                if any(prior[field] != record[field] for field in ("observation", "window_key", "legal_action_keys", "stratum")):
                    raise ValueError("重复SHA输入发生变化")
                for origin in record["origins"]:
                    if origin in prior["origins"]:
                        raise ValueError("同来源行动前记录重复")
                    prior["origins"].append(origin)
    strata = defaultdict(list)
    for item in unique.values():
        item["origins"].sort(key=lambda o: canonical(o))
        strata[canonical(item["stratum"]).decode()].append(item)
    keys = sorted(strata, key=lambda k: sha(k.encode()))
    groups = [sorted(strata[k], key=lambda r: r["input_sha256"]) for k in keys]
    buckets = defaultdict(list)
    for index, key in enumerate(keys):
        layer = json.loads(key)
        buckets[layer[1], layer[0]].append(index)
    queues = {}
    for bucket, indexes in buckets.items():
        queues[bucket] = deque((i, groups[i][depth]) for depth in range(max(len(groups[i]) for i in indexes))
                              for i in indexes if depth < len(groups[i]))
    root_counts, layer_counts, selected = Counter(), Counter(), []
    while len(selected) < limits["max_windows"] and any(queues.values()):
        for bucket in sorted(queues):
            queue = queues[bucket]
            while queue and len(selected) < limits["max_windows"]:
                index, item = queue.popleft()
                clusters = {(o["source_id"], o["mother_root"]) for o in item["origins"]}
                if layer_counts[index] >= limits["per_stratum"] or any(root_counts[c] >= limits["max_windows_per_source_root"] for c in clusters):
                    continue
                selected.append(item)
                layer_counts[index] += 1
                root_counts.update(clusters)
                break
    return {"windows": selected, "window_count": len(selected), "source_record_count": sum(len(m["records"]) for m in materials),
            "unique_input_count": len(unique), "source_frames": [m["frame"] for m in materials],
            "sampling_frame": [{"input_sha256": r["input_sha256"], "stratum": r["stratum"], "origins": r["origins"]} for r in sorted(unique.values(), key=lambda r: r["input_sha256"])],
            "stratum_sizes": [{"stratum": g[0]["stratum"], "unique_inputs": len(g), "selected": layer_counts[i]} for i, g in enumerate(groups)],
            "selected_source_roots": [{"source_id": k[0], "mother_root": k[1], "windows": v} for k, v in sorted(root_counts.items())],
            "empty_rare_strata": "unknown_not_passed"}


def build_public_input_panel(source_refs: list, out_dir: Path, *, limits: dict) -> dict:
    """只读全部原始来源，构建新/2面板；历史/1不能转写为/2来源。"""
    materials = [read_public_input_source(Path(r["path"]), r["sha256"]) for r in source_refs]
    selection = select_public_inputs(materials, limits)
    if not selection["window_count"]:
        raise ValueError("限额下没有选中公开输入")
    frozen = merge_frozen(materials)
    result = {"schema": PANEL_SCHEMA, **CLAIMS, "selection": SELECTION, "limits": limits,
              "source_refs": source_refs, "frozen_files": frozen, **selection}
    for path, digest in frozen.items():
        if fingerprint(Path(path))["sha256"] != digest:
            raise ValueError("面板生产过程中来源漂移")
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "panel.json").write_bytes(canonical(result) + b"\n")
    return result


def validate_public_input_panel(path: Path) -> dict:
    """重核真实RAW、producer、抽样框、固定选择和全部输入；摘要本身不能自证。"""
    raw = path.read_bytes()
    panel = json.loads(raw)
    if panel.get("schema") != PANEL_SCHEMA or panel.get("selection") != SELECTION or any(panel.get(k) != v for k, v in CLAIMS.items()):
        raise ValueError("不是显式来源/2面板")
    materials = [read_public_input_source(Path(r["path"]), r["sha256"]) for r in panel["source_refs"]]
    expected = {"schema": PANEL_SCHEMA, **CLAIMS, "selection": SELECTION, "limits": panel["limits"], "source_refs": panel["source_refs"],
                "frozen_files": merge_frozen(materials), **select_public_inputs(materials, panel["limits"])}
    if not expected["window_count"] or canonical(expected) != canonical(panel):
        raise ValueError("面板抽样框/选择/输入/根限额与真实来源不一致")
    return {"panel": panel, "frozen_files": {**panel["frozen_files"], str(path.resolve()): sha(raw)}}


def merge_frozen(materials: list) -> dict:
    """同一路径不能以不同摘要悄悄覆盖前一来源。"""
    files = {}
    for material in materials:
        for path, digest in material["frozen_files"].items():
            if path in files and files[path] != digest:
                raise ValueError("来源闭包同路径不同字节")
            files[path] = digest
    return files


def verify_natural_producer(directory: Path, manifest: dict) -> None:
    """按已封快照静态重求自然producer闭包；解析失败或空清单不能冒称完整。"""
    snapshot = directory / "code_snapshot"
    declared = manifest["source_manifest"]
    def resolve(module):
        part = Path(*module.split("."))
        for relative in (Path("src") / part.with_suffix(".py"), Path("src") / part / "__init__.py"):
            if (snapshot / relative).is_file():
                return relative
        return None
    todo, reached = ["hangma_bot.offline.vip_route_development"], set()
    while todo:
        module = todo.pop()
        if module in reached:
            continue
        reached.add(module)
        relative = resolve(module)
        if relative is None or str(relative) not in declared:
            raise ValueError("自然producer真实执行依赖缺失:" + module)
        tree = ast.parse((snapshot / relative).read_text(encoding="utf-8"))
        package = list(relative.parts[1:-1])
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
                if any(name.startswith("hangma_bot.") and resolve(name) is None for name in imports):
                    raise ValueError("自然producer显式导入源码缺失")
            elif isinstance(node, ast.ImportFrom):
                base = package[:len(package) - (node.level - 1)] if node.level else []
                name = ".".join(base + ([node.module] if node.module else []))
                if name.startswith("hangma_bot.") and resolve(name) is None:
                    raise ValueError("自然producer真实模块缺失:" + name)
                imports = [name] + [name + "." + alias.name for alias in node.names]
            todo.extend(name for name in imports if name.startswith("hangma_bot.") and resolve(name) is not None)
    required = {str(resolve(module)) for module in reached}
    identity_sources = manifest["candidate_identity"]["source_manifest"]
    if not identity_sources or any(declared.get(name) != value for name, value in identity_sources.items()):
        raise ValueError("自然producer未绑定真实候选共同依赖")
    required.update(identity_sources)
    required.add("scripts/vip_route_development.py")
    if set(declared) != required:
        raise ValueError("自然producer源码闭包与候选来源不精确")
    driver = (snapshot / "src/hangma_bot/offline/vip_route_development.py").read_text(encoding="utf-8")
    if repr(manifest["schema"]) not in driver and '"' + manifest["schema"] + '"' not in driver:
        raise ValueError("自然manifest版本不是其真实producer版本")


def verify_natural_integrity(directory: Path, manifest: dict, raw: dict, frame: dict) -> None:
    """完整源的全有全无门：只核终态分母/漂移，不读取分数选择或按结果删根。"""
    for root in manifest["frame"]:
        permutations = root["permutations"]
        if (len(permutations) != len(frame[root["root_id"]]) or not permutations
                or any(len(p) != 4 or any(type(v) is not int for v in p) or set(p) != {0, 1, 2, 3} for p in permutations)):
            raise ValueError("自然母根换座重复或不完整")
    path = directory / "summary.json"
    if str(path.resolve()) not in raw:
        raise ValueError("完整自然源未绑定实际终态")
    summary = json.loads(path.read_bytes())
    planned = 2 * sum(len(ps) for ps in frame.values()) * len(manifest["pool_ids"])
    if (summary["schema"] not in ("vip-route-development-result/1", "vip-route-development-result/2")
            or summary["batch_id"] != manifest["batch_id"] or summary["source_kind"] != "simulation"
            or summary["status"] != "development_complete_not_confirmed" or summary["identity_stable"] is not True
            or summary["drift_error"] is not None or summary["planned_table_instances"] != planned
            or summary["charged_table_instances"] != planned or manifest["planned_table_instances"] != planned
            or summary["development_only"] is not True or summary["confirmation_claim"] is not False or summary["published"] is not False
            or manifest["strict_challenger"] is not True or set(summary["pools"]) != set(manifest["pool_ids"])):
        raise ValueError("自然完整源终态/母根分母/漂移不闭合")
    for pool in summary["pools"].values():
        if pool["development_complete"] is not True or pool["planned_rows"] != planned // len(manifest["pool_ids"]) or pool["observed_rows"] != pool["planned_rows"]:
            raise ValueError("自然完整源缺实际注册桌实例")


def verify_natural_baseline(directory: Path, manifest: dict, raw: dict) -> None:
    """沿旧producer默认JSON空格序列化核R18身份，纯AST读注册源码，不构造评分器。"""
    baseline = manifest["policy_metadata"]["A"]
    fields = {"registered_name", "source_sha256", "source_manifest", "params", "max_operations", "rule_config", "value_limits", "provider", "policy_id"}
    if set(baseline) != fields or type(baseline["max_operations"]) is not int or baseline["max_operations"] <= 0:
        raise ValueError("真实R18完整材料缺字段")
    identity = {k: v for k,v in baseline.items() if k != "policy_id"}
    historical_json = json.dumps(identity, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    source_path = directory / "r18.py"
    if (baseline["policy_id"] != "research-r18-v2:" + sha(historical_json)
            or str(source_path.resolve()) not in raw or fingerprint(source_path)["sha256"] != baseline["source_sha256"]
            or baseline["rule_config"] != manifest["config"]["rules"] or baseline["value_limits"] != manifest["value_limits"]
            or not baseline["source_manifest"] or any(manifest["source_manifest"].get(k) != v for k,v in baseline["source_manifest"].items())):
        raise ValueError("A标签不是完整材料及真实源码绑定的R18身份")
    registered = directory / "code_snapshot/src/hangma_bot/policy/r18_integrated_positive_v2.py"
    tree = ast.parse(registered.read_text(encoding="utf-8"))
    literals = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {"R18_INTEGRATED_POSITIVE_V2_SHA256", "R18_INTEGRATED_POSITIVE_V2_SOURCE"}:
                literals[node.targets[0].id] = ast.literal_eval(node.value)
    if literals["R18_INTEGRATED_POSITIVE_V2_SHA256"] != baseline["source_sha256"] or literals["R18_INTEGRATED_POSITIVE_V2_SOURCE"].encode() != source_path.read_bytes():
        raise ValueError("A实际R18源码不是冻结注册版本")


def verify_conditioned_inputs(prereg: dict, producer: dict) -> dict:
    """显式绑前定根及136张物理原件；只核文件/牌池，不调用发牌、世界或规则。"""
    for item in prereg["exact_inputs"]:
        path = str((REPO_ROOT / item["path"]).resolve())
        if producer.get(path) != {k:item[k] for k in ("bytes", "sha256")}:
            raise ValueError("条件前定exact_inputs未被producer精确绑定")
    for item in prereg["input_seals"]:
        path = str((REPO_ROOT / item["path"]).resolve())
        if producer.get(path, {}).get("sha256") != item["sha256"]:
            raise ValueError("条件上游首封引用未被producer绑定")
    root_path = (REPO_ROOT / prereg["roots_path"]).resolve()
    if str(root_path) not in producer or not any((REPO_ROOT / i["path"]).resolve() == root_path for i in prereg["exact_inputs"]):
        raise ValueError("前定roots_path没有独立精确输入绑定")
    roots = json.loads(root_path.read_bytes())
    if [r["root_id"] for r in roots] != prereg["root_ids"] or [r["slot"] for r in roots] != prereg["root_profiles"]:
        raise ValueError("条件抽样框越根或profile变化")
    for root in roots:
        path = root_path.parent / (root["root_id"] + "-teacher-origin.json")
        if str(path.resolve()) not in producer:
            raise ValueError("136张条件物理来源原件未冻结")
        teacher = json.loads(path.read_bytes())
        world = teacher["hand"]["initial"]["world_payload"]
        deck = teacher["full_physical_deck"]
        hands, wall, drawn = world["hands"], world["wall"], world["dealer_drawn_tile"]
        physical = [tile for hand in hands for tile in hand] + [drawn] + wall
        if (teacher["sampling_algorithm"] != prereg["sampling_algorithm"] or teacher["native_seed_natural_deal"] is not False
                or teacher["slot"] != root["slot"] or world["seed"] != root["slot"]["seed"]
                or world["match_id"] != root["root_id"] or world["dealer_seat"] != prereg["focal_seat"]
                or world["rules_hash"] != prereg["rules_hash"] or world["rule_config"] != prereg["rule_config"]
                or len(hands) != 4 or any(len(h) != 13 for h in hands) or len(physical) != 136
                or len(deck) != 136 or Counter(physical) != Counter(deck) or Counter(deck) != Counter({t:4 for t in CANONICAL_TILE_ORDER})
                or hands[prereg["focal_seat"]] != root["observation"]["my_hand"] or drawn != root["observation"]["drawn_tile"]
                or len(wall) != root["observation"]["remaining_tile_count"] or root["r18_arrival_prefix"] != []):
            raise ValueError("条件136张牌池/本座初始公开观察绑定不完整")
    return {r["root_id"]:r for r in roots}
