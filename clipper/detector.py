"""Erkennt Highlights an ploetzlich viel Aktivitaet im Chat ("Hype im Chat")."""
from __future__ import annotations

import re
import statistics
import time
from collections import deque

from .config import Detection


class HypeDetector:
    def __init__(self, cfg: Detection):
        self.cfg = cfg
        self.events: deque[tuple[float, float]] = deque()  # (zeit, gewicht)
        self.history: deque[float] = deque()  # Fenster-Werte pro Sekunde (Baseline)
        self.last_clip = 0.0
        words = "|".join(re.escape(w) for w in cfg.hype_words)
        self._hype = re.compile(rf"(?:^|\W)(?:{words})(?:\W|$)", re.IGNORECASE)

    def add_message(self, text: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        weight = 2.0 if self._hype.search(text) else 1.0
        self.events.append((now, weight))

    def score(self, now: float) -> float:
        cutoff = now - self.cfg.window_seconds
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
        return sum(w for _, w in self.events)

    def tick(self, now: float | None = None) -> float | None:
        """Einmal pro Sekunde aufrufen. Gibt den Peak-Zeitpunkt zurueck, wenn ein Highlight erkannt wurde."""
        now = time.time() if now is None else now
        current = self.score(now)
        baseline = statistics.median(self.history) if len(self.history) >= 30 else None

        self.history.append(current)
        while len(self.history) > self.cfg.baseline_minutes * 60:
            self.history.popleft()

        if baseline is None:  # erst Normalniveau lernen
            return None
        threshold = max(self.cfg.min_messages, baseline * self.cfg.multiplier)
        if current >= threshold and now - self.last_clip >= self.cfg.cooldown_seconds:
            self.last_clip = now
            return now
        return None
