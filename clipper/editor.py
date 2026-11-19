"""Schneidet Clips aus dem Puffer und macht daraus 9:16-Videos mit Untertiteln."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from .config import Clip
from .recorder import SEGMENT_SECONDS, segments

log = logging.getLogger(__name__)

_whisper = None


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler:\n{res.stderr[-2000:]}")


def cut_from_buffer(buffer_dir: Path, start: float, end: float, out: Path) -> float:
    """Fuegt die passenden Puffer-Stuecke zusammen. Gibt den Versatz zurueck, ab dem der Clip beginnt."""
    parts = [(t, p) for t, p in segments(buffer_dir) if t + SEGMENT_SECONDS > start and t < end]
    if not parts:
        raise RuntimeError("Keine Aufnahme fuer diesen Zeitraum im Puffer.")
    listfile = out.with_suffix(".txt")
    listfile.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for _, p in parts), encoding="utf-8"
    )
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", str(listfile), "-c", "copy", str(out)])
    listfile.unlink(missing_ok=True)
    return max(0.0, start - parts[0][0])


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def transcribe(video: Path, cfg: Clip, offset: float, duration: float) -> list[tuple[float, float, str]]:
    """Gibt Wortgruppen (start, ende, text) relativ zum Clip-Anfang zurueck."""
    global _whisper
    from faster_whisper import WhisperModel

    if _whisper is None:
        log.info("Lade Whisper-Modell '%s' (beim ersten Mal wird es heruntergeladen) ...", cfg.whisper_model)
        _whisper = WhisperModel(cfg.whisper_model, device="auto", compute_type="int8")

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{offset:.2f}",
              "-i", str(video), "-t", f"{duration:.2f}", "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        segs, _ = _whisper.transcribe(str(wav), language=cfg.language, word_timestamps=True,
                                      vad_filter=True)
        words = [w for s in segs for w in (s.words or [])]

    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3 or (cur[-1].end - cur[0].start) > 1.2 or w.word.strip().endswith((".", "!", "?")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return [(g[0].start, g[-1].end, "".join(w.word for w in g).strip()) for g in groups]


def write_ass(lines: list[tuple[float, float, str]], path: Path, cfg: Clip, y: int) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.width}
PlayResY: {cfg.height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for start, end, text in lines:
        text = text.upper().replace("{", "(").replace("}", ")").replace("\n", " ")
        events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
                      f"{{\\pos({cfg.width // 2},{y})}}{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render_vertical(src: Path, out: Path, cfg: Clip, facecam: list[float] | None,
                    offset: float = 0.0, duration: float | None = None) -> Path:
    """Macht aus dem Querformat-Stream ein 9:16-Video.

    Mit Facecam: Streamer oben, Spiel unten (wie im Video).
    Ohne Facecam: unscharfer Hintergrund, Stream mittig.
    """
    W, H = cfg.width, cfg.height
    if duration is None:
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(src)], capture_output=True, text=True)
        duration = float(probe.stdout.strip()) - offset

    if facecam:
        x, y, w, h = facecam
        top = cfg.facecam_height
        game = H - top
        graph = (
            f"[0:v]split=2[a][b];"
            f"[a]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},"
            f"scale={W}:{top}:force_original_aspect_ratio=increase,crop={W}:{top}[cam];"
            f"[b]crop='min(iw,ih*{W}/{game})':ih,scale={W}:{game},setsar=1[game];"
            f"[cam][game]vstack=inputs=2"
        )
        sub_y = top
    else:
        graph = (
            f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:5[bg];"
            f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        sub_y = int(H * 0.72)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        if cfg.subtitles:
            try:
                lines = transcribe(src, cfg, offset, duration)
                write_ass(lines, tmpdir / "subs.ass", cfg, sub_y)
                graph += ",subtitles=subs.ass"  # relativer Pfad, damit Windows-Pfade kein Problem sind
            except Exception as e:  # noqa: BLE001
                log.warning("Untertitel uebersprungen: %s", e)
        graph += ",format=yuv420p[v]"

        out.parent.mkdir(parents=True, exist_ok=True)
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
              "-ss", f"{offset:.2f}", "-i", str(src.resolve()), "-t", f"{duration:.2f}",
              "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0?",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
              str(out.resolve())], cwd=tmpdir)
    return out
