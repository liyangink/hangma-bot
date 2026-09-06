"""独立本地观战器。

该包只读取已经落盘的审计记录；它不持有 Token、不发送官方请求，
也不被赛事运行模块导入。
"""

from spectator.model import SpectatorRepository

__all__ = ["SpectatorRepository"]
