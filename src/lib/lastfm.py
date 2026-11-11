# lastfm.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import json
import logging
import os
import threading
import time
from gettext import gettext as _
from pathlib import Path
from urllib.parse import urlencode

import requests
from gi.repository import GLib, Secret

logger = logging.getLogger(__name__)

API_KEY = "fdad22d7b86a0258ad6a0b8dbafa145d"
API_SECRET = "f83f026124bc1e30a5a074c7e0d3c75e"


# Last.fm takes scrobbles up to two weeks old, and at most 50 per request
MAX_QUEUED_AGE = 14 * 24 * 3600
MAX_BATCH = 50
# Error codes worth trying again later: invalid session (until the user connects
# again), service offline, temporarily unavailable and rate limited
RETRY_ERRORS = {9, 11, 16, 29}


class LastFmError(Exception):
    """An error returned by the Last.fm API.

    code is Last.fm's error code, or None when Last.fm couldn't be reached.
    """

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code

    @property
    def retry(self) -> bool:
        return self.code is None or self.code in RETRY_ERRORS


class LastFmSecretStore:
    """Store the Last.fm user session in the system keyring."""

    def __init__(self) -> None:
        self.schema = Secret.Schema.new(
            "io.github.nokse22.high-tide.lastfm",
            Secret.SchemaFlags.NONE,
            {"service": Secret.SchemaAttributeType.STRING},
        )
        self.attributes = {"service": "lastfm"}
        self.data = {}

        try:
            password = Secret.password_lookup_sync(
                self.schema, self.attributes, None
            )
            if password:
                self.data = json.loads(password)
        except Exception:
            logger.exception("Failed to load Last.fm credentials")

    def save(self, session_key: str, username: str):
        self.data = {
            "session-key": session_key,
            "username": username,
        }
        try:
            Secret.password_store_sync(
                self.schema,
                self.attributes,
                Secret.COLLECTION_DEFAULT,
                "High Tide Last.fm account",
                json.dumps(self.data),
                None,
            )
        except Exception as exc:
            self.data = {}
            message = _("Could not save Last.fm session: {error}").format(
                error=exc
            )
            raise LastFmError(message) from exc

    def clear(self):
        self.data = {}
        try:
            Secret.password_clear_sync(self.schema, self.attributes, None)
        except Exception:
            logger.exception("Failed to clear Last.fm credentials")


class LastFmClient:
    API_URL = "https://ws.audioscrobbler.com/2.0/"
    AUTH_URL = "https://www.last.fm/api/auth/"

    def __init__(self, store: LastFmSecretStore) -> None:
        self.store = store
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.session_key = store.data.get("session-key", "")
        self.username = store.data.get("username", "")
        self.pending_token = None

    @property
    def authenticated(self) -> bool:
        return bool(self.session_key)

    def _signature(self, params: dict) -> str:
        signature = "".join(
            f"{key}{params[key]}"
            for key in sorted(params)
            if key not in ("format", "callback")
        )
        return hashlib.md5(
            f"{signature}{self.api_secret}".encode(), usedforsecurity=False
        ).hexdigest()

    def _request(self, method: str, params: dict, post: bool = False) -> dict:
        request_params = {"method": method, "api_key": self.api_key, **params}
        request_params["api_sig"] = self._signature(request_params)
        request_params["format"] = "json"

        try:
            if post:
                response = requests.post(
                    self.API_URL, data=request_params, timeout=15
                )
            else:
                response = requests.get(
                    self.API_URL, params=request_params, timeout=15
                )
        except requests.RequestException as exc:
            raise LastFmError(str(exc)) from exc

        # Errors come with an error code in the body, also on HTTP errors
        try:
            result = response.json()
        except ValueError:
            result = None
        if isinstance(result, dict) and "error" in result:
            raise LastFmError(
                result.get("message", _("Unknown Last.fm error")), result["error"]
            )
        if not response.ok or not isinstance(result, dict):
            raise LastFmError(f"HTTP {response.status_code}")
        return result

    def begin_authentication(self) -> str:
        result = self._request("auth.getToken", {})
        try:
            self.pending_token = result["token"]
        except KeyError as exc:
            message = _("Last.fm returned an invalid authorization token")
            raise LastFmError(message) from exc
        query = urlencode({"api_key": self.api_key, "token": self.pending_token})
        return f"{self.AUTH_URL}?{query}"

    def finish_authentication(self) -> str:
        if not self.pending_token:
            raise LastFmError(_("Start Last.fm authorization first"))
        result = self._request("auth.getSession", {"token": self.pending_token})
        try:
            session = result["session"]
            self.session_key = session["key"]
            self.username = session["name"]
        except KeyError as exc:
            message = _("Last.fm returned an invalid session")
            raise LastFmError(message) from exc
        self.pending_token = None
        self.store.save(self.session_key, self.username)
        return self.username

    def disconnect(self):
        self.store.clear()
        self.session_key = ""
        self.username = ""
        self.pending_token = None

    @staticmethod
    def _track_params(track) -> dict:
        artist = getattr(getattr(track, "artist", None), "name", "")
        album = getattr(getattr(track, "album", None), "name", "")
        params = {
            "artist": artist,
            "track": getattr(track, "name", ""),
            "duration": str(getattr(track, "duration", 0) or 0),
        }
        if album:
            params["album"] = album
        track_number = getattr(track, "track_num", None)
        if track_number:
            params["trackNumber"] = str(track_number)
        return params

    def update_now_playing(self, track):
        params = {**self._track_params(track), "sk": self.session_key}
        self._request("track.updateNowPlaying", params, post=True)

    def scrobble(self, entries: list[dict]) -> None:
        """Scrobble up to 50 plays, each made by scrobble_entry()"""
        params = {"sk": self.session_key}
        for i, entry in enumerate(entries):
            for key, value in entry.items():
                params[f"{key}[{i}]"] = value
        result = self._request("track.scrobble", params, post=True)
        ignored = result.get("scrobbles", {}).get("@attr", {}).get("ignored", 0)
        if str(ignored) != "0":
            logger.info(f"Last.fm ignored {ignored} scrobble(s)")

    @classmethod
    def scrobble_entry(cls, track, started_at: int) -> dict:
        return {**cls._track_params(track), "timestamp": str(started_at)}


class LastFmQueue:
    """Plays to scrobble, kept in a file until Last.fm takes them"""

    def __init__(self, client: LastFmClient, path: Path | None = None) -> None:
        self.client = client
        self.path = path or Path(
            GLib.get_user_data_dir(), "high-tide", "lastfm-queue.json"
        )
        self.lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            entries = json.loads(self.path.read_text())
            return entries if isinstance(entries, list) else []
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            logger.exception("Couldn't read the Last.fm queue")
            return []

    def _save(self, entries: list[dict]) -> None:
        try:
            if not entries:
                self.path.unlink(missing_ok=True)
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries))
            os.replace(tmp, self.path)
        except OSError:
            logger.exception("Couldn't save the Last.fm queue")

    def send(self, entry: dict | None = None) -> None:
        """Scrobble entry and everything kept from before, keeping what fails"""
        with self.lock:
            entries = self._load() + ([entry] if entry else [])
            oldest = time.time() - MAX_QUEUED_AGE
            entries = [e for e in entries if int(e.get("timestamp", 0)) > oldest]
            if not entries or not self.client.authenticated:
                self._save(entries)
                return
            unsent = []
            for start in range(0, len(entries), MAX_BATCH):
                batch = entries[start : start + MAX_BATCH]
                if unsent:
                    unsent += batch
                    continue
                try:
                    self.client.scrobble(batch)
                except LastFmError as exc:
                    if exc.retry:
                        logger.info(f"Couldn't scrobble, will try again later: {exc}")
                        unsent += batch
                    else:
                        logger.warning(
                            f"Last.fm refused {len(batch)} scrobble(s): {exc}"
                        )
            if unsent and len(entries) > len(unsent):
                logger.info(f"Scrobbled {len(entries) - len(unsent)} play(s)")
            self._save(unsent)

    def clear(self) -> None:
        with self.lock:
            self._save([])


class LastFmScrobbler:
    """Track listening time and submit eligible plays to Last.fm."""

    def __init__(
        self, player, client: LastFmClient, queue: LastFmQueue | None = None
    ) -> None:
        self.player = player
        self.client = client
        self.queue = queue or LastFmQueue(client)
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
                    logger.exception("Last.fm request failed")

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

        # Last.fm's rule: tracks over 30 s, played for half their length or 4 minutes
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
