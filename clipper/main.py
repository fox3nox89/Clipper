"""Einstiegspunkt: python -m clipper <befehl>"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import chat, editor
from .config import Config, Streamer, load
from .detector import HypeDetector
from .recorder import SEGMENT_SECONDS, Recorder, check_tools, is_live

log = logging.getLogger("clipper")


async def make_clip(cfg: Config, s: Streamer, peak: float, score: float, lock: asyncio.Lock) -> None:
    # warten, bis die Sekunden nach dem Peak fertig aufgenommen sind
    await asyncio.sleep(cfg.clip.after_seconds + SEGMENT_SECONDS + 3)
    start, end = peak - cfg.clip.before_seconds, peak + cfg.clip.after_seconds
    stamp = datetime.fromtimestamp(peak).strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = cfg.output_dir / s.name
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / f".{stamp}_raw.ts"
    final = out_dir / f"{stamp}.mp4"
    try:
        offset = editor.cut_from_buffer(cfg.buffer_dir / s.name, start, end, raw)
        async with lock:  # immer nur ein Clip gleichzeitig rendern (CPU)
            log.info("[%s] Rendere Clip %s ...", s.name, final.name)
            await asyncio.to_thread(editor.render_vertical, raw, final, cfg.clip, s.facecam,
                                    offset, end - start)
        final.with_suffix(".json").write_text(json.dumps({
            "streamer": s.name, "platform": s.platform, "channel": s.channel,
            "peak_time": datetime.fromtimestamp(peak).isoformat(), "chat_score": score,
        }, indent=2), encoding="utf-8")
        log.info("[%s] ✅ Clip fertig: %s", s.name, final)
    except Exception as e:  # noqa: BLE001
        log.error("[%s] Clip fehlgeschlagen: %s", s.name, e)
    finally:
        raw.unlink(missing_ok=True)


async def watch_streamer(cfg: Config, s: Streamer, lock: asyncio.Lock) -> None:
    while True:
        if not await is_live(s.url):
            await asyncio.sleep(cfg.check_interval_seconds)
            continue
        log.info("[%s] 🔴 ist live – starte Aufnahme und Chat", s.name)
        detector = HypeDetector(cfg.detection)
        recorder = Recorder(s.name, s.url, cfg.buffer_dir / s.name, cfg.quality, cfg.buffer_minutes)
        if s.platform == "twitch":
            chat_task = asyncio.create_task(chat.twitch_chat(s.channel, detector.add_message))
        else:
            chat_task = asyncio.create_task(chat.kick_chat(s.channel, s.kick_chatroom_id,
                                                           detector.add_message))
        rec_task = asyncio.create_task(recorder.run())
        started = time.time()
        clips: list[asyncio.Task] = []
        while not rec_task.done():
            await asyncio.sleep(1)
            now = time.time()
            peak = detector.tick(now)
            # erst clippen, wenn genug Puffer vor dem Peak da ist
            if peak and now - started > cfg.clip.before_seconds + SEGMENT_SECONDS:
                score = detector.score(now)
                log.info("[%s] 🔥 Hype im Chat (Score %.0f) – Clip wird erstellt", s.name, score)
                clips.append(asyncio.create_task(make_clip(cfg, s, peak, score, lock)))
        chat_task.cancel()
        if clips:
            await asyncio.gather(*clips, return_exceptions=True)
        log.info("[%s] Stream offline", s.name)


async def run(cfg: Config) -> None:
    check_tools()
    lock = asyncio.Lock()
    log.info("Überwache: %s", ", ".join(f"{s.name} ({s.platform})" for s in cfg.streamers))
    await asyncio.gather(*(watch_streamer(cfg, s, lock) for s in cfg.streamers))


def snapshot(source: str, out: Path) -> None:
    """Speichert ein Standbild mit 10%-Raster, um die Facecam-Position abzulesen."""
    grid = "drawgrid=w=iw/10:h=ih/10:t=2:c=red@0.7"
    if source.startswith("http"):
        sl = subprocess.Popen(["streamlink", "--twitch-disable-ads", "--stdout", source, "best"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0", "-frames:v", "1",
                        "-vf", grid, str(out)], stdin=sl.stdout, check=True)
        sl.terminate()
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "5", "-i", source,
                        "-frames:v", "1", "-vf", grid, str(out)], check=True)
    print(f"Gespeichert: {out}\nJedes rote Kästchen = 0.1. Lies x, y, Breite, Höhe der Facecam ab.")


def main() -> None:
    p = argparse.ArgumentParser(prog="clipper", description="Automatische Stream-Clips im Hochformat")
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="Streamer überwachen und automatisch clippen")
    sp = sub.add_parser("snapshot", help="Standbild mit Raster (für die Facecam-Position)")
    sp.add_argument("source", help="Stream-URL oder Videodatei")
    sp.add_argument("-o", "--out", default="snapshot.png")
    rp = sub.add_parser("render", help="Eine lokale Videodatei testweise ins Hochformat bringen")
    rp.add_argument("video")
    rp.add_argument("-o", "--out", default="test_clip.mp4")
    rp.add_argument("--facecam", help="x,y,breite,hoehe z. B. 0.75,0.0,0.25,0.3")
    rp.add_argument("--start", type=float, default=0.0)
    rp.add_argument("--duration", type=float)
    rp.add_argument("--no-subs", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.cmd == "run":
        try:
            asyncio.run(run(load(args.config)))
        except KeyboardInterrupt:
            print("\nBeendet.")
    elif args.cmd == "snapshot":
        snapshot(args.source, Path(args.out))
    elif args.cmd == "render":
        from .config import Clip
        clip_cfg = load(args.config).clip if Path(args.config).exists() else Clip()
        if args.no_subs:
            clip_cfg.subtitles = False
        face = [float(v) for v in args.facecam.split(",")] if args.facecam else None
        editor.render_vertical(Path(args.video), Path(args.out), clip_cfg, face,
                               args.start, args.duration)
        print(f"Fertig: {args.out}")
