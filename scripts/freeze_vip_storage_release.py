"""离线重冻研究数据迁移后的包装；保持算法、规则、编译体和原批准身份。"""

from __future__ import annotations

import json
from pathlib import Path

from hangma_bot import bootstrap
from hangma_bot.policy import vip_g37_rf1_release

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"test_room": "test-room", "auto_match": "free-match",
         "test_tournament": "test-tournament", "official_tournament": "official-tournament"}


def freeze_storage_packages() -> list[dict]:
    """核对八个包装只改变源码绑定，写入新版本，已有原件拒绝覆盖。"""
    rows = []
    for family, scopes in (("p0", bootstrap.VIP_S03_RULEFIX_P0_PACKAGE_SCOPES),
                           ("rf1", vip_g37_rf1_release.PACKAGE_SCOPES)):
        for strategy, (mode, _, relative) in scopes.items():
            destination = ROOT / relative
            previous = ROOT / (relative.replace("approved-v5", "approved-v4")
                               if family == "p0" else relative.replace("-v2/", "-v1/"))
            old = json.loads(previous.read_bytes())
            payload = (bootstrap.build_vip_s03_rulefix_p0_manifest(strategy, old["evidence_sha256"])
                       if family == "p0" else bootstrap.build_vip_g37_rf1_manifest(strategy))
            changed = {key for key in set(old) | set(payload) if old.get(key) != payload.get(key)}
            if changed - {"source_manifest", "release_package_id"}:
                raise RuntimeError("迁移包装改变了算法或批准范围：" + str(sorted(changed)))
            if payload["startup_admitted"] is not True:
                raise RuntimeError("迁移包装缺少原真实启动资格")
            prefix = "vip-s03-rulefix-p0-approved-v" if family == "p0" else "vip-g37-rf1-v"
            old_version, new_version = ("4", "5") if family == "p0" else ("1", "2")
            template_name = prefix + new_version + "." + KINDS[mode] + ".example.json"
            template = ROOT / "configs" / template_name
            config = json.loads((ROOT / "configs" / (prefix + old_version + "." + KINDS[mode] + ".example.json")).read_bytes())
            config["expected_policy_release_id"] = payload["release_package_id"]
            for identity in config.get("identities", []):
                identity["expected_policy_release_id"] = payload["release_package_id"]
            rows.append({"manifest": destination, "payload": payload, "template": template, "config": config,
                         "family": family, "mode": mode})
    if any(row["manifest"].exists() or row["template"].exists() for row in rows):
        raise FileExistsError("新包装目录已有原件，拒绝覆盖")
    for row in rows:
        row["manifest"].parent.mkdir(parents=True)
        for path, value in ((row["manifest"], row["payload"]), (row["template"], row["config"])):
            with path.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
    return [{"family": row["family"], "mode": row["mode"],
             "manifest": str(row["manifest"].relative_to(ROOT)),
             "release_package_id": row["payload"]["release_package_id"]} for row in rows]


if __name__ == "__main__":
    print(json.dumps(freeze_storage_packages(), ensure_ascii=False, indent=2))
