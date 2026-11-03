"""定時器：tick loop 和戰鬥 loop 共用的「每隔幾秒做一次」。"""
import asyncio


async def every(seconds, step):
    """每隔 seconds 秒呼叫一次 step()，step() 回傳 False 就停。

    照 loop.time() 排下一次的時間，不會越跑越慢；某一次做太久、已經過了下一次的時間，
    就從現在重新算，不追趕（跟 C 版一樣）。step() 是普通函式，要很快做完，不能卡住。
    """
    loop = asyncio.get_running_loop()
    next_time = loop.time() + seconds
    while True:
        await asyncio.sleep(max(0.0, next_time - loop.time()))
        if step() is False:
            return
        next_time += seconds
        if next_time <= loop.time():
            next_time = loop.time() + seconds


def cancel(task):
    """停掉 task。在 task 自己裡面呼叫時不停，讓它自己跑完結束。"""
    if task is None or task.done():
        return
    try:
        current = asyncio.current_task()
    except RuntimeError:                    # 沒有在跑的 asyncio（例如同步的測試裡重新載入區域）
        current = None
    if task is not current:
        task.cancel()
