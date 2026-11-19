# Clipper – automatische Stream-Clips im Hochformat

Überwacht Twitch- und Kick-Streamer. Sobald im Chat plötzlich viel los ist
(„Hype im Chat“), schneidet das Tool automatisch einen Clip:

- **Hochformat 1080×1920** (TikTok, Reels, Shorts)
- **Streamer oben, Spiel unten**
- **Untertitel drauf** (automatisch per Whisper, läuft lokal und kostenlos)

Die fertigen Clips landen in `clips/<streamer>/`. Hochladen und den Link bei der
Kampagne einreichen machst du selbst. So bleibt dein Konto sicher, denn TikTok,
Instagram und YouTube sperren automatisierte Massen-Uploads gerne.

## Wichtig vorher

- **Clippe nur Streamer mit einer offiziellen Clipping-Kampagne** (z. B. auf
  contentrewards.com). Melde dich dort an, lies die Regeln (Format, Hashtags,
  Mindestlänge) und reiche deine Video-Links ein. Ohne Kampagne verletzt du
  Urheberrechte und bekommst kein Geld.
- Bezahlt wird nach Aufrufen (oft um 1–2 $ pro 1.000). Der Verdienst hängt davon
  ab, ob deine Clips Reichweite bekommen. Das Tool garantiert keine Einnahmen.
- Das Tool muss laufen, während die Streamer live sind. Lass es also auf deinem
  PC oder einem kleinen Server laufen.

## Installation (einmalig)

1. **Python 3.10+** installieren: <https://www.python.org/downloads/>
   (Windows: beim Installieren „Add Python to PATH“ anhaken)
2. **ffmpeg** installieren:
   - Windows: `winget install Gyan.FFmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
3. Im Projektordner ein Terminal öffnen und ausführen:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Mac/Linux:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

   Damit wird auch `streamlink` installiert, das die Streams aufnimmt.

## Einrichten

1. `config.example.yaml` kopieren und in `config.yaml` umbenennen.
2. Deine Streamer eintragen (`platform: twitch` oder `kick`, `channel` = Name aus der URL).
3. **Facecam-Position festlegen.** Sie ist bei jedem Streamer anders. Während der
   Streamer live ist:

   ```bash
   python -m clipper snapshot https://www.twitch.tv/lacy
   ```

   Öffne `snapshot.png`. Das rote Raster teilt das Bild in Zehntel. Lies ab, wo
   die Facecam ist, z. B. links oben, 3 Kästchen breit und 3 hoch:
   `facecam: [0.0, 0.0, 0.3, 0.3]`.
   Ohne `facecam` gibt es einen unscharfen Hintergrund mit dem Stream in der Mitte.
4. **Testen**, ohne auf einen Stream zu warten, mit einem beliebigen
   heruntergeladenen Stream-Video:

   ```bash
   python -m clipper render mein_vod.mp4 --facecam 0.0,0.0,0.3,0.3 --start 60 --duration 30
   ```

   Danach `test_clip.mp4` ansehen und die Facecam-Werte anpassen, bis es passt.

## Starten

```bash
python -m clipper run
```

Das Tool prüft jede Minute, wer live ist. Für jeden Live-Streamer gilt:

1. Die letzten 5 Minuten des Streams werden laufend zwischengespeichert (`buffer/`).
2. Der Chat wird anonym mitgelesen (kein Login nötig).
3. Kommen plötzlich viel mehr Nachrichten als normal, besonders mit „KEKW“,
   „LMAO“, „💀“ usw., wird ein Clip erstellt: 30 s vor bis 10 s nach dem Peak.
4. Die Untertitel werden erzeugt und der Clip als `.mp4` gespeichert.

Beenden mit `Strg + C`.

## Feineinstellung (`config.yaml`)

| Einstellung | Wirkung |
|---|---|
| `detection.multiplier` | Kleiner = mehr Clips, größer = nur die krassesten Momente |
| `detection.min_messages` | Bei kleinen Streams senken (z. B. 8) |
| `detection.cooldown_seconds` | Mindestabstand zwischen Clips |
| `detection.hype_words` | Wörter/Emotes, die doppelt zählen |
| `clip.before_seconds` / `after_seconds` | Länge des Clips |
| `clip.whisper_model` | `tiny` = schnell, `medium` = genauere Untertitel (braucht mehr Leistung) |
| `quality` | z. B. `720p60`, wenn dein PC beim Rendern nicht hinterherkommt |

## Probleme

- **„Fehlt: ffmpeg …“**: ffmpeg ist nicht installiert oder nicht im PATH. Danach das Terminal neu öffnen.
- **Kick-Chat verbindet nicht**: Kick blockiert manchmal die automatische Suche.
  Öffne `https://kick.com/api/v2/channels/<name>` im Browser, suche `"chatroom":{"id": …}`
  und trage die Zahl als `kick_chatroom_id` ein.
- **Es kommen keine Clips**: Das Tool lernt in den ersten 30 Sekunden das normale
  Chat-Tempo. Danach `multiplier` oder `min_messages` senken.
- **Untertitel fehlen**: Beim ersten Clip lädt Whisper das Sprachmodell herunter
  (einige hundert MB). Dafür brauchst du eine Internetverbindung.
