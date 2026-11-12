# listenbrainz.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sending listens to ListenBrainz (https://listenbrainz.org).

Users connect with the user token from their ListenBrainz settings page; there's
no app registration. API: https://listenbrainz.readthedocs.io/en/latest/users/api/
"""

import json
import logging
from gettext import gettext as _
from pathlib import Path

import requests
from gi.repository import GLib, Secret

from .scrobbling import ScrobbleQueue, Scrobbler

logger = logging.getLogger(__name__)

API_URL = "https://api.listenbrainz.org/1"
SETTINGS_URL = "https://listenbrainz.org/settings/"
# ListenBrainz takes up to 1000 listens per request, and listens of any age
MAX_BATCH = 1000


class ListenBrainzError(Exception):
    """An error from ListenBrainz.

    status is the HTTP status, or None when ListenBrainz couldn't be reached.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retry(self) -> bool:
        # Not reachable, invalid token (until the user connects again), rate
        # limited or a server error: send again later. Other errors won't go away.
        return self.status is None or self.status in (401, 429) or self.status >= 500


class ListenBrainzSecretStore:
    """Store the ListenBrainz user token in the system keyring."""

    def __init__(self) -> None:
        self.schema = Secret.Schema.new(
            "io.github.nokse22.high-tide.listenbrainz",
            Secret.SchemaFlags.NONE,
            {"service": Secret.SchemaAttributeType.STRING},
        )
        self.attributes = {"service": "listenbrainz"}
        self.data = {}

        try:
            password = Secret.password_lookup_sync(self.schema, self.attributes, None)
            if password:
                self.data = json.loads(password)
        except Exception:
            logger.exception("Failed to load the ListenBrainz token")

    def save(self, token: str, username: str) -> None:
        self.data = {"token": token, "username": username}
        try:
            Secret.password_store_sync(
                self.schema,
                self.attributes,
                Secret.COLLECTION_DEFAULT,
                "High Tide ListenBrainz account",
                json.dumps(self.data),
                None,
            )
        except Exception as exc:
            self.data = {}
            message = _("Could not save the ListenBrainz token: {error}").format(
                error=exc
            )
            raise ListenBrainzError(message) from exc

    def clear(self) -> None:
        self.data = {}
        try:
            Secret.password_clear_sync(self.schema, self.attributes, None)
        except Exception:
            logger.exception("Failed to clear the ListenBrainz token")


class ListenBrainzClient:
    def __init__(self, store: ListenBrainzSecretStore, version: str = "") -> None:
        self.store = store
        self.version = version
        self.token = store.data.get("token", "")
        self.username = store.data.get("username", "")

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    def _request(self, method: str, path: str, token: str, body=None) -> dict:
        try:
            response = requests.request(
                method,
                f"{API_URL}/{path}",
                headers={"Authorization": f"Token {token}"},
                json=body,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise ListenBrainzError(str(exc)) from exc

        try:
            result = response.json()
        except ValueError:
            result = {}
        if not response.ok:
            message = result.get("error") if isinstance(result, dict) else None
            raise ListenBrainzError(
                message or f"HTTP {response.status_code}", response.status_code
            )
        return result if isinstance(result, dict) else {}

    def connect(self, token: str) -> str:
        """Check a user token and save it. Returns the user name."""
        token = token.strip()
        if not token:
            raise ListenBrainzError(_("Enter your user token"))
        result = self._request("GET", "validate-token", token)
        if not result.get("valid"):
            raise ListenBrainzError(_("ListenBrainz doesn't accept this token"))
        username = result.get("user_name", "")
        self.store.save(token, username)
        self.token = token
        self.username = username
        return username

    def disconnect(self) -> None:
        self.store.clear()
        self.token = ""
        self.username = ""

    def _track_metadata(self, track) -> dict:
        artists = [a.name for a in (getattr(track, "artists", None) or []) if a.name]
        artist = getattr(getattr(track, "artist", None), "name", "") or ", ".join(
            artists
        )
        album = getattr(getattr(track, "album", None), "name", "")
        info = {
            "media_player": "High Tide",
            "submission_client": "High Tide",
            "music_service": "tidal.com",
            "music_service_name": "TIDAL",
        }
        if self.version:
            info["media_player_version"] = self.version
            info["submission_client_version"] = self.version
        if artists:
            info["artist_names"] = artists
        if getattr(track, "share_url", None):
            info["origin_url"] = track.share_url
        if getattr(track, "isrc", None):
            info["isrc"] = track.isrc
        if getattr(track, "duration", None):
            info["duration_ms"] = int(track.duration) * 1000
        if getattr(track, "track_num", None):
            info["tracknumber"] = track.track_num
        metadata = {
            "artist_name": artist,
            "track_name": track.name,
            "additional_info": info,
        }
        if album:
            metadata["release_name"] = album
        return metadata

    def update_now_playing(self, track) -> None:
        body = {
            "listen_type": "playing_now",
            "payload": [{"track_metadata": self._track_metadata(track)}],
        }
        self._request("POST", "submit-listens", self.token, body)

    def scrobble_entry(self, track, started_at: int) -> dict:
        return {
            "listened_at": started_at,
            "track_metadata": self._track_metadata(track),
        }

    @staticmethod
    def entry_time(entry: dict) -> int:
        return int(entry.get("listened_at", 0))

    def scrobble(self, entries: list[dict]) -> None:
        """Send up to 1000 listens, each made by scrobble_entry()"""
        body = {
            "listen_type": "single" if len(entries) == 1 else "import",
            "payload": entries,
        }
        result = self._request("POST", "submit-listens", self.token, body)
        logger.debug(f"ListenBrainz: {result}")


class ListenBrainzQueue(ScrobbleQueue):
    """Listens kept in a file until ListenBrainz takes them"""

    def __init__(self, client: ListenBrainzClient, path: Path | None = None) -> None:
        super().__init__(
            client,
            path
            or Path(GLib.get_user_data_dir(), "high-tide", "listenbrainz-queue.json"),
            "ListenBrainz",
            MAX_BATCH,
        )


class ListenBrainzScrobbler(Scrobbler):
    """Track listening time and submit the listens that count to ListenBrainz."""

    def __init__(
        self,
        player,
        client: ListenBrainzClient,
        queue: ListenBrainzQueue | None = None,
    ) -> None:
        super().__init__(player, client, queue or ListenBrainzQueue(client))
