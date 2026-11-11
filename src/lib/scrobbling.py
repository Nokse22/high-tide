# scrobbling.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What scrobbling services share: deciding when a play counts, and keeping the
plays that couldn't be sent in a file until the service takes them.

A service client provides:
    authenticated: whether plays should be sent
    update_now_playing(track): tell the service what's playing
    scrobble_entry(track, started_at): a play as a JSON-friendly dict
    entry_time(entry): when that play started (Unix time)
    scrobble(entries): send plays, raising an exception whose ``retry``
        attribute says whether they should be kept and sent again later
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class ScrobbleQueue:
    """Plays to send, kept in a file until the service takes them"""

    def __init__(
        self,
        client,
        path: Path,
        name: str,
        batch_size: int,
        max_age: int | None = None,
        max_entries: int = 5000,
    ) -> None:
        self.client = client
        self.path = path
        self.name = name
        self.batch_size = batch_size
        self.max_age = max_age
        self.max_entries = max_entries
        self.lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            entries = json.loads(self.path.read_text())
            return entries if isinstance(entries, list) else []
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            logger.exception(f"Couldn't read the {self.name} queue")
            return []

    def _save(self, entries: list[dict]) -> None:
        try:
            if not entries:
                self.path.unlink(missing_ok=True)
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries[-self.max_entries :]))
            os.replace(tmp, self.path)
        except OSError:
            logger.exception(f"Couldn't save the {self.name} queue")

    def send(self, entry: dict | None = None) -> None:
        """Send entry and everything kept from before, keeping what fails"""
        with self.lock:
            entries = self._load() + ([entry] if entry else [])
            if self.max_age is not None:
                oldest = time.time() - self.max_age
                entries = [e for e in entries if self.client.entry_time(e) > oldest]
            if not entries or not self.client.authenticated:
                self._save(entries)
                return
            unsent = []
            for start in range(0, len(entries), self.batch_size):
                batch = entries[start : start + self.batch_size]
                if unsent:
                    unsent += batch
                    continue
                try:
                    self.client.scrobble(batch)
                except Exception as exc:
                    if getattr(exc, "retry", True):
                        logger.info(
                            f"Couldn't send to {self.name}, will try again later: "
                            f"{exc}"
                        )
                        unsent += batch
                    else:
                        logger.warning(
                            f"{self.name} refused {len(batch)} play(s): {exc}"
                        )
            if unsent and len(entries) > len(unsent):
                logger.info(f"Sent {len(entries) - len(unsent)} play(s) to {self.name}")
            self._save(unsent)

    def clear(self) -> None:
        with self.lock:
            self._save([])


class Scrobbler:
    """Track listening time and send the plays that count to a service."""

    def __init__(self, player, client, queue: ScrobbleQueue) -> None:
        self.player = player
        self.client = client
        self.queue = queue
        self.track = None
        self.started_at = 0
        self.listened_seconds = 0.0
        self.last_tick = None
        self.last_position = 0.0
        self.playback_started = False
        self.submitted = False
        self.generation = 0

        player.connect("song-changed", self.on_song_changed)
        player.connect("update-slider", self.on_tick)
        player.connect("notify::playing", self.on_playing_changed)

        # Plays kept from an earlier run
        self._run(self.queue.send)

    def _run(self, function, *args):
        generation = self.generation

        def worker():
            try:
                function(*args)
            except Exception:
                if generation == self.generation:
                    logger.exception(f"{self.queue.name} request failed")

        threading.Thread(target=worker, daemon=True).start()

    def on_song_changed(self, *_args):
        self.track = self.player.playing_track
        self.started_at = int(time.time())
        self.listened_seconds = 0.0
        self.last_tick = time.monotonic() if self.player.playing else None
        self.last_position = 0.0
        self.playback_started = self.player.playing
        self.submitted = False
        self.generation += 1

        if self.track and self.playback_started and self.client.authenticated:
            self._run(self.client.update_now_playing, self.track)

    def on_playing_changed(self, *_args):
        if not self.player.playing:
            self.last_tick = None
            return
        if self.track and not self.playback_started:
            self.playback_started = True
            self.started_at = int(time.time())
            if self.client.authenticated:
                self._run(self.client.update_now_playing, self.track)
        self.last_tick = time.monotonic()

    def on_tick(self, *_args):
        if not self.track or not self.player.playing:
            return

        now = time.monotonic()
        position = self.player.query_position(default=0) / 1_000_000_000

        # A backwards jump to the beginning while repeating the same track is a new play
        if position + 2 < self.last_position and position < 5:
            self.on_song_changed()
            return

        if self.last_tick is not None:
            self.listened_seconds += min(now - self.last_tick, 2.0)
        self.last_tick = now
        self.last_position = position

        # Last.fm's and ListenBrainz's rule: tracks over 30 s, played for half
        # their length or 4 minutes
        duration = getattr(self.track, "duration", 0) or 0
        threshold = min(duration / 2, 240)
        if (
            self.client.authenticated
            and duration > 30
            and not self.submitted
            and self.listened_seconds >= threshold
        ):
            self.submitted = True
            entry = self.client.scrobble_entry(self.track, self.started_at)
            self._run(self.queue.send, entry)

    def credentials_changed(self):
        self.generation += 1
        if not self.client.authenticated:
            # The kept plays belong to the account that was disconnected
            self._run(self.queue.clear)
            return
        self._run(self.queue.send)
        if self.track and self.player.playing:
            self._run(self.client.update_now_playing, self.track)
