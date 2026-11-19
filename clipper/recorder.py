"""Nimmt einen Livestream als laufenden Puffer aus 10-Sekunden-Stuecken auf."""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

SEGMENT_SECONDS = 10
NAME_FORMAT = "%Y%m%d-%H%M%S"


def check_tools() -> None:
    missing = [t for t in ("ffmpeg", "ffprobe", "streamlink") if shutil.which(t) is None]
    if missing:
        raise SystemExit(f"Fehlt: {', '.join(missing)}. Siehe README, Abschnitt Installation.")


async def is_live(url: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "streamlink", "--json", url,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    return await proc.wait() == 0


def segment_time(path: Path) -> float:
    return datetime.strptime(path.stem, NAME_FORMAT).timestamp()


def segments(directory: Path) -> list[tuple[float, Path]]:
    out = []
    for p in directory.glob("*.ts"):
        try:
            out.append((segment_time(p), p))
        except ValueError:
            continue
    return sorted(out)


class Recorder:
    def __init__(self, name: str, url: str, directory: Path, quality: str, buffer_minutes: int):
        self.name = name
        self.url = url
        self.dir = directory
        self.quality = quality
        self.buffer_seconds = buffer_minutes * 60
        self.dir.mkdir(parents=True, exist_ok=True)

    async def run(self) -> None:
        """Nimmt auf, bis der Stream endet."""
        for old in self.dir.glob("*.ts"):
            old.unlink(missing_ok=True)
        sl = subprocess.Popen(
            ["streamlink", "--twitch-disable-ads", "--stdout", self.url, self.quality],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        ff = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
             "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
             "-reset_timestamps", "1", "-strftime", "1",
             str(self.dir / f"{NAME_FORMAT}.ts")],
            stdin=sl.stdout, stderr=subprocess.DEVNULL,
        )
        sl.stdout.close()  # damit ffmpeg das Ende merkt
        log.info("[%s] Aufnahme laeuft", self.name)
        try:
            while ff.poll() is None:
                self._cleanup()
                await asyncio.sleep(5)
        finally:
            for p in (sl, ff):
                if p.poll() is None:
                    p.terminate()
            log.info("[%s] Aufnahme beendet", self.name)

    def _cleanup(self) -> None:
        cutoff = time.time() - self.buffer_seconds
        for t, p in segments(self.dir)[:-1]:  # das aktuelle Stueck nie loeschen
            if t < cutoff:
                p.unlink(missing_ok=True)
