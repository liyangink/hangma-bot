#!/usr/bin/env python3
"""主审：先胡损失需要多大番值收益才能抵消——阈值计算器（回应独立复审的工程建议）。

模型（只自摸、零和）：每局毛收入 = P(胡率) x W(每次胡得分)。
保持净分不变而放弃 dP 的胡率，需要：

    (P - dP) x (W + dW) = P x W   =>   dW = P*W*dP / (P - dP)

反过来，已知可获得的 dW，它能买下多少胡率损失：

    dP = dW * P / (P*W + dW)

输入取自 59 房画像（第 46 轮）：我方 P = 0.2619、W = 17.329、均番 1.269；
榜上 P = 0.2544、W = 19.551、均番 1.409。
"""
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

P, W, F = 0.2619, 17.329, 1.269
P2, W2, F2 = 0.2544, 19.551, 1.409


def dw_for_dp(dp, p=P, w=W):
    return float("inf") if dp >= p else p * w * dp / (p - dp)


def dp_for_dw(dw, p=P, w=W):
    return dw * p / (p * w + dw)


def main() -> int:
    print("我方：胡率 %.4f、均胡牌分 %.2f、均番 %.3f、每局毛收入 P*W = %.3f"
          % (P, W, F, P * W))
    print("榜上：胡率 %.4f、均胡牌分 %.2f、均番 %.3f" % (P2, W2, F2))
    print()
    print("## 一、阈值表：放弃 dP 胡率，需要补多少分/次胡")
    print()
    print("| 放弃胡率 | 相对值 | 需要 dW | 相对值 |")
    print("| --- | --- | --- | --- |")
    for dp in (0.001, 0.005, 0.01, 0.02, 0.05, 0.10):
        dw = dw_for_dp(dp)
        print("| %.1f pp | %.1f%% | **%+.3f 分** | %+.1f%% |"
              % (dp * 100, 100 * dp / P, dw, 100 * dw / W))
    print()
    print("**阈值很低：放弃 1 pp 胡率只要 +0.180 分/次胡（约 +0.013 番）就能打平。**")
    print()
    print("## 二、反过来：榜上的番值优势能买下多少胡率损失")
    print()
    dw_ranked = W2 - W
    print("榜上均胡牌分比我方高 %.3f 分；而他们胡率比我方低 %.2f pp。"
          % (dw_ranked, (P - P2) * 100))
    print("把 +%.3f 分/次胡 当收益，它可以买下 **%.2f pp** 的胡率损失。"
          % (dw_ranked, 100 * dp_for_dw(dw_ranked)))
    print()
    print("**结论：这不是一个可以互相兑换的取舍。**")
    print("   他们用 -0.75 pp 的胡率换到了 +2.22 分/次胡，")
    print("   而按本赛制的兑换率，那 2.22 分**值 7.8 pp** 的胡率。")
    print("   => 他们在番值侧是免费的；我们不是「用先胡率买了番值」，而是番值侧真的缺。")
    print()
    print("## 三、回溯核对：本会话测过的「换番值」提案")
    print()
    print("| 轴 | 胡率变化 | 番值变化 | 打平所需 | 判读 | 实测 |")
    print("| --- | --- | --- | --- | --- | --- |")
    p_a, p_b = 1.0, 0.4766
    need_fan = p_a * 1.0 / p_b
    print("| P24 盲弃胡 | 1.000 -> 0.477 | 番 1.000 -> 1.367 | 需 %.3f 番 | **不够（只到 %.0f%%）** | **-10.84 分/桌** |"
          % (need_fan, 100 * 1.3667 / need_fan))
    print("| R17-B 两步后继 | — | — | — | — | -3.29 分/桌 |")
    print("| P31 鸣牌常数 | — | — | — | — | -5.00 分/桌 |")
    print("| P29 不喂牌 | — | — | — | — | -9.20 分/桌 |")
    print("| P5 向听权重 70 | — | — | — | — | +0.28 分/桌（不显著）|")
    print()
    print("## 四、这条阈值应当写进每一份预登记")
    print()
    print("任何面向番值的提案，在写提案时就必须回答：")
    print("1. 它预计掉多少胡率？")
    print("2. 它预计涨多少分/次胡（或多少番）？")
    print("3. 按 dW = P*W*dP/(P-dP)，dW 够不够？")
    print()
    print("本会话的教训：所有听起来合理的番值路线（弃胡追爆头、多鸣牌、不喂牌、两步后继）")
    print("都在第 1 问上就超支了——它们掉的胡率远超它们能挣回的番值。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
