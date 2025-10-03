# player_object.py
#
# Copyright 2023 Nokse
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

import logging
import random
import threading
from enum import IntEnum
from gettext import gettext as _
from pathlib import Path
from typing import Any, List, Union

from gi.repository import GLib, GObject, Gst
from tidalapi import Album, Artist, Mix, Playlist, Track
from tidalapi.media import ManifestMimeType

from . import discord_rpc, utils

logger = logging.getLogger(__name__)


class RepeatType(IntEnum):
    NONE = 0
    SONG = 1
    LIST = 2


class AudioSink(IntEnum):
    AUTO = 0
    PULSE = 1
    ALSA = 2
    JACK = 3
    OSS = 4
    PIPEWIRE = 5


class PlayerObject(GObject.GObject):
    """Handles player logic, queue, and shuffle functionality."""

    current_song_index = GObject.Property(type=int, default=-1)
    can_go_next = GObject.Property(type=bool, default=True)
    can_go_prev = GObject.Property(type=bool, default=True)

    __gsignals__ = {
        "songs-list-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "update-slider": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "song-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "song-added-to-queue": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "duration-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "volume-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "buffering": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(
        self,
        preferred_sink: AudioSink = AudioSink.AUTO,
        alsa_device: str = "default",
        normalize: bool = False,
        quadratic_volume: bool = False,
    ) -> None:
        GObject.GObject.__init__(self)

        Gst.init(None)

        version_str = Gst.version_string()
        logger.info(f"GStreamer version: {version_str}")

        self.pipeline = Gst.Pipeline.new("dash-player")

        self.playbin = Gst.ElementFactory.make("playbin3", "playbin")
        if self.playbin:
            self.playbin.connect("about-to-finish", self.play_next_gapless)
            self.gapless_enabled = True
        else:
            logger.error("Could not create playbin3 element, trying playbin...")
            self.playbin = Gst.ElementFactory.make("playbin", "playbin")
            self.gapless_enabled = False

        if preferred_sink == AudioSink.PIPEWIRE:
            self.gapless_enabled = False

        self.use_about_to_finish = True

        self.pipeline.add(self.playbin)

        self.normalize = normalize
        self.quadratic_volume = quadratic_volume
        self.most_recent_rg_tags = ""

        self.discord_rpc_enabled = True

        self.alsa_device: str = alsa_device
        # Configure audio sink
        self._setup_audio_sink(preferred_sink)

        # Set up message bus
        self._bus = self.pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message::eos", self._on_bus_eos)
        self._bus.connect("message::error", self._on_bus_error)
        self._bus.connect("message::buffering", self._on_buffering_message)
        self._bus.connect("message::stream-start", self._on_track_start)

        # Initialize state utils
        self._shuffle = False
        self._playing = False
        self._repeat_type = RepeatType.NONE

        self.id_list: List[str] = []

        self.queue: List[Track] = []
        self.current_mix_album_playlist: Union[Mix, Album, Playlist] | None = None
        self._tracks_to_play: List[Track] = []
        self.tracks_to_play: List[Track] = []
        self._shuffled_tracks_to_play: List[Track] = []
        self.played_songs: List[Track] = []
        self.playing_track: Track | None = None
        self.song_album: Album | None = None
        self.duration = self.query_duration()
        self.manifest: Any | None = None
        self.stream: Any | None = None
        self.update_timer: Any | None = None
        self.seek_after_sink_reload: int | None = None
        self.seeked_to_end = False

        # next track variables for gapless
        self.next_track: Any | None = None

    @GObject.Property(type=bool, default=False)
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, _playing: bool) -> None:
        self._playing = _playing
        self.notify("playing")

    @GObject.Property(type=bool, default=False)
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, _shuffle: bool) -> None:
        if self._shuffle == _shuffle:
            return

        self._shuffle = _shuffle
        self.notify("shuffle")
        self._update_shuffle_queue()
        # self.emit("song-changed")

    @GObject.Property(type=int, default=0)
    def repeat_type(self) -> RepeatType:
        return self._repeat_type

    @repeat_type.setter
    def repeat_type(self, _repeat_type: RepeatType) -> None:
        self._repeat_type = _repeat_type
        self.notify("repeat-type")

    def _setup_audio_sink(self, sink_type: AudioSink) -> None:
        """Configure the audio sink using parse_launch for simplicity."""
        sink_map = {
            AudioSink.AUTO: "autoaudiosink",
            AudioSink.PULSE: "pulsesink",
            AudioSink.ALSA: f"alsasink device={self.alsa_device}",
            AudioSink.JACK: "jackaudiosink",
            AudioSink.OSS: "osssink",
            AudioSink.PIPEWIRE: "pipewiresink",
        }

        sink_name = sink_map.get(sink_type, "autoaudiosink")

        # add normalization to pipeline if set by settings
        normalization = ""
        if self.normalize:
            # the pre-amp value is set to match tidal webs volume
            normalization = (
                f"taginject name=rgtags {self.most_recent_rg_tags} ! "
                f"rgvolume name=rgvol pre-amp=4.0 fallback-gain=-10 headroom=6.0 ! "
                f"rglimiter ! audioconvert !"
            )

        pipeline_str = (
            f"queue ! audioconvert ! {normalization} audioresample ! {sink_name}"
        )

        if sink_type == AudioSink.PIPEWIRE:
            self.gapless_enabled = False
        else:
            self.gapless_enabled = True

        try:
            audio_bin = Gst.parse_bin_from_description(pipeline_str, True)
            if not audio_bin:
                raise RuntimeError("Failed to create audio bin")

            self.playbin.set_property("audio-sink", audio_bin)
        except GLib.Error:
            logger.exception("Error creating pipeline")
            self.playbin.set_property(
                "audio-sink", Gst.ElementFactory.make("autoaudiosink", None)
            )

    def change_audio_sink(self, sink_type: AudioSink) -> None:
        """Change the audio sink while maintaining playback state.

        Args:
            sink_type (int): The audio sink `AudioSink` enum
        """
        self.use_about_to_finish = False
        # Play the same track again after reload
        self.next_track = self.playing_track
        was_playing: bool = self.playing
        position: int = self.query_position()
        duration: int = self.query_duration()

        self.pipeline.set_state(Gst.State.NULL)
        self._setup_audio_sink(sink_type)

        if was_playing and duration != 0:
            self.pipeline.set_state(Gst.State.PLAYING)
            self.seek_after_sink_reload = position / duration
        self.use_about_to_finish = True

    def _on_bus_eos(self, *args) -> None:
        """Handle end of stream."""
        if not self.tracks_to_play or not self.queue:
            self.pause()
        if not self.gapless_enabled:
            GLib.idle_add(self.play_next)

    def _on_bus_error(self, bus: Any, message: Any) -> None:
        """Handle pipeline errors."""
        err, debug = message.parse_error()
        logger.error(f"Error: {err.message}")
        logger.error(f"Debug info: {debug}")

        # Use string compare instead of error codes (Seems be just generic error)
        if "Internal data stream error" in err.message and "not-linked" in debug:
            logger.error(
                "Stream error: Element not linked. Attempting to restart pipeline..."
            )
            self.play_track(self.playing_track)

        elif (
            "Error outputting to audio device" in err.message
            and "disconnected" in err.message
        ):
            utils.send_toast(_("ALSA Audio Device is not available"), 5)
            self.pause()
            self.pipeline.set_state(Gst.State.NULL)

    def _on_buffering_message(self, bus: Any, message: Any) -> None:
        buffer_per: int = message.parse_buffering()
        mode, avg_in, avg_out, buff_left = message.parse_buffering_stats()

        self.emit("buffering", buffer_per)

    def set_track(self, track: Track | None = None):
        """Sets the currently Playing track

        Args:
            track: If set, the playing track is set to it.
            Otherwise self.next_track is used
        """
        if not track and not self.next_track:
            # This method has already been called in _play_track_url
            return
        if track:
            self.playing_track = track
        else:
            self.playing_track = self.next_track
            self.next_track = None
        self.song_album = self.playing_track.album
        self.can_go_next = len(self._tracks_to_play) > 0
        self.can_go_prev = len(self.played_songs) > 0
        self.duration = self.query_duration()
        # Should only trigger when track is enqued on start without playback
        if not self.duration:
            # self.duration is microseconds, but self.playing_track.duration is seconds
            self.duration = self.playing_track.duration * 1_000_000_000
        self.notify("can-go-prev")
        self.notify("can-go-next")
        self.emit("song-changed")

    def _on_track_start(self, bus: Any, message: Any):
        """This Method is called when a new track starts playing

        Args:
            bus: required by Gst
            message: required by Gst
        """
        # apply replaygain first to avoid volume clipping
        # (Idk if that will happen but its the only thing that has effect on audio in here)
        if self.stream:
            self.apply_replaygain_tags()
        self.set_track()

        if self.discord_rpc_enabled and self.playing_track:
            discord_rpc.set_activity(self.playing_track, 0)

        if self.update_timer:
            GLib.source_remove(self.update_timer)
        self.update_timer = GLib.timeout_add(1000, self._update_slider_callback)

        self.seeked_to_end = False
        if self.seek_after_sink_reload:
            self.seek(self.seek_after_sink_reload)
            self.seek_after_sink_reload = None

    def play_this(
        self, thing: Union[Mix, Album, Playlist, List[Track], Track], index: int = 0
    ) -> None:
        """Play tracks from a mix, album, playlist, or artist.

        Args:
            thing: An object (Mix, Album, Playlist, Artist, or list of Tracks) to play
            index (int): The index of the track to start playing (default: 0)
        """
        self.current_mix_album_playlist = thing
        tracks: List[Track] = self.get_track_list(thing)

        if not tracks:
            logger.info("No tracks found to play")
            return

        self._tracks_to_play = tracks[index:] + tracks[:index]
        if not self._tracks_to_play:
            return

        track: Track = self._tracks_to_play.pop(0)
        self.tracks_to_play = self._tracks_to_play
        self.played_songs = []

        if self.shuffle:
            self._update_shuffle_queue()

        # Will result in play() call later
        self.playing = True
        self.play_track(track)

    def shuffle_this(
        self, thing: Union[Mix, Album, Playlist, List[Track], Track]
    ) -> None:
        """Same as play_this, but enables shuffle mode.

        Args:
            thing: An object (Mix, Album, Playlist, Artist, or list of Tracks) to play
        """
        tracks: List[Track] = self.get_track_list(thing)
        self.play_this(thing, random.randint(0, len(tracks)))
        self.shuffle = True

    def get_track_list(
        self, thing: Union[Mix, Album, Playlist, Artist, List[Track], Track]
    ) -> List[Track]:
        """Convert various sources into a list of tracks.

        Args:
            thing: A TIDAL object (Mix, Album, Playlist, Artist, or list of Tracks)

        Returns:
            list: List of Track objects, or None if conversion failed
        """
        tracks_list: List[Track] | None = None

        if isinstance(thing, Mix):
            tracks_list = thing.items()
        elif isinstance(thing, Album):
            tracks_list = thing.tracks()
        elif isinstance(thing, Playlist):
            tracks_list = thing.tracks()
        elif isinstance(thing, Artist):
            tracks_list = thing.top_tracks()
        elif isinstance(thing, list):
            tracks_list = thing
        elif isinstance(thing, Track):
            tracks_list = [thing]

        self.id_list = [track.id for track in tracks_list]

        return tracks_list

    def play(self) -> None:
        """Start playback of the current track."""
        self.playing = True
        self.pipeline.set_state(Gst.State.PLAYING)

        if self.discord_rpc_enabled and self.playing_track:
            discord_rpc.set_activity(
                self.playing_track, self.query_position() / 1_000_000
            )
        if self.update_timer:
            GLib.source_remove(self.update_timer)
        self.update_timer = GLib.timeout_add(1000, self._update_slider_callback)

    def pause(self) -> None:
        """Pause playback of the current track."""
        self.playing = False
        self.pipeline.set_state(Gst.State.PAUSED)

        if self.discord_rpc_enabled:
            discord_rpc.set_activity()

    def play_pause(self) -> None:
        """Toggle between play and pause states."""
        if self.playing:
            self.pause()
        else:
            self.play()

    def play_track(self, track: Track, gapless=False) -> None:
        """Play a specific track immediately or enqueue it for gapless playback

        Args:
            track: The Track object to play
            gapless: Whether to enqueue the track for gapless playback
        """
        threading.Thread(target=self._play_track_thread, args=(track, gapless)).start()

    def _play_track_thread(self, track: Track, gapless=False) -> None:
        """Thread for loading and playing a track.

        Args:
            track: The Track object to play
            gapless: Whether to enqueue the track for gapless playback
        """

        self.stream = None
        self.manifest = None

        try:
            self.stream = track.get_stream()
            self.manifest = self.stream.get_stream_manifest()
            urls = self.manifest.get_urls()

            # When not gapless there is a race condition between get_stream() and on_track_start
            if not gapless:
                self.apply_replaygain_tags()

            if self.stream.manifest_mime_type == ManifestMimeType.MPD:
                data = self.stream.get_manifest_data()
                if data:
                    mpd_path = Path(utils.CACHE_DIR, "manifest.mpd")
                    with open(mpd_path, "w") as file:
                        file.write(data)

                    music_url = "file://{}".format(mpd_path)
                else:
                    raise AttributeError("No MPD manifest available!")
            elif self.stream.manifest_mime_type == ManifestMimeType.BTS:
                urls = self.manifest.get_urls()
                if isinstance(urls, list):
                    music_url = urls[0]
                else:
                    music_url = urls

            GLib.idle_add(self._play_track_url, track, music_url, gapless)
        except Exception:
            logger.exception("Error getting track URL")

    def apply_replaygain_tags(self):
        """Apply ReplayGain normalization tags to the current track if enabled."""
        audio_sink = self.playbin.get_property("audio-sink")

        if audio_sink:
            rgtags = audio_sink.get_by_name("rgtags")

        tags = ""

        # https://github.com/EbbLabs/python-tidal/issues/332
        # Rather quiet album than broken eardrums
        if self.stream.track_replay_gain != 1.0:
            tags = (
                f"replaygain-track-gain={self.stream.track_replay_gain},"
                f"replaygain-track-peak={self.stream.track_peak_amplitude}"
            )

        if self.stream.album_replay_gain != 1.0:
            tags = (
                f"replaygain-album-gain={self.stream.album_replay_gain},"
                f"replaygain-album-peak={self.stream.album_peak_amplitude}"
            )

        if rgtags:
            rgtags.set_property("tags", tags)
            logger.info("Applied RG Tags")
        # Save replaygain tags for every song to avoid missing tags when
        # toggling the option
        self.most_recent_rg_tags = f"tags={tags}"

    def _play_track_url(self, track, music_url, gapless=False):
        """Set up and play track from URL."""
        if not gapless:
            self.use_about_to_finish = False
            self.pipeline.set_state(Gst.State.NULL)
            self.playbin.set_property("volume", self.playbin.get_property("volume"))
        self.playbin.set_property("uri", music_url)

        logger.info(music_url)

        if gapless:
            self.next_track = track
        else:
            self.set_track(track)

        if not gapless and self.playing:
            self.play()

        if not gapless:
            self.use_about_to_finish = True

    def play_next_gapless(self, playbin: Any):
        """Enqueue the next track for gapless playback.

        Args:
            playbin: required by Gst
        """
        # playbin is need as arg but we access it later over self
        if self.gapless_enabled and self.use_about_to_finish and self.tracks_to_play:
            GLib.idle_add(self.play_next, True)
            logger.info("Trying gapless playbck")
        else:
            logger.info("Ignoring about to finish event")

    def play_next(self, gapless=False):
        """Play the next track in the queue or playlist.

        Args:
            gapless: Whether to enqueue the track in gapless mode
        """

        # A track is already enqueued from an about-to-finish
        if self.next_track:
            logger.info("Using already enqueued track from gapless")
            track = self.next_track
            self.next_track = None
            self.play_track(track, gapless=gapless)
            return

        if self._repeat_type == RepeatType.SONG and not gapless:
            self.seek(0)
            self.apply_replaygain_tags()
            return
        if self._repeat_type == RepeatType.SONG:
            self.play_track(self.playing_track, gapless=True)
            return

        if self.playing_track:
            self.played_songs.append(self.playing_track)

        if self.queue:
            track = self.queue.pop(0)
            self.play_track(track, gapless=gapless)
            return

        if not self._tracks_to_play and self._repeat_type == RepeatType.LIST:
            self._tracks_to_play = self.played_songs
            self.tracks_to_play = self._tracks_to_play
            self.played_songs = []

        if not self._tracks_to_play:
            self.pause()
            return

        track_list = []
        if self.shuffle:
            track_list = self._shuffled_tracks_to_play
        else:
            track_list = self._tracks_to_play

        if track_list and len(track_list) > 0:
            track = track_list.pop(0)
            self.play_track(track, gapless=gapless)

    def play_previous(self):
        """Play the previous track or restart current track if near beginning."""
        # if not in the first 2 seconds of the track restart song
        if self.query_position() > 2 * Gst.SECOND:
            self.seek(0)
            return

        if not self.played_songs:
            return

        last_index = len(self.played_songs) - 1
        track = self.played_songs.pop(last_index)
        if self.playing_track:
            self._tracks_to_play.insert(0, self.playing_track)
        self.play_track(track)

    def _update_shuffle_queue(self):
        if self.shuffle:
            self._shuffled_tracks_to_play = self._tracks_to_play.copy()
            random.shuffle(self._shuffled_tracks_to_play)
            self.tracks_to_play = self._shuffled_tracks_to_play
        else:
            self.tracks_to_play = self._tracks_to_play

    def add_to_queue(self, track):
        """Add a track to the end of the play queue.

        Args:
            track: The Track object to add to the queue
        """
        self.queue.append(track)
        self.emit("song-added-to-queue")

    def add_next(self, track):
        """Add a track to the top of the queue.

        Args:
            track: The Track object to play next
        """
        self.queue.insert(0, track)
        self.emit("song-added-to-queue")

    def query_volume(self):
        """Get the current playback volume.

        Returns:
            float: Current volume level (0.0 to 1.0), adjusted for quadratic scaling if enabled
        """
        volume = self.playbin.get_property("volume")
        if self.quadratic_volume:
            return round(volume ** (1 / 2), 1)
        else:
            return round(volume, 1)

    def change_volume(self, value):
        """Set the playback volume.

        Args:
            value (float): Volume level (0.0 to 1.0), will be squared if quadratic volume is enabled
        """
        if self.quadratic_volume:
            self.playbin.set_property("volume", value**2)
        else:
            self.playbin.set_property("volume", value)
        self.emit("volume-changed", value)

    def _update_slider_callback(self):
        """Update playback slider and duration."""
        self.update_timer = None
        if not self.duration:
            logger.warning("Duration missing, trying again")
            self.duration = self.query_duration()
        self.emit("update-slider")
        return self.playing

    def query_duration(self):
        """Get the duration of the current track.

        Returns:
            int: Duration in nanoseconds, or 0 if query failed
        """
        success, duration = self.playbin.query_duration(Gst.Format.TIME)
        return duration if success else 0

    def query_position(self, default=0) -> int | None:
        """Get the current playback position.

        Args:
            default (int): Default value to return if query fails (default: 0)

        Returns:
            int: Position in nanoseconds, or default value if query failed
        """
        success, position = self.playbin.query_position(Gst.Format.TIME)
        return position if success else default

    def seek(self, seek_fraction):
        """Seek to a position in the current track.

        Args:
            seek_fraction (float): Position as a fraction of total duration (0.0 to 1.0)
        """

        # If a seek close to the end is performed then skip
        # Avoids UI desync and stuck tracks
        if not self.seeked_to_end and seek_fraction > 0.98:
            self.use_about_to_finish = False
            self.seeked_to_end = True
            self.play_next()
            return
        position = int(seek_fraction * self.query_duration())
        self.playbin.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, position
        )

        if self.discord_rpc_enabled:
            discord_rpc.set_activity(self.playing_track, position / 1_000_000)

    def set_discord_rpc(self, enabled: bool = True):
        """Enable or disable Discord Rich Presence integration.

        Args:
            enabled (bool): Whether to enable Discord RPC (default: True)
        """
        self.discord_rpc_enabled = enabled
        if enabled and self.playing:
            discord_rpc.set_activity(
                self.playing_track, self.query_position() / 1_000_000
            )
        elif enabled:
            discord_rpc.set_activity()
        else:
            discord_rpc.disconnect()

    def get_index(self):
        """Get the index of the currently playing track in the playlist.

        Returns:
            int: Index of current track, or 0 if not found
        """
        for index, track_id in enumerate(self.id_list):
            if track_id == self.playing_track.id:
                return index
        return 0
