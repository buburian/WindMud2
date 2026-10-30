"""最小的 MUD telnet 原型：Big5、Login:、HP100> prompt、chat 廣播。

用法：uv run python -m mud [--port 4000] [--host 0.0.0.0]
指令：chat <話>、quit

原則：收進來的一律當 bytes 處理，收滿一行才 decode。
「坑」標記的地方，就是 Python 寫 telnet 常出錯的點。
"""
