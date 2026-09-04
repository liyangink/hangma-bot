"""策略模块的可捕获异常；应用层据此切换到紧急保底计划。"""

from __future__ import annotations


class PolicyError(Exception):
    """策略失败基类；应用层捕获后必须使用已准备的保底计划。"""


class PolicyTimeoutError(PolicyError):
    """增强计算超过决策预算截止时间；不得继续占用动作窗口。"""
