"""为已冻结的拒绝取证源码生成窄修复；不启动玩家、不修改旧门。

输入必须逐字节匹配第19房实际运行取证模块，避免给未知版本套补丁。
这里只准备离线取证模块，发布或新运行根还须单独完成来源和生命周期门。
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path


BASELINE_SHA256 = '501d62bfed009371e2efd2dfe8d18ff78d809360500fc2815cfebca20de62e18'
OLD_GUARD = "or refreshed.get('phase') == old_window[3]"


def is_other_seat_draw(snapshot: dict, old_window: tuple) -> bool:
    """仅确认同一摸牌相位已换成其他有效座位，不据本机时钟推断超时。

本函数只补充相位关闭的座位条件；完整应用时序、旧合法动作、唯一提交
与独立新窗成功由原 prove 继续逐项核验。布尔值不能冒充座位整数。
"""
    if len(old_window) != 5 or old_window[3] != 'draw':
        return False
    seat, turn = old_window[4], snapshot.get('turn')
    return (snapshot.get('phase') == 'draw' and type(seat) is int
            and 0 <= seat < 4 and type(turn) is int and 0 <= turn < 4 and turn != seat)


def repaired_source(source: bytes) -> bytes:
    """生成独立源码；版本不符或补丁定位不唯一时报错，不改输入文件。"""
    if hashlib.sha256(source).hexdigest() != BASELINE_SHA256:
        raise ValueError('拒绝取证来源不是已冻结的第19房版本')
    text = source.decode('utf-8')
    if text.count(OLD_GUARD) != 1:
        raise ValueError('相位关闭守卫定位不唯一')
    replacement = ("or (refreshed.get('phase') == old_window[3] "
                   "and not is_other_seat_draw(refreshed, old_window))")
    return (text.replace(OLD_GUARD, replacement, 1)
            + '\n\n' + inspect.getsource(is_other_seat_draw)).encode('utf-8')


def main() -> None:
    """只写新文件及来源收据；已有目标拒绝覆盖，无网络或赛事副作用。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    receipt_path = args.out.with_suffix('.receipt.json')
    if args.out.exists() or receipt_path.exists():
        raise FileExistsError('不覆盖既有取证模块或收据')
    source = args.source.read_bytes()
    result = repaired_source(source)
    with args.out.open('xb') as stream:
        stream.write(result)
    receipt = {'schema': 'closed-discard-readonly-repair/1',
               'baseline_sha256': BASELINE_SHA256,
               'repaired_sha256': hashlib.sha256(result).hexdigest(),
               'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'source': str(args.source.resolve()), 'out': str(args.out.resolve()),
               'read_only_original_no_activation': True, 'production_admission': False}
    with receipt_path.open('x') as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
