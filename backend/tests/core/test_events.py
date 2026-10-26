import asyncio
import threading

from aura.core.events import EventBus


async def _collect(bus: EventBus, key: str, after: int = 0, heartbeat_s: float = 5.0) -> list:
    out = []
    async for event in bus.subscribe(key, after, heartbeat_s=heartbeat_s):
        out.append(event)
    return out


async def test_replay_after_last_event_id():
    bus = EventBus()
    for i in range(5):
        bus.publish("k", "step", {"i": i})
    bus.close("k")
    events = await _collect(bus, "k", after=3)
    assert [e.seq for e in events] == [4, 5]
    assert [e.data["i"] for e in events] == [3, 4]


async def test_live_events_from_another_thread_wake_subscribers():
    bus = EventBus()

    def publisher():
        for i in range(3):
            bus.publish("live", "tick", {"i": i})
        bus.close("live")

    task = asyncio.create_task(_collect(bus, "live"))
    await asyncio.sleep(0.05)
    threading.Thread(target=publisher).start()
    events = await asyncio.wait_for(task, timeout=5)
    assert [e.data["i"] for e in events] == [0, 1, 2]


async def test_idle_stream_yields_heartbeats():
    bus = EventBus()
    beats = []

    async def watch():
        async for event in bus.subscribe("idle", heartbeat_s=0.05):
            beats.append(event)
            if len(beats) == 3:
                return

    await asyncio.wait_for(watch(), timeout=2)
    assert beats == [None, None, None]


async def test_publishing_after_close_is_ignored():
    bus = EventBus()
    bus.publish("c", "a")
    bus.close("c")
    assert bus.publish("c", "b") == 1
    assert [e.type for e in await _collect(bus, "c")] == ["a"]
