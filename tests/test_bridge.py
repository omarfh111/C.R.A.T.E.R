import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from crater_m2.bridge import TelemetryBridge
from crater_m2.codec import encode_frame, decode_frame


async def wait_clients(bridge, expected):
    for _ in range(100):
        if bridge.client_count == expected:
            return
        await asyncio.sleep(.005)
    raise AssertionError("client registration timeout")


def test_actual_websocket_one_canonical_json_per_message(frame):
    async def check():
        async with TelemetryBridge(port=0) as bridge:
            async with connect(bridge.url) as client:
                await wait_clients(bridge, 1)
                decoded = decode_frame(encode_frame(frame))
                await bridge.publish(decoded)
                text = await asyncio.wait_for(client.recv(), 2)
                assert isinstance(text, str)
                assert json.loads(text) == decoded
                assert "receivedAt" not in json.loads(text)
            await wait_clients(bridge, 0)
    asyncio.run(check())


def test_reconnect_replays_last_received_frame(frame):
    async def check():
        async with TelemetryBridge(port=0) as bridge:
            await bridge.publish(frame)
            async with connect(bridge.url) as client:
                assert json.loads(await asyncio.wait_for(client.recv(), 2))["sequence"] == 42
    asyncio.run(check())


def test_wrong_path_rejected():
    async def check():
        async with TelemetryBridge(port=0) as bridge:
            async with connect(bridge.url.replace("/telemetry", "/wrong")) as client:
                with pytest.raises(ConnectionClosed):
                    await asyncio.wait_for(client.recv(), 2)
    asyncio.run(check())


def test_invalid_payload_not_published(frame):
    async def check():
        async with TelemetryBridge(port=0) as bridge:
            frame["extra"] = True
            with pytest.raises(ValueError):
                await bridge.publish(frame)
            assert bridge.latest is None
    asyncio.run(check())


def test_slow_client_queue_is_bounded_and_does_not_stall(frame):
    class SlowClient:
        async def close(self, code, reason):
            self.code = code

    async def check():
        bridge = TelemetryBridge(max_client_queue=1)
        slow = SlowClient()
        queue = asyncio.Queue(maxsize=1)
        bridge.clients[slow] = queue
        await bridge.publish(frame)
        frame["sequence"] += 1
        await bridge.publish(frame)
        await asyncio.sleep(0)
        assert queue.qsize() == 1
        assert bridge.client_count == 0
        assert bridge.slow_clients == 1
        assert slow.code == 1013
    asyncio.run(check())
