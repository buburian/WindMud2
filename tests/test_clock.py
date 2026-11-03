import asyncio
import time

from mud.clock import cancel, every


def test_every_keeps_its_interval():
    # 照 loop.time() 排時間：跑 10 次大約就是 10 個間隔，不會越跑越慢
    async def main():
        loop = asyncio.get_running_loop()
        times = []

        def step():
            times.append(loop.time())
            return len(times) < 10

        start = loop.time()
        await every(0.02, step)
        return start, times

    start, times = asyncio.run(main())
    assert len(times) == 10
    assert 0.2 <= times[-1] - start < 0.3


def test_every_does_not_catch_up():
    # 有一次做太久（超過好幾個間隔），下一次從現在重新算，不會連續補跑好幾次
    async def main():
        loop = asyncio.get_running_loop()
        times = []

        def step():
            times.append(loop.time())
            if len(times) == 1:
                time.sleep(0.1)             # 故意卡住 10 個間隔
            return len(times) < 3

        await every(0.01, step)
        return times

    times = asyncio.run(main())
    assert times[1] - times[0] >= 0.1 + 0.01 * 0.9


def test_every_stops_when_step_returns_false():
    calls = []

    async def main():
        await every(0.001, lambda: calls.append(1) or len(calls) < 3)

    asyncio.run(asyncio.wait_for(main(), timeout=1))
    assert len(calls) == 3


def test_cancel_does_not_stop_the_task_it_is_called_in():
    # 在 task 自己裡面呼叫 cancel()：不停，讓它自己跑完
    async def main():
        async def job():
            cancel(asyncio.current_task())
            await asyncio.sleep(0)
            return "跑完了"

        return await asyncio.create_task(job())

    assert asyncio.run(main()) == "跑完了"


def test_cancel_stops_other_tasks():
    async def main():
        task = asyncio.create_task(asyncio.sleep(10))
        await asyncio.sleep(0)
        cancel(task)
        await asyncio.sleep(0)
        return task.cancelled()

    assert asyncio.run(main())
