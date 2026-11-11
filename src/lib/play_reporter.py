# play_reporter.py
#
# Copyright 2026 Petru101
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reports plays to TIDAL, so they show up in Recently played on every device and
count for recommendations.

Fetching a stream doesn't count as a play: the official apps send a
`playback_session` event for every play to TIDAL's event producer. The event
layout follows TIDAL's own open source SDK (github.com/tidal-music/tidal-sdk-android,
modules `eventproducer` and `player/events`). The events describe the real sender,
High Tide on Linux.
"""

import base64
import json
import logging
import platform
import threading
import time
import uuid
from pathlib import Path
from typing import Any, List, Tuple
from xml.etree import ElementTree

import requests
from gi.repository import GLib
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix, MixV2
from tidalapi.playlist import Playlist

logger = logging.getLogger(__name__)

EVENT_BATCH_URL = "https://ec.tidal.com/api/event-batch"
# TIDAL counts a play after 30 seconds
MIN_PLAYED_SECONDS = 30
MAX_BATCH = 10
MAX_QUEUED = 500
MAX_QUEUED_AGE_MS = 14 * 24 * 3600 * 1000


def get_source(thing: Any, track: Any) -> Tuple[str, str]:
    """Get the source TIDAL attributes a play to.

    Args:
        thing: What the track was played from (Album, Playlist, Mix, Artist, ...)
        track: The played track

    Returns:
        (source type, source id); a track played on its own is an ITEM with its
            own id, the only form TIDAL shows in Recently played
    """
    if isinstance(thing, Album):
        return "ALBUM", str(thing.id)
    if isinstance(thing, Playlist):
        return "PLAYLIST", str(thing.id)
    if isinstance(thing, (Mix, MixV2)):
        return "MIX", str(thing.id)
    if isinstance(thing, Artist):
        return "ARTIST", str(thing.id)
    return "ITEM", str(track.id)


def _get_claims(access_token: str) -> dict:
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


class _PlaySession:
    def __init__(self, track: Any, source: Tuple[str, str], position: float, stream):
        self.track = track
        self.source = source
        self.id = str(uuid.uuid4())
        self.start_timestamp = int(time.time() * 1000)
        self.start_position = position
        self.position = position
        self.actions: List[dict] = []
        self.played_seconds = 0.0
        self.resumed_at: float | None = None

        quality = getattr(stream, "audio_quality", None) or "LOSSLESS"
        self.quality = str(getattr(quality, "value", quality))
        audio_mode = getattr(stream, "audio_mode", None) or "STEREO"
        self.audio_mode = str(getattr(audio_mode, "value", audio_mode))

    def resume(self) -> None:
        if self.resumed_at is None:
            self.resumed_at = time.monotonic()

    def pause(self) -> None:
        if self.resumed_at is not None:
            self.played_seconds += time.monotonic() - self.resumed_at
            self.resumed_at = None

    def get_played_seconds(self) -> float:
        if self.resumed_at is None:
            return self.played_seconds
        return self.played_seconds + time.monotonic() - self.resumed_at

    def add_action(self, action_type: str, position: float) -> None:
        self.actions.append(
            {
                "timestamp": int(time.time() * 1000),
                "assetPosition": position,
                "actionType": action_type,
            }
        )

    def counts(self) -> bool:
        duration = self.track.duration or MIN_PLAYED_SECONDS
        return self.get_played_seconds() >= min(MIN_PLAYED_SECONDS, duration - 1)

    def get_payload(self) -> dict:
        return {
            "playbackSessionId": self.id,
            "startTimestamp": self.start_timestamp,
            "startAssetPosition": self.start_position,
            "isPostPaywall": True,
            "productType": "TRACK",
            "requestedProductId": str(self.track.id),
            "actualProductId": str(self.track.id),
            "actualAssetPresentation": "FULL",
            "actualAudioMode": self.audio_mode,
            "actualQuality": self.quality,
            "sourceType": self.source[0],
            "sourceId": self.source[1],
            "actions": self.actions,
            "endTimestamp": int(time.time() * 1000),
            "endAssetPosition": self.position,
        }


class PlayReporter:
    """Follows the player and reports each play of at least 30 seconds to TIDAL.

    Events that can't be sent (offline, errors) are kept in a file and sent with
    the next ones.
    """

    def __init__(self, player: Any, session: Any, version: str, queue_path: Path):
        self.player = player
        self.session = session
        self.version = version
        self.queue_path = queue_path

        self.current: _PlaySession | None = None
        self.was_playing = player.playing
        self.queue_lock = threading.Lock()

        player.connect("song-changed", self._on_song_changed)
        player.connect("notify::playing", self._on_playing_changed)
        player.connect("seeked", self._on_seeked)
        GLib.timeout_add_seconds(1, self._update_position)

    def _query_position(self) -> float:
        position = self.player.query_position(default=None)
        return position / 1_000_000_000 if position else 0.0

    def _update_position(self) -> bool:
        # The position is kept up to date, because when the song changes the
        # player already reports the position of the next one
        if self.current and self.player.playing:
            self.current.position = self._query_position()
        return True

    def _on_song_changed(self, *args) -> None:
        self._finish_current()

        track = self.player.playing_track
        if track is None:
            return

        self.current = _PlaySession(
            track,
            get_source(self.player.get_playing_source(), track),
            self._query_position(),
            self.player.stream,
        )
        if self.player.playing:
            self.current.resume()

    def _on_playing_changed(self, *args) -> None:
        # The player also sets it when a song starts, without pausing or resuming
        if self.player.playing == self.was_playing:
            return
        self.was_playing = self.player.playing

        if not self.current:
            return
        position = self._query_position()
        if self.player.playing:
            self.current.resume()
            self.current.add_action("PLAYBACK_START", position)
        else:
            self.current.pause()
            self.current.position = position
            self.current.add_action("PLAYBACK_STOP", position)

    def _on_seeked(self, player, old_position: float, new_position: float) -> None:
        if not self.current:
            return
        self.current.add_action("PLAYBACK_STOP", old_position)
        self.current.add_action("PLAYBACK_START", new_position)
        self.current.position = new_position

    def _finish_current(self, wait: bool = False) -> None:
        session = self.current
        self.current = None
        if session is None or not session.counts():
            return

        # A track that played to the end changed song within a second of it
        duration = session.track.duration or 0
        if duration and session.position > duration - 2:
            session.position = float(duration)

        event = {
            "ts": int(time.time() * 1000),
            "uuid": str(uuid.uuid4()),
            "payload": session.get_payload(),
        }
        thread = threading.Thread(target=self._send, args=([event],))
        thread.start()
        if wait:
            thread.join(timeout=3)

    def flush(self) -> None:
        """Send the play in progress, call when the app closes"""
        self._finish_current(wait=True)

    def _send(self, events: List[dict]) -> None:
        with self.queue_lock:
            events = self._load_queue() + events
            now = int(time.time() * 1000)
            events = [e for e in events if now - e["ts"] < MAX_QUEUED_AGE_MS]

            unsent = []
            for start in range(0, len(events), MAX_BATCH):
                batch = events[start : start + MAX_BATCH]
                unsent += batch if unsent else self._post(batch)

            self._save_queue(unsent[-MAX_QUEUED:])

    def _post(self, events: List[dict]) -> List[dict]:
        """Post a batch of events, returns the ones that should be sent again"""
        for attempt in range(2):
            try:
                response = requests.post(
                    EVENT_BATCH_URL,
                    data=self._get_form(events),
                    headers={"Authorization": f"Bearer {self.session.access_token}"},
                    timeout=10,
                )
            except requests.RequestException as e:
                logger.info(f"Couldn't report plays to TIDAL, will retry: {e}")
                return events

            if response.status_code in (401, 403) and attempt == 0:
                if self._refresh_token():
                    continue
            if not response.ok:
                logger.info(f"Couldn't report plays to TIDAL ({response.status_code})")
                return events

            unsent = self._get_unsent(events, response.text)
            if unsent:
                logger.info(f"TIDAL didn't take all plays: {response.text[:300]}")
            if len(unsent) < len(events):
                logger.info(f"Reported {len(events) - len(unsent)} play(s) to TIDAL")
            return unsent
        return events

    def _refresh_token(self) -> bool:
        try:
            return self.session.token_refresh(self.session.refresh_token)
        except Exception as e:
            logger.info(f"Couldn't refresh the token to report plays: {e}")
            return False

    def _get_unsent(self, events: List[dict], reply: str) -> List[dict]:
        """Get the events TIDAL didn't take, by the rules of its own SDKs: an event
        is done only when the reply lists it as sent, or as malformed (SenderFault).
        Anything else, like a Wi-Fi login page answering instead, is sent again."""
        try:
            root = ElementTree.fromstring(reply)
        except ElementTree.ParseError:
            return events

        done = {
            entry.findtext("{*}Id")
            for entry in root.iterfind(".//{*}SendMessageBatchResultEntry")
        }
        for entry in root.iterfind(".//{*}BatchResultErrorEntry"):
            if entry.findtext("{*}SenderFault") == "true":
                logger.warning(f"TIDAL rejected a reported play: {reply[:300]}")
                done.add(entry.findtext("{*}Id"))
        return [event for event in events if event["uuid"] not in done]

    def _get_form(self, events: List[dict]) -> dict:
        access_token = self.session.access_token
        claims = _get_claims(access_token)
        now = str(int(time.time() * 1000))

        headers = json.dumps(
            {
                "app-version": self.version,
                "os-name": platform.system(),
                "os-version": platform.release(),
                "consent-category": "NECESSARY",
                "requested-sent-timestamp": now,
                "authorization": access_token,
                "client-id": self.session.config.client_id_pkce
                if self.session.is_pkce
                else self.session.config.client_id,
            }
        )

        form = {}
        for index, event in enumerate(events, 1):
            body = {
                "group": "play_log",
                "version": 2,
                "ts": event["ts"],
                "uuid": event["uuid"],
                "user": {
                    "id": claims.get("uid"),
                    "clientId": claims.get("cid"),
                    "sessionId": claims.get("sid"),
                },
                "client": {
                    "token": str(claims.get("cid", "")),
                    "deviceType": "desktop",
                    "version": self.version,
                    "platform": platform.system().lower(),
                },
                "payload": event["payload"],
            }
            entry = f"SendMessageBatchRequestEntry.{index}."
            form[entry + "Id"] = event["uuid"]
            form[entry + "MessageBody"] = json.dumps(body)
            form[entry + "MessageAttribute.1.Name"] = "Name"
            form[entry + "MessageAttribute.1.Value.StringValue"] = "playback_session"
            form[entry + "MessageAttribute.1.Value.DataType"] = "String"
            form[entry + "MessageAttribute.2.Name"] = "Headers"
            form[entry + "MessageAttribute.2.Value.StringValue"] = headers
            form[entry + "MessageAttribute.2.Value.DataType"] = "String"
        return form

    def _load_queue(self) -> List[dict]:
        try:
            return json.loads(self.queue_path.read_text())
        except (OSError, ValueError):
            return []

    def _save_queue(self, events: List[dict]) -> None:
        try:
            if events:
                self.queue_path.write_text(json.dumps(events))
            else:
                self.queue_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Couldn't save the plays to report later")
