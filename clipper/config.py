"""Konfiguration laden (config.yaml)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Streamer:
    name: str
    platform: str  # "twitch" oder "kick"
    channel: str
    # Facecam-Bereich als Anteil des Bildes: [x, y, breite, hoehe] (0..1)
    facecam: list[float] | None = None
    # Nur Kick: Chatroom-ID (wird sonst automatisch gesucht)
    kick_chatroom_id: int | None = None
    # false = wird nicht ueberwacht (z. B. solange keine Kampagne laeuft)
    enabled: bool = True

    @property
    def url(self) -> str:
        if self.platform == "kick":
            return f"https://kick.com/{self.channel}"
        return f"https://www.twitch.tv/{self.channel}"


@dataclass
class Detection:
    window_seconds: int = 10          # Zeitfenster fuer "Hype im Chat"
    baseline_minutes: int = 5         # Normalniveau des Chats
    multiplier: float = 3.0           # so viel mehr als normal = Highlight
    min_messages: int = 25            # mindestens so viele Nachrichten im Fenster
    cooldown_seconds: int = 90        # Pause zwischen zwei Clips pro Streamer
    hype_words: list[str] = field(default_factory=lambda: [
        "LUL", "LMAO", "KEKW", "OMEGALUL", "ICANT", "LOL", "CLIP", "W", "WTF",
        "HOLY", "NAH", "💀", "😂",
    ])


@dataclass
class Clip:
    before_seconds: int = 30          # so viel vor dem Hype-Peak
    after_seconds: int = 10           # so viel danach
    width: int = 1080
    height: int = 1920
    facecam_height: int = 640         # Hoehe der Facecam oben (px)
    subtitles: bool = True
    whisper_model: str = "small"      # tiny/base/small/medium
    language: str | None = None       # None = automatisch erkennen


@dataclass
class Config:
    streamers: list[Streamer]
    detection: Detection
    clip: Clip
    output_dir: Path
    buffer_dir: Path
    buffer_minutes: int = 5
    check_interval_seconds: int = 60
    quality: str = "best"


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    streamers = [Streamer(**s) for s in raw.get("streamers", [])]
    streamers = [s for s in streamers if s.enabled]
    if not streamers:
        raise SystemExit("config.yaml: kein Streamer mit 'enabled: true' eingetragen.")
    for s in streamers:
        if s.platform not in ("twitch", "kick"):
            raise SystemExit(f"{s.name}: platform muss 'twitch' oder 'kick' sein.")
        if s.facecam is not None and len(s.facecam) != 4:
            raise SystemExit(f"{s.name}: facecam braucht 4 Werte [x, y, breite, hoehe].")
    return Config(
        streamers=streamers,
        detection=Detection(**raw.get("detection", {})),
        clip=Clip(**raw.get("clip", {})),
        output_dir=Path(raw.get("output_dir", "clips")),
        buffer_dir=Path(raw.get("buffer_dir", "buffer")),
        buffer_minutes=raw.get("buffer_minutes", 5),
        check_interval_seconds=raw.get("check_interval_seconds", 60),
        quality=raw.get("quality", "best"),
    )
