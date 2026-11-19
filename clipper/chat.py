"""Chat mitlesen (anonym, kein Login noetig).

Jede Funktion ruft `on_message(text)` fuer jede Chatnachricht auf und laeuft,
bis sie abgebrochen wird. Bei Verbindungsabbruch wird neu verbunden.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Callable

log = logging.getLogger(__name__)

OnMessage = Callable[[str], None]


async def twitch_chat(channel: str, on_message: OnMessage) -> None:
    channel = channel.lower()
    while True:
        try:
            reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
            nick = f"justinfan{random.randint(10000, 99999)}"
            writer.write(f"NICK {nick}\r\nJOIN #{channel}\r\n".encode())
            await writer.drain()
            log.info("[%s] Twitch-Chat verbunden", channel)
            while True:
                line = await reader.readline()
                if not line:
                    raise ConnectionError("Verbindung geschlossen")
                text = line.decode("utf-8", "ignore").strip()
                if text.startswith("PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                elif " PRIVMSG " in text:
                    on_message(text.split(" :", 1)[-1])
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] Twitch-Chat getrennt (%s), neuer Versuch in 10 s", channel, e)
            await asyncio.sleep(10)


# Oeffentlicher Pusher-Key, den kick.com im eigenen Web-Client nutzt.
KICK_PUSHER = (
    "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
    "?protocol=7&client=js&version=8.4.0&flash=false"
)


async def kick_chatroom_id(channel: str) -> int:
    """Chatroom-ID ueber die Kick-API holen (kann von Cloudflare blockiert werden)."""
    import urllib.request

    def fetch() -> int:
        req = urllib.request.Request(
            f"https://kick.com/api/v2/channels/{channel}",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return int(json.load(r)["chatroom"]["id"])

    return await asyncio.to_thread(fetch)


async def kick_chat(channel: str, chatroom_id: int | None, on_message: OnMessage) -> None:
    import websockets

    if chatroom_id is None:
        try:
            chatroom_id = await kick_chatroom_id(channel)
        except Exception as e:  # noqa: BLE001
            log.error(
                "[%s] Kick-Chatroom-ID nicht gefunden (%s). Trage 'kick_chatroom_id' "
                "in config.yaml ein (siehe README).", channel, e,
            )
            return
    while True:
        try:
            async with websockets.connect(KICK_PUSHER) as ws:
                await ws.send(json.dumps({
                    "event": "pusher:subscribe",
                    "data": {"auth": "", "channel": f"chatrooms.{chatroom_id}.v2"},
                }))
                log.info("[%s] Kick-Chat verbunden", channel)
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("event") == "pusher:ping":
                        await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                    elif msg.get("event", "").endswith("ChatMessageEvent"):
                        data = json.loads(msg["data"])
                        on_message(data.get("content", ""))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] Kick-Chat getrennt (%s), neuer Versuch in 10 s", channel, e)
            await asyncio.sleep(10)
