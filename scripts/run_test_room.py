"""官方测试房间四 Token 启动入口骨架。

实施 Agent 应启动四个隔离子进程，每个子进程复用 ``run_participant.py``。
``config.M`` 是每个身份的同时场数，不是需要创建的 Token 数。
"""


def main() -> None:
    """启动四个测试身份；当前仅冻结入口位置，尚未实现进程编排。"""

    raise NotImplementedError("由测试房间入口实施 Agent 按模块指导文档实现")


if __name__ == "__main__":
    main()

