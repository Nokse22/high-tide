# lastfm.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import json
import logging
from gettext import gettext as _
from pathlib import Path
from urllib.parse import urlencode

import requests
from gi.repository import GLib, Secret

from .scrobbling import ScrobbleQueue, Scrobbler

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

    @staticmethod
    def entry_time(entry: dict) -> int:
        return int(entry.get("timestamp", 0))


class LastFmQueue(ScrobbleQueue):
    """Plays to scrobble, kept in a file until Last.fm takes them"""

    def __init__(self, client: LastFmClient, path: Path | None = None) -> None:
        super().__init__(
            client,
            path or Path(GLib.get_user_data_dir(), "high-tide", "lastfm-queue.json"),
            "Last.fm",
            MAX_BATCH,
            MAX_QUEUED_AGE,
        )


class LastFmScrobbler(Scrobbler):
    """Track listening time and submit eligible plays to Last.fm."""

    def __init__(
        self, player, client: LastFmClient, queue: LastFmQueue | None = None
    ) -> None:
        super().__init__(player, client, queue or LastFmQueue(client))
