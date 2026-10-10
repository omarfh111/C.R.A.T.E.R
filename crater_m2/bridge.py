"""Local station bridge: decoded canonical JSON -> M3 WebSocket endpoint."""

import asyncio
import json
import re

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from .contract import validate_frame


class TelemetryBridge:
    def __init__(self, host="127.0.0.1", port=8765, *, max_client_queue=32):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("bridge binds only to loopback")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("invalid port")
        if type(max_client_queue) is not int or max_client_queue < 1:
            raise ValueError("positive client queue limit required")
        self.host, self.port = host, port
        self.max_client_queue = max_client_queue
        self.clients = {}
        self.latest = None
        self.slow_clients = 0
        self._close_tasks = set()
        self.server = None

    @property
    def client_count(self):
        return len(self.clients)

    @property
    def url(self):
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"ws://{host}:{self.port}/telemetry"

    async def __aenter__(self):
        self.server = await serve(self._handle, self.host, self.port,
                                  origins=[None, re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?")],
                                  max_size=65536, write_limit=32768, close_timeout=1)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()
        if self._close_tasks:
            await asyncio.gather(*self._close_tasks, return_exceptions=True)

    async def _handle(self, websocket):
        if websocket.request.path != "/telemetry":
            await websocket.close(1008, "Use /telemetry")
            return
        queue = asyncio.Queue(maxsize=self.max_client_queue)
        self.clients[websocket] = queue
        if self.latest is not None:
            queue.put_nowait(self.latest)

        async def send_messages():
            try:
                while True:
                    await websocket.send(await queue.get())
            except ConnectionClosed:
                return

        sender = asyncio.create_task(send_messages())
        closed = asyncio.create_task(websocket.wait_closed())
        try:
            await asyncio.wait((sender, closed), return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.clients.pop(websocket, None)
            sender.cancel()
            closed.cancel()
            await asyncio.gather(sender, closed, return_exceptions=True)

    async def publish(self, frame):
        text = json.dumps(validate_frame(frame), separators=(",", ":"), allow_nan=False)
        self.latest = text
        for client, queue in list(self.clients.items()):
            try:
                queue.put_nowait(text)
            except asyncio.QueueFull:
                self.clients.pop(client, None)
                self.slow_clients += 1
                task = asyncio.create_task(client.close(1013, "Telemetry consumer too slow; reconnect"))
                self._close_tasks.add(task)
                task.add_done_callback(self._close_tasks.discard)
