"""离线冻结P0 v4与RF1独立四模式包；不读Token、不启动会话、不填批准。"""

import argparse
import json
from pathlib import Path

from hangma_bot import bootstrap
from hangma_bot.policy import vip_g37_rf1_release

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"test_room": "test-room", "auto_match": "free-match",
         "test_tournament": "test-tournament", "official_tournament": "official-tournament"}


def _save(path: Path, value) -> None:
    """只写新目录/新模板，已有文件拒绝覆盖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _config(previous: Path, *, strategy: str, package_id: str, display: str) -> dict:
    """保留既有隔离/SSE/时限字段，仅换可选策略和其明确包ID。"""
    config = json.loads(previous.read_bytes())
    if "token" in config:
        raise ValueError("模板不得包含Token原文")
    config["strategy"] = strategy
    config["expected_policy_release_id"] = package_id
    if config.get("mode") == "test_room":
        for identity in config["identities"]:
            identity["strategy"] = strategy
            identity["expected_policy_release_id"] = package_id
        config["audit_root"] = "artifacts/sessions/" + display + "/test-room/audit"
    else:
        config["audit_root"] = "artifacts/sessions/" + display + "/" + strategy + "/audit"
    return config


def freeze_p0_v4() -> list[dict]:
    """只重冻包装源码清单；核心CID、公式、编译及原P0批准须与v3相同。"""
    prepared = []
    for strategy, (mode, _, path) in bootstrap.VIP_S03_RULEFIX_P0_PACKAGE_SCOPES.items():
        destination = ROOT / path
        previous = ROOT / path.replace("approved-v4", "approved-v3")
        old = json.loads(previous.read_bytes())
        payload = bootstrap.build_vip_s03_rulefix_p0_manifest(strategy, old["evidence_sha256"])
        for key in ["candidate_identity", "source_sha256", "compiled_runtime", "qualification", "startup_admitted",
                    "strength_admission", "params", "rules_source_hash", "hand_math"]:
            if payload[key] != old[key]:
                raise RuntimeError("P0包装重冻不得改变原批准或核心: " + key)
        prepared.append({"path": destination, "payload": payload, "old_path": previous, "mode": mode})
    if any(row["path"].exists() for row in prepared):
        raise FileExistsError("P0 v4已有原件，禁止覆盖")
    for row in prepared:
        _save(row["path"], row["payload"])
        kind = KINDS[row["mode"]]
        old_config = ROOT / "configs" / ("vip-s03-rulefix-p0-approved-v3." + kind + ".example.json")
        _save(ROOT / "configs" / ("vip-s03-rulefix-p0-approved-v4." + kind + ".example.json"),
              _config(old_config, strategy=row["payload"]["strategy"], package_id=row["payload"]["release_package_id"], display="T110-S03-P0"))
    return [{"manifest": str(row["path"]), "release_package_id": row["payload"]["release_package_id"],
             "P0_original_CID_and_approval_preserved": True} for row in prepared]


def freeze_rf1(draft_directory: Path | None = None) -> list[dict]:
    """草案只写指定新目录；正式作用域必须已有真实独立启动批准。"""
    prepared = []
    for strategy, (mode, _, path) in vip_g37_rf1_release.PACKAGE_SCOPES.items():
        payload = bootstrap.build_vip_g37_rf1_manifest(strategy)
        old_config = ROOT / "configs" / ("vip-s03-rulefix-p0-approved-v3." + KINDS[mode] + ".example.json")
        if draft_directory is None and payload["startup_admitted"] is not True:
            raise RuntimeError("RF1缺真实批准；请用--draft-dir保存草案，不占用正式包路径")
        destination = ROOT / path if draft_directory is None else draft_directory / mode / "manifest.json"
        config_directory = ROOT / "configs" if draft_directory is None else draft_directory / "configs"
        prepared.append({"path": destination, "payload": payload,
            "config_path": config_directory / ("vip-g37-rf1-v1." + KINDS[mode] + ".example.json"),
            "config": _config(old_config, strategy=strategy, package_id=payload["release_package_id"], display="G37-RF1")})
    if any(row["path"].exists() or row["config_path"].exists() for row in prepared):
        raise FileExistsError("RF1已有原件，批准更新应另派生版本，不覆盖")
    for row in prepared:
        _save(row["path"], row["payload"]); _save(row["config_path"], row["config"])
    return [{"manifest": str(row["path"]), "release_package_id": row["payload"]["release_package_id"],
             "startup_admitted": row["payload"]["startup_admitted"], "strength_admission": False} for row in prepared]


def main() -> None:
    """显式离线冻结单一系列；没有任何比赛/API入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", choices=["p0-v4", "rf1"])
    parser.add_argument("--draft-dir", type=Path, help="RF1草案专用的新目录，正常启动仍拒绝草案")
    args = parser.parse_args()
    if args.family == "p0-v4" and args.draft_dir is not None:
        parser.error("--draft-dir仅供RF1草案")
    result = freeze_p0_v4() if args.family == "p0-v4" else freeze_rf1(args.draft_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
