# lastfm.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import json
import logging
import threading
import time
from urllib.parse import urlencode

import requests
from gi.repository import Secret

logger = logging.getLogger(__name__)


class LastFmError(Exception):
    """An error returned by the Last.fm API."""


class LastFmSecretStore:
    """Store Last.fm credentials and the user session in system keyring."""

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

    def save(self, api_key: str, api_secret: str, session_key: str, username: str):
        self.data = {
            "api-key": api_key,
            "api-secret": api_secret,
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
            raise LastFmError(f"Could not save Last.fm session: {exc}") from exc

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
        self.api_key = store.data.get("api-key", "")
        self.api_secret = store.data.get("api-secret", "")
        self.session_key = store.data.get("session-key", "")
        self.username = store.data.get("username", "")
        self.pending_token = None

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.api_secret and self.session_key)

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
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise LastFmError(str(exc)) from exc

        if "error" in result:
            raise LastFmError(result.get("message", "Unknown Last.fm error"))
        return result

    def begin_authentication(self, api_key: str, api_secret: str) -> str:
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        if not self.api_key or not self.api_secret:
            raise LastFmError("An API key and shared secret are required")

        result = self._request("auth.getToken", {})
        try:
            self.pending_token = result["token"]
        except KeyError as exc:
            message = "Last.fm returned an invalid authorization token"
            raise LastFmError(message) from exc
        query = urlencode({"api_key": self.api_key, "token": self.pending_token})
        return f"{self.AUTH_URL}?{query}"

    def finish_authentication(self) -> str:
        if not self.pending_token:
            raise LastFmError("Start Last.fm authorization first")
        result = self._request("auth.getSession", {"token": self.pending_token})
        try:
            session = result["session"]
            self.session_key = session["key"]
            self.username = session["name"]
        except KeyError as exc:
            raise LastFmError("Last.fm returned an invalid session") from exc
        self.pending_token = None
        self.store.save(
            self.api_key, self.api_secret, self.session_key, self.username
        )
        return self.username

    def disconnect(self):
        self.store.clear()
        self.api_key = ""
        self.api_secret = ""
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

    def scrobble(self, track, started_at: int):
        params = {
            **self._track_params(track),
            "timestamp": str(started_at),
            "sk": self.session_key,
        }
        self._request("track.scrobble", params, post=True)


class LastFmScrobbler:
    """Track listening time and submit eligible plays to Last.fm."""

    def __init__(self, player, client: LastFmClient) -> None:
        self.player = player
        self.client = client
        self.pause_timeout_seconds = 180
        self.track = None
        self.started_at = 0
        self.listened_seconds = 0.0
        self.last_tick = None
        self.paused_since = None
        self.last_position = 0.0
        self.pause_status = False
        self.pause_expired = False
        self.submitted = False
        self.generation = 0

        player.connect("song-changed", self.on_song_changed)
        player.connect("update-slider", self.on_tick)
        player.connect("notify::playing", self.on_playing_changed)

    def set_pause_timeout(self, timeout_seconds: int) -> None:
        self.pause_timeout_seconds = max(0, int(timeout_seconds))

    def _run(self, function, *args):
        generation = self.generation

        def worker():
            try:
                function(*args)
            except LastFmError:
                if generation == self.generation:
                    logger.exception("Last.fm request failed")

        threading.Thread(target=worker, daemon=True).start()

    def on_song_changed(self, *_args):
        self.track = self.player.playing_track
        self.started_at = int(time.time())
        self.listened_seconds = 0.0
        self.last_tick = time.monotonic() if self.player.playing else None
        self.paused_since = time.monotonic() if not self.player.playing else None
        self.last_position = 0.0
        self.pause_status = not self.player.playing
        self.pause_expired = False
        self.submitted = False
        self.generation += 1

        if self.track and self.client.authenticated:
            self._run(self.client.update_now_playing, self.track)

    def on_playing_changed(self, *_args):
        now = time.monotonic()
        if self.player.playing:
            if self.paused_since is not None and self.pause_timeout_seconds > 0:
                if now - self.paused_since >= self.pause_timeout_seconds:
                    self.pause_expired = True
            self.paused_since = None
            self.pause_status = False
            self.last_tick = now
            return

        self.pause_status = True
        self.paused_since = now
        self.last_tick = None

    def on_tick(self, *_args):
        if not self.track:
            return

        if not self.player.playing:
            if (
                self.pause_timeout_seconds > 0
                and self.paused_since is not None
                and not self.pause_expired
            ):
                if time.monotonic() - self.paused_since >= self.pause_timeout_seconds:
                    self.pause_expired = True
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

        duration = getattr(self.track, "duration", 0) or 0
        threshold = min(duration / 2, 240)
        if (
            self.client.authenticated
            and duration > 30
            and not self.submitted
            and not self.pause_expired
            and self.listened_seconds >= threshold
        ):
            self.submitted = True
            self._run(self.client.scrobble, self.track, self.started_at)

    def credentials_changed(self):
        self.generation += 1
        if self.track and self.player.playing and self.client.authenticated:
            self._run(self.client.update_now_playing, self.track)
