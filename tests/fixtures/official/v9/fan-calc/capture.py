#!/usr/bin/env python3
"""离线采集官方 fan-calc 金例；模块运行时禁止联网，本脚本仅用于生成测试夹具。

来源：POST https://10.240.169.190:18080/portal/api/tools/fan-calc（免认证）
指南版本：v9（2026-09-03 抓取，规则语义与 v8 一致）
用法：python3 capture.py [输出.jsonl]
"""
import json, ssl, sys, time, urllib.request

BASE = "https://10.240.169.190:18080/portal/api/tools/fan-calc"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # 仅对官方内网自签名证书关闭校验

PLAIN = ["1w","1w","1w","2w","3w","4w","5w","6w","7w","8w","9w","东","东"]

def case(tag, hand, draw, count=0, piao=0, base=1):
    return {"tag": tag, "request": {"hand": hand, "draw": draw,
            "chain": {"count": count, "piao": piao}, "base": base}}

CASES = [
    # 支付公式：平胡随链变化
    case("plain-chain-0-0", PLAIN, "东", 0, 0),
    case("plain-chain-1-0", PLAIN, "东", 1, 0),
    case("plain-chain-2-0", PLAIN, "东", 2, 0),
    case("plain-chain-3-0", PLAIN, "东", 3, 0),
    case("plain-chain-6-3", PLAIN, "东", 6, 3),
    case("plain-chain-1-1", PLAIN, "东", 1, 1),
    case("plain-chain-2-1", PLAIN, "东", 2, 1),
    case("plain-chain-2-2", PLAIN, "东", 2, 2),
    case("plain-chain-3-3", PLAIN, "东", 3, 3),
    case("plain-chain-4-3", PLAIN, "东", 4, 3),
    case("plain-base-2", PLAIN, "东", 0, 0, 2),
    case("plain-base-10", PLAIN, "东", 0, 0, 10),
    # 七对与豪华七对
    case("chiitoi-basic", ["1w","1w","2w","2w","3w","3w","4w","4w","5w","5w","6w","6w","7w"], "7w"),
    case("chiitoi-2lux", ["1w","1w","1w","1w","2w","2w","2w","2w","3w","3w","4w","4w","5w"], "5w"),
    case("chiitoi-3lux-white", ["1w","1w","1w","1w","2w","2w","2w","2w","3w","3w","3w","3w","白"], "4w"),
    case("chiitoi-white-pair", ["1w","1w","2w","2w","3w","3w","4w","4w","5w","5w","6w","6w","白"], "白"),
    # 4 白板倍率（手留）
    case("four-white-kept", ["白","白","白","白","1w","2w","3w","4w","5w","6w","东","东","9w"], "9w"),
    case("three-white-kept-one-piao", ["白","白","白","1w","2w","3w","4w","5w","6w","东","东","9w","8w"], "9w", 1, 1),
    # 财神万能牌替代
    case("wild-complete-run", ["白","1w","2w","3w","4w","5w","6w","7w","8w","9w","东","东","2b"], "3b"),
    case("wild-pair-completes", ["白","1w","2w","3w","4w","5w","6w","7w","8w","9w","2b","3b","东"], "东"),
    # 有财必拷响是否由工具强制（手留财神 + 平胡型）
    case("youcai-plain-hu-shape", ["白","1w","2w","3w","4w","5w","6w","7w","8w","9w","东","东","2b"], "3b", 0, 0),
    # 未胡 / 向听样例
    case("not-hu", ["1w","2w","3w","4w","5w","6w","7w","8w","9w","1b","2b","3b","4b"], "5b"),
    case("tenpai-only-wild-wins", ["1w","1w","2w","2w","3w","3w","4w","4w","5w","5w","6w","6w","7w"], "白"),
    # 边界：白板作刻子/顺子成分的多解
    case("three-white-triplet", ["白","白","白","1w","2w","3w","4w","5w","6w","7w","8w","9w","东"], "东"),
    case("four-white-plus-lux", ["白","白","白","白","1w","1w","1w","2w","2w","2w","3w","3w","3w"], "4w", 3, 3),
]

def main(out_path):
    results = []
    for c in CASES:
        body = json.dumps(c["request"]).encode()
        req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                row = {"tag": c["tag"], "request": c["request"], "response": data}
        except urllib.error.HTTPError as e:
            row = {"tag": c["tag"], "request": c["request"], "http_status": e.code,
                   "response": e.read().decode()[:300]}
        results.append(row)
        print(c["tag"], "->", json.dumps(row.get("response"), ensure_ascii=False)[:160])
        time.sleep(0.15)  # 官方限速 10 次/秒/IP，保守间隔
    with open(out_path, "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("saved", len(results), "cases ->", out_path)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cases.jsonl")
