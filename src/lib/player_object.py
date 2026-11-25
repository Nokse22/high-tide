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
import shutil
import threading
import time
import base64
from concurrent.futures import ThreadPoolExecutor
from enum import IntEnum
from gettext import gettext as _
from pathlib import Path
from typing import Any, List, Union

from gi.repository import GLib, GObject, Gst, Gio

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist
from tidalapi.media import Track, ManifestMimeType

from . import jack
from . import cast, discord_rpc, dlna, utils

logger = logging.getLogger(__name__)

# Seconds of audio a cached track can lack. Audio frames are under 0.1 s and MPD
# segments about 4 s, and track durations are rounded to whole seconds.
MAX_CACHE_GAP = 1.5

# ALSA output holds the sound card exclusively, so it's let go after pausing this long
ALSA_RELEASE_SECONDS = 5


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
    # 5 was GStreamer's native PipeWire sink, which crackled and couldn't play
    # gapless. Automatic plays through PipeWire too, via its PulseAudio server


class PlayerObject(GObject.GObject):
    """Handles player logic, queue, and shuffle functionality."""

    current_song_index = GObject.Property(type=int, default=-1)
    can_go_next = GObject.Property(type=bool, default=True)
    can_go_prev = GObject.Property(type=bool, default=True)
    # When the list ends, keep playing the last song's radio (the autoplay setting)
    autoplay = GObject.Property(type=bool, default=False)

    __gsignals__ = {
        "songs-list-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "update-slider": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "song-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # old and new position in seconds
        "seeked": (GObject.SignalFlags.RUN_FIRST, None, (float, float)),
        "song-added-to-queue": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # Songs were added to the next songs (autoplay)
        "next-songs-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "duration-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "volume-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "buffering": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        # Playing moved to another device or back here, see set_renderer
        "renderer-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        preferred_sink: AudioSink = AudioSink.AUTO,
        alsa_device: str = "default",
        normalize: bool = False,
        quadratic_volume: bool = False,
        output_rate: int = 0,
        jack_connect: str = "",
    ) -> None:
        GObject.GObject.__init__(self)
        # Sample rate everything is converted to before the output, 0 for each
        # song's own: cards and DACs that pop when the rate changes stay at one
        self.output_rate = output_rate

        # The DLNA device playing instead of this computer, see set_renderer
        self.renderer: dlna.Renderer | cast.CastDevice | None = None

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

        self.use_about_to_finish = True

        self.pipeline.add(self.playbin)

        self.normalize = normalize
        self.quadratic_volume = quadratic_volume
        self.most_recent_rg_tags = ""

        self.discord_rpc_enabled = True

        self.alsa_device: str = alsa_device
        # Where the JACK output connects to: a JACK client's name, or
        # jack.SOUND_CARD / jack.NOTHING
        self.jack_connect: str = jack_connect
        # Position and duration (ns) of the paused track while the sound card is let go
        self.released_at: tuple[int, int] | None = None
        self.release_timer: int | None = None
        self.resuming_released = False
        # Configure audio sink
        self._setup_audio_sink(preferred_sink)

        # Set up message bus
        self._bus = self.pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message::eos", self._on_bus_eos)
        self._bus.connect("message::error", self._on_bus_error)
        self._bus.connect("message::buffering", self._on_buffering_message)
        self._bus.connect("message::stream-start", self._on_track_start)
        self._bus.connect("message::async-done", self._on_async_done)

        # Initialize state utils
        self._shuffle = False
        self._playing = False
        self._repeat_type = RepeatType.NONE

        self.id_list: List[str] = []

        self.queue: List[Track] = []
        self.current_mix_album_playlist: Union[Mix, Album, Playlist] | None = None
        self.play_source = None
        # Autoplay: the radio being loaded for (a track id), and the songs it added
        # with the radio they come from
        self._autoplay_loading_for = None
        self._autoplay_sources: dict = {}
        self.playing_from_queue = False
        self._last_queued_track = None
        self._tracks_to_play: List[Track] = []
        self.tracks_to_play: List[Track] = []
        self._shuffled_tracks_to_play: List[Track] = []
        # The list in the order it was started in, to continue from when shuffle is
        # turned off
        self._play_order: List[Track] = []
        self.played_songs: List[Track] = []
        self.playing_track: Track | None = None
        self.song_album: Album | None = None
        self.duration = self.query_duration()
        self.manifest: Any | None = None
        self.stream: Any | None = None
        self.update_timer: Any | None = None
        self.seek_after_sink_reload: int | None = None
        self.last_stream_reload: int = 0
        # the track being loaded again by _reload_track
        self.reloading_track: Track | None = None
        # when the uri of the playing track was loaded, its stream urls expire after
        # about an hour (wall-clock time, to count time spent suspended)
        self.stream_loaded_at: float = 0
        # to notice when the stream of the playing track gets stuck
        self.last_position: int | None = None
        self.position_stuck_since: float = 0.0
        # where the last seek went, as the position can't be queried until it's done
        self.last_seek_position: int | None = None

        # next track variables for gapless
        self.next_track: Any | None = None
        # (track id, stream, manifest, fetch time) of the next track, fetched
        # before the current one ends so its uri can be set in about-to-finish
        self.prefetched: tuple | None = None
        self.prefetch_id: int | None = None
        # track whose uri was set in about-to-finish from the prefetched stream
        self.handed_off_track: Track | None = None
        # a gapless track is being loaded / the current one ended before it was
        self.loading_gapless = False
        self.reached_eos = False
        # the last track requested for gapless playback, dropped if another track
        # is played directly while it loads
        self.gapless_request: Track | None = None
        # the next track, when loading it for gapless playback failed: it's
        # loaded again when the current one ends
        self.failed_next_track: Track | None = None
        # counts the tracks played directly; a track that finishes loading after
        # another one was played is dropped, so only the last one asked for plays
        self.play_request = 0

        # for not caching on metered networks
        self.monitor = Gio.NetworkMonitor.get_default()
        # Music cache downloads in progress, by cache file: one per track at a time
        self._cache_downloads: dict = {}
        self._cache_lock = threading.Lock()
        self._closing = False

        self._media_server: dlna.MediaServer | None = None
        # Commands to the device, sent in order and off the main thread
        self._remote_commands = ThreadPoolExecutor(max_workers=1)
        # Changes with every track sent to the device, so late results are ignored
        self._remote_token = 0
        # Position, duration (seconds) and volume (0 to 1) on the device
        self.remote_position = 0.0
        self.remote_duration = 0.0
        self.remote_volume = 1.0
        # When the volume was last sent to the device: it can take a moment to apply,
        # and readings from before that would move the slider back
        self._remote_volume_set_at = 0.0
        # Volumes waiting to be sent (behind other commands, like loading a track)
        self._remote_volume_pending = 0
        self._remote_volume_lock = threading.Lock()
        # Where to continue when play is pressed, after switching to it while paused
        self._remote_resume_at = 0.0
        self._remote_prepare_locks: dict[str, threading.Lock] = {}

    # False while playing on a device whose volume can't be read or set
    volume_available = GObject.Property(type=bool, default=True)

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
        if not _shuffle:
            self._continue_in_order()
        self._update_shuffle_queue()
        self.emit("song-added-to-queue")
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
            AudioSink.JACK: "jackaudiosink name=jacksink",
            AudioSink.OSS: "osssink",
        }

        sink_name = sink_map.get(sink_type, "autoaudiosink")
        self.sink_type = sink_type

        # add normalization to pipeline if set by settings
        normalization = ""
        if self.normalize:
            # the pre-amp value is set to match tidal webs volume
            normalization = (
                f"taginject name=rgtags {self.most_recent_rg_tags} ! "
                f"rgvolume name=rgvol pre-amp=4.0 fallback-gain=-10 headroom=6.0 ! "
                f"rglimiter ! audioconvert !"
            )

        rate = f"audio/x-raw,rate={self.output_rate} ! " if self.output_rate else ""
        pipeline_str = (
            f"queue ! audioconvert ! {normalization} audioresample ! {rate}{sink_name}"
        )

        try:
            audio_bin = Gst.parse_bin_from_description(pipeline_str, True)
            if not audio_bin:
                raise RuntimeError("Failed to create audio bin")

            if sink_type == AudioSink.JACK:
                self._set_jack_connect(audio_bin.get_by_name("jacksink"))
            self.playbin.set_property("audio-sink", audio_bin)
        except GLib.Error:
            logger.exception("Error creating pipeline")
            self.playbin.set_property(
                "audio-sink", Gst.ElementFactory.make("autoaudiosink", None)
            )

    def _set_jack_connect(self, sink) -> None:
        """Connect the JACK output where the user chose, so it doesn't start on
        the sound card and get moved there by a patchbay a moment later."""
        if sink is None:
            return
        if jack.IN_FLATPAK or self.jack_connect == jack.NOTHING:
            Gst.util_set_object_arg(sink, "connect", "none")
        elif self.jack_connect != jack.SOUND_CARD:
            sink.set_property("port-pattern", jack.port_pattern(self.jack_connect))

    def change_audio_sink(self, sink_type: AudioSink) -> None:
        """Change the audio sink while maintaining playback state.

        Args:
            sink_type (int): The audio sink `AudioSink` enum
        """
        self._cancel_release()
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
        if not self.gapless_enabled:
            GLib.idle_add(self.play_next)
        elif self.loading_gapless:
            # The next uri wasn't set in time, _play_track_url will play it
            logger.warning("Track ended before the next one was loaded")
            self.reached_eos = True
        elif self.next_track or self.failed_next_track or self._has_next_track():
            logger.warning("Track ended without switching to the next one")
            self.play_next()
        else:
            self.pause()

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

        # The stream URLs expire after a while (e.g. after a long pause or suspend),
        # so reload the track to get new ones and continue from the same position
        elif "Couldn't download fragments" in err.message:
            now = GLib.get_monotonic_time()
            if now - self.last_stream_reload < 30_000_000:
                return
            self.last_stream_reload = now

            logger.error(
                "Stream error: Couldn't download fragments. Reloading track..."
            )
            self._reload_track()

    def _reload_track(self) -> None:
        """Load the playing track again and continue from the same position"""
        self.reloading_track = self.playing_track
        self.play_track(self.playing_track)

    def _stream_expires_soon(self) -> bool:
        """Whether the stream urls of the playing track expire before it's downloaded"""
        if not self.playing_track or not self.stream_loaded_at or self.next_track:
            return False
        uri = self.playbin.get_property("current-uri") or ""
        if uri.startswith("file://") and not uri.endswith(".mpd"):
            # Playing from the music cache
            return False
        # They last about an hour, but very long tracks would never finish in time,
        # so only bother after at least a short pause
        age = time.time() - self.stream_loaded_at
        remaining = max(self.query_duration() - self.query_position(), 0) / Gst.SECOND
        return age > 10 * 60 and age + remaining > 50 * 60

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
        self.playing_from_queue = self.playing_track is self._last_queued_track
        self.can_go_next = len(self._tracks_to_play) > 0
        self.can_go_prev = self._can_go_back()
        self.duration = self.query_duration()
        # Should only trigger when track is enqued on start without playback
        if not self.duration:
            # self.duration is microseconds, but self.playing_track.duration is seconds
            self.duration = self.playing_track.duration * 1_000_000_000
        self.notify("can-go-prev")
        self.notify("can-go-next")
        autoplay_source = self._autoplay_sources.get(self.playing_track.id)
        if autoplay_source is not None and not self.playing_from_queue:
            # Played from the radio autoplay added: say so (Playing from, reports)
            self.play_source = autoplay_source
            self.current_mix_album_playlist = autoplay_source
        self.emit("song-changed")
        self._autoplay_if_ending()

    def _on_track_start(self, bus: Any, message: Any):
        """This Method is called when a new track starts playing

        Args:
            bus: required by Gst
            message: required by Gst
        """
        if self.resuming_released:
            # The same track again, after letting go of the sound card while paused.
            # The duration may not be known yet, so seek to the position itself
            self.resuming_released = False
            position = self.released_at[0] if self.released_at else 0
            self.released_at = None
            logger.info(f"Continuing at {position / Gst.SECOND:.1f}s")
            if position:
                self.last_seek_position = position
                self.playbin.seek_simple(
                    Gst.Format.TIME,
                    Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                    position,
                )
            return

        # apply replaygain first to avoid volume clipping
        # (Idk if that will happen but its the only thing that has effect on audio in here)
        if self.stream:
            self.apply_replaygain_tags()
        self.set_track()
        self.stream_loaded_at = time.time()

        if self.discord_rpc_enabled and self.playing_track:
            discord_rpc.set_activity(self.playing_track, 0)

        if self.update_timer:
            GLib.source_remove(self.update_timer)
        self.update_timer = GLib.timeout_add(1000, self._update_slider_callback)

        self.last_seek_position = None
        self._continue_after_reload()

        self.can_go_prev = self._can_go_back()
        # Only notify to deactivate
        if not self.can_go_prev:
            self.notify("can-go-prev")
            GLib.timeout_add(2000, self.previous_timer_callback)

    def _continue_after_reload(self) -> None:
        """Seek to where the track was before it was loaded again.

        The position to continue at is a fraction of the duration, which GStreamer
        may not know yet when the track starts; seeking then would start it over,
        so it waits for the track to be ready.
        """
        if not self.seek_after_sink_reload:
            return
        success, duration = self.playbin.query_duration(Gst.Format.TIME)
        if not success or duration <= 0:
            logger.info("Duration not known yet, continuing once the track is ready")
            return
        # Continue exactly where it was, without repeating part of the track
        self.seek(self.seek_after_sink_reload, accurate=True)
        self.seek_after_sink_reload = None

    def _on_async_done(self, bus: Any, message: Any) -> None:
        self._continue_after_reload()

    def play_this(
        self,
        thing: Union[Mix, Album, Playlist, List[Track], Track],
        index: int = 0,
        tracks: List[Track] | None = None,
        source=None,
    ) -> None:
        """Play tracks from a mix, album, playlist, or artist.

        Args:
            thing: An object (Mix, Album, Playlist, Artist, or list of Tracks) to play
            index (int): The index of the track to start playing (default: 0)
            tracks: The tracks of thing, if already fetched (default: None)
            source: What a list of tracks was played from (Album, Playlist, Mix,
                Artist), for the plays reported to TIDAL
        """
        self.current_mix_album_playlist = thing
        self.play_source = source if source is not None else thing
        self._autoplay_sources = {}
        if tracks is None:
            tracks = self.get_track_list(thing)
        else:
            tracks = utils.filter_ai_items(tracks)

        if not tracks:
            logger.info("No tracks found to play")
            return

        self.id_list = [track.id for track in tracks]

        if not 0 <= index < len(tracks):
            return
        self._play_order = list(tracks)
        track: Track = tracks[index]

        if not track.available:
            self.play_this(thing, index + 1, tracks, source=source)
        else:
            # As in TIDAL's apps, the music stops after the last song unless
            # repeat is on, and Back plays the songs before the picked one (see
            # _previous_in_order) (#261). With shuffle on, all the others are
            # shuffled.
            if self.shuffle:
                self._tracks_to_play = tracks[index + 1 :] + tracks[:index]
            else:
                self._tracks_to_play = tracks[index + 1 :]
            self.played_songs = []
            self.tracks_to_play = self._tracks_to_play

            if self.shuffle:
                self._update_shuffle_queue()

            # Will result in play() call later
            self.playing = True
            self.play_track(track)

    def shuffle_this(
        self, thing: Union[Mix, Album, Playlist, List[Track], Track], source=None
    ) -> None:
        """Same as play_this, but enables shuffle mode.

        Args:
            thing: An object (Mix, Album, Playlist, Artist, or list of Tracks) to play
            source: What a list of tracks was played from, see play_this
        """
        tracks: List[Track] = self.get_track_list(thing)
        if not tracks:
            return
        # On first, so the songs after a random first one are all of the others
        self.shuffle = True
        self.play_this(thing, random.randrange(len(tracks)), tracks, source=source)

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
            tracks_list = thing.get_top_tracks()
        elif isinstance(thing, list):
            tracks_list = thing
        elif isinstance(thing, Track):
            tracks_list = [thing]

        if tracks_list is None:
            return None

        return utils.filter_ai_items(tracks_list)

    def play(self) -> None:
        """Start playback of the current track."""
        self._cancel_release()
        self.playing = True
        if self.renderer:
            renderer = self.renderer
            resume_at = self._remote_resume_at
            self._remote_resume_at = 0.0

            def resume():
                renderer.play()
                if resume_at:
                    renderer.seek_when_playing(resume_at)

            self._remote_command(resume)
        else:
            if self.released_at:
                self.resuming_released = True
            if self._stream_expires_soon():
                # Resuming after a long pause: get new stream urls (or play the track
                # from the cache) now, instead of failing to download the rest of it
                logger.info("Stream urls expire soon, reloading track")
                self._reload_track()
                return
            self.pipeline.set_state(Gst.State.PLAYING)

        if self.discord_rpc_enabled and self.playing_track:
            discord_rpc.set_activity(
                self.playing_track, self.query_position() / 1_000_000_000
            )
        if self.update_timer:
            GLib.source_remove(self.update_timer)
        self.update_timer = GLib.timeout_add(1000, self._update_slider_callback)

    def pause(self) -> None:
        """Pause playback of the current track."""
        self.playing = False
        if self.renderer:
            self._remote_command(self.renderer.pause)
        else:
            self.pipeline.set_state(Gst.State.PAUSED)
        self._cancel_release()
        if self.sink_type == AudioSink.ALSA and not self.renderer:
            self.release_timer = GLib.timeout_add_seconds(
                ALSA_RELEASE_SECONDS, self._release_sound_card
            )

        if self.discord_rpc_enabled:
            discord_rpc.set_activity()

    def _cancel_release(self) -> None:
        if self.release_timer:
            GLib.source_remove(self.release_timer)
            self.release_timer = None

    def _release_sound_card(self) -> bool:
        """Stop the pipeline while paused, so other programs can use the sound card.

        play() starts the track again from the same position.
        """
        self.release_timer = None
        if self.playing or self.released_at or self.next_track:
            # A track queued for gapless playback would play instead of this one
            return False
        self.released_at = (self.query_position(), self.query_duration())
        self.pipeline.set_state(Gst.State.NULL)
        logger.info("Paused on ALSA, let go of the sound card")
        return False

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
        if self.renderer:
            # Only this computer plays tracks gaplessly, from about-to-finish
            if not gapless:
                # A track still loading here mustn't replace this one on the device
                self.play_request += 1
                self._play_remote(track)
            return
        if gapless:
            self.gapless_request = track
        handed_off_track = self.handed_off_track
        self.handed_off_track = None
        if gapless and track is handed_off_track:
            # The uri was already set in play_next_gapless
            self.next_track = track
            return
        request = None
        if gapless:
            self.loading_gapless = True
        else:
            self.play_request += 1
            request = self.play_request
        threading.Thread(
            target=self._play_track_thread, args=(track, gapless, request)
        ).start()

    def _is_outdated(self, track, request) -> bool:
        """Whether another track was played directly after this one was asked for"""
        if request is None or request == self.play_request:
            return False
        logger.info(f"Dropping track {track.id}: another track was played")
        return True

    def _play_track_thread(self, track: Track, gapless=False, request=None) -> None:
        self.stream = None
        self.manifest = None

        cached_music = self._cached_music_path(track)
        if cached_music:
            self._play_cached_track(track, cached_music, gapless, request)
            return

        try:
            stream = utils.get_stream(track)
            if self._is_outdated(track, request):
                return
            utils.check_stream_quality(track, stream)
            self.stream = stream
            self.manifest = self.stream.get_stream_manifest()
            urls = self.manifest.get_urls()

            music_url = self._get_cached_or_stream_url(track, gapless)

            GLib.idle_add(self._play_track_url, track, music_url, gapless, request)
        except Exception:
            logger.exception("Error getting track URL")
            if gapless:
                GLib.idle_add(self._on_gapless_load_failed, track)

    def _on_gapless_load_failed(self, track: Track) -> None:
        self.loading_gapless = False
        if track is not self.gapless_request:
            return  # another track was played meanwhile
        self.gapless_request = None
        self.failed_next_track = track
        if self.reached_eos:
            # The current track already ended, so nothing would start it
            self.reached_eos = False
            self.play_next()

    def _play_cached_track(self, track, cached_music, gapless=False, request=None) -> None:
        """Play a track from the music cache.

        Its stream info (ReplayGain, quality label) comes from TIDAL, but a slow or
        missing connection (e.g. offline, which retries for minutes) shouldn't hold
        up a track that's on disk, so it plays without it after a short wait.
        """
        info = {}

        def get_info():
            try:
                stream = utils.get_stream(track)
                info["manifest"] = stream.get_stream_manifest()
                info["stream"] = stream
            except Exception:
                logger.warning(f"Couldn't get the stream info of {track.id}")
                return
            if info.get("late"):
                GLib.idle_add(self._set_late_stream_info, track, info)

        thread = threading.Thread(target=get_info, daemon=True)
        thread.start()
        thread.join(2)
        if self._is_outdated(track, request):
            return
        if "stream" in info:
            self.stream, self.manifest = info["stream"], info["manifest"]
        else:
            info["late"] = True
            logger.warning(f"Playing {track.id} from the music cache without its stream info")
        logger.info(f"Playing from music cache: {track.id}")
        GLib.idle_add(
            self._play_track_url, track, f"file://{cached_music}", gapless, request
        )

    def _set_late_stream_info(self, track, info) -> None:
        if self.playing_track is track and not self.stream:
            self.stream, self.manifest = info["stream"], info["manifest"]
            self.apply_replaygain_tags()

    def _cached_music_path(self, track) -> Path | None:
        """Get the track's file in the music cache, if it's there."""
        if not track or not getattr(utils, "MUSIC_DIR", None):
            return None
        cached_music = utils.MUSIC_DIR / f"{track.id}_{utils.session.audio_quality}.m4a"
        return cached_music if cached_music.exists() else None

    def _get_cached_or_stream_url(self, track, gapless=False):
        """Get URL from cache or stream, caching if not cached."""
        cached_music = self._cached_music_path(track)
        if cached_music:
            logger.info(f"Playing from music cache: {track.id}")
            return f"file://{cached_music}"

        return self._get_stream_url(track, gapless)

    def _get_stream_url(self, track, gapless=False):
        """Get stream URL and start background caching."""
        if not gapless:
            self.apply_replaygain_tags()

        if self.stream.manifest_mime_type == ManifestMimeType.MPD:
            data = self.stream.get_manifest_data()
            if not data:
                raise AttributeError("No MPD manifest available!")

            major, minor, micro, nano = Gst.version()
            if (major, minor) >= (1, 26):
                # Write manifest to temp location for GStreamer and caching
                mpd_path = Path(utils.CACHE_DIR, "manifest.mpd")
                with open(mpd_path, "w") as f:
                    f.write(data)

                if not self.monitor.get_network_metered():
                    self._start_caching(track, self._cache_mpd_track, data)

                return f"file://{mpd_path}"
            else:
                if isinstance(data, str):
                    mpd_bytes = data.encode("utf-8")
                else:
                    mpd_bytes = data
                mpd_b64 = base64.b64encode(mpd_bytes).decode("ascii")
                return "data:application/dash+xml;base64," + mpd_b64

        elif self.stream.manifest_mime_type == ManifestMimeType.BTS:
            urls = self.manifest.get_urls()
            stream_url = urls[0] if isinstance(urls, list) else urls

            if not self.monitor.get_network_metered():
                self._start_caching(track, self._cache_bts_track, stream_url)

            return stream_url

        raise AttributeError(f"Unhandled manifest mime type: {self.stream.manifest_mime_type}")

    def _start_caching(self, track, download, source) -> None:
        """Download a track into the music cache in the background, unless it's
        already being downloaded (playing it again while it downloads, e.g. repeat)."""
        cached_music = utils.MUSIC_DIR / f"{track.id}_{utils.session.audio_quality}.m4a"
        with self._cache_lock:
            if self._closing or cached_music in self._cache_downloads:
                return
            self._cache_downloads[cached_music] = None

        def run():
            try:
                download(track, source, cached_music)
            finally:
                with self._cache_lock:
                    self._cache_downloads.pop(cached_music, None)

        # Daemon, so a download never keeps the app running after it closes
        threading.Thread(target=run, daemon=True).start()

    def stop_caching(self) -> None:
        """Stop the music cache downloads, e.g. when the app closes."""
        with self._cache_lock:
            self._closing = True
            downloads = list(self._cache_downloads.items())
        for cached_music, process in downloads:
            if process:
                process.kill()
                process.wait()
            # The app can end before the download's own thread cleans up
            cached_music.with_suffix(".tmp").unlink(missing_ok=True)
            cached_music.with_suffix(".mpd").unlink(missing_ok=True)

    def _cache_mpd_track(self, track, manifest, cached_music):
        """Download and cache MPD track via ffmpeg in background."""
        tmp = cached_music.with_suffix(".tmp")
        # Its own copy of the manifest: the shared one is replaced by the next track
        mpd_path = cached_music.with_suffix(".mpd")

        try:
            import subprocess
            logger.info(f"Caching MPD track: {track.id}")
            mpd_path.write_text(manifest)
            process = subprocess.Popen(
                [
                    "ffmpeg",
                    # Leave the terminal alone when started from one: reading it from
                    # the sandbox's background process group stops the whole app
                    "-nostdin",
                    "-protocol_whitelist", "file,crypto,data,http,https,tcp,tls",
                    "-i", str(mpd_path),
                    "-f", "mp4",
                    "-c", "copy",
                    "-y", str(tmp)
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            with self._cache_lock:
                self._cache_downloads[cached_music] = process
                closing = self._closing
            if closing:
                process.kill()
            _, stderr = process.communicate()

            if self._closing:
                tmp.unlink(missing_ok=True)
            elif process.returncode != 0:
                logger.warning(f"ffmpeg failed for {track.id}: {stderr.decode()}")
                tmp.unlink(missing_ok=True)
            elif missing := self._find_missing_audio(tmp, track.duration):
                errors = [
                    line for line in stderr.decode().splitlines()
                    if "error" in line.lower() or "failed" in line.lower()
                ]
                logger.warning(f"Not caching {track.id}, {missing}: {errors}")
                tmp.unlink(missing_ok=True)
            else:
                tmp.rename(cached_music)
                logger.info(f"Cached MPD track: {track.id}")
        except Exception as e:
            logger.warning(f"Failed to cache MPD track {track.id}: {e}")
            tmp.unlink(missing_ok=True)
        finally:
            mpd_path.unlink(missing_ok=True)

    def _find_missing_audio(self, path, duration) -> str | None:
        """Describe the audio missing from a downloaded track, if any.

        ffmpeg skips a segment of an MPD stream it can't download and still exits
        successfully, so the cached file would go silent there on every play.
        """
        import subprocess
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "packet=pts_time",
                "-of", "csv=p=0",
                str(path)
            ],
            capture_output=True,
            text=True,
            check=True
        )

        previous = 0.0
        for line in result.stdout.splitlines():
            position = float(line.split(",")[0])
            if position - previous > MAX_CACHE_GAP:
                return f"no audio from {previous:.1f} s to {position:.1f} s"
            previous = position

        if duration - previous > MAX_CACHE_GAP:
            return f"audio ends at {previous:.1f} s of {duration} s"
        return None

    def _cache_bts_track(self, track, stream_url, cached_music):
        """Download and cache BTS track in background."""
        tmp = cached_music.with_suffix(".tmp")

        try:
            import requests
            logger.info(f"Caching BTS track: {track.id}")
            response = requests.get(stream_url, stream=True)
            if response.status_code == 200:
                with open(tmp, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self._closing:
                            break
                        f.write(chunk)
                if self._closing:
                    tmp.unlink(missing_ok=True)
                    return
                tmp.rename(cached_music)
                logger.info(f"Cached BTS track: {track.id}")
            else:
                logger.warning(f"BTS download failed for {track.id}: HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to cache BTS track {track.id}: {e}")
            tmp.unlink(missing_ok=True)

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

    def _play_track_url(self, track, music_url, gapless=False, request=None):
        """Set up and play track from URL."""
        if self._is_outdated(track, request):
            return
        if self.renderer:
            # A device was picked while the track was loading here
            if not gapless:
                self._play_remote(track)
            return
        if gapless:
            self.loading_gapless = False
            if track is not self.gapless_request:
                logger.info(f"Dropping gapless track {track.id}: another track was played")
                return
            if self.reached_eos:
                # Too late for gapless, the previous track already ended
                gapless = False
        if not gapless and track is self.reloading_track:
            # What was already downloaded keeps playing while the track loads again,
            # so continue from where it is now, not from where the reload started
            duration = self.query_duration()
            if duration:
                self.seek_after_sink_reload = self.query_position() / duration
        if not gapless:
            self._cancel_release()
            self.released_at = None
            self.resuming_released = False
            # A track played directly replaces the one queued for gapless playback,
            # which would otherwise be shown as playing when this one starts
            self.gapless_request = None
            self.next_track = None
            self.failed_next_track = None
            self.reached_eos = False
            self.reloading_track = None
            self.use_about_to_finish = False
            self.pipeline.set_state(Gst.State.NULL)
            self.playbin.set_property("volume", self.playbin.get_property("volume"))
        self.playbin.set_property("uri", music_url)

        logger.info(music_url)

        if gapless:
            self.next_track = track
        else:
            self.set_track(track)
            self.stream_loaded_at = time.time()

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
        if self.gapless_enabled and self.use_about_to_finish and self._has_next_track():
            # The current track can reach EOS soon after this signal, and then
            # a uri set later is ignored, so set it now if it's ready
            self._set_prefetched_uri()
            GLib.idle_add(self.play_next, True)
            logger.info("Trying gapless playbck")
        else:
            logger.info("Ignoring about to finish event")

    def _has_next_track(self) -> bool:
        """Whether play_next will play a track after the current one"""
        return bool(
            self.tracks_to_play
            or self.queue
            or (self.playing_track and self._repeat_type != RepeatType.NONE)
        )

    def _peek_next_track(self) -> Track | None:
        """Get the track play_next(gapless=True) would play, without removing it"""
        if self._repeat_type == RepeatType.SONG:
            return self.playing_track
        if self.queue:
            return self.queue[0]
        if self.shuffle:
            track_list = self._shuffled_tracks_to_play
        else:
            track_list = self._tracks_to_play
        if not track_list and self._repeat_type == RepeatType.LIST and not self.shuffle:
            # play_next starts the list again
            return (self._play_order or self.played_songs or [self.playing_track])[0]
        return track_list[0] if track_list else None

    def _prefetch_next_track(self) -> None:
        """Fetch the stream of the next track in the background"""
        if self.next_track or self.handed_off_track or self.loading_gapless:
            return
        if not self._has_next_track():
            return
        track = self._peek_next_track()
        if not track or track.id == self.prefetch_id:
            return
        self.prefetch_id = track.id
        threading.Thread(target=self._prefetch_thread, args=(track,)).start()

    def _prefetch_thread(self, track: Track) -> None:
        try:
            stream = utils.get_stream(track)
            utils.check_stream_quality(track, stream)
            manifest = stream.get_stream_manifest()
            if self.prefetch_id != track.id:
                return  # the next track changed meanwhile
            self.prefetched = (track.id, stream, manifest, GLib.get_monotonic_time())
            logger.info(f"Prefetched stream: {track.id}")
        except Exception:
            logger.exception("Error prefetching track stream")

    def _set_prefetched_uri(self) -> None:
        """Set the uri of the next track from its prefetched stream, if any.

        Called from a streaming thread in about-to-finish.
        """
        prefetched = self.prefetched
        self.prefetched = None
        self.prefetch_id = None
        track = self._peek_next_track()
        if not prefetched or not track:
            return
        track_id, stream, manifest, fetched_at = prefetched
        # Stream urls expire an hour after they are fetched
        too_old = GLib.get_monotonic_time() - fetched_at > 30 * 60 * 1_000_000
        if track_id != track.id or too_old:
            return
        try:
            self.stream = stream
            self.manifest = manifest
            music_url = self._get_cached_or_stream_url(track, gapless=True)
        except Exception:
            logger.exception("Error using prefetched stream")
            return
        self.playbin.set_property("uri", music_url)
        self.handed_off_track = track
        logger.info(f"Using prefetched stream: {music_url}")

    def play_next(self, gapless=False, skip=False):
        """Play the next track in the queue or playlist.

        Args:
            gapless: Whether to enqueue the track in gapless mode
            skip: The user asked for the next track, so repeating one track
                doesn't apply: it's only for when the track ends
        """
        repeat_song = self._repeat_type == RepeatType.SONG and not skip
        if skip and self._repeat_type == RepeatType.SONG and self.next_track:
            if self.playing_track and self.next_track.id == self.playing_track.id:
                # The repeat queued for gapless playback: play the next track instead
                self.next_track = None
        if skip and self._repeat_type == RepeatType.SONG and self.failed_next_track:
            if self.playing_track and self.failed_next_track.id == self.playing_track.id:
                self.failed_next_track = None

        if self.failed_next_track:
            # Loading it for gapless playback failed: try it again
            track = self.failed_next_track
            self.failed_next_track = None
            self.play_track(track, gapless=gapless)
            return

        # A track is already enqueued from an about-to-finish
        if self.next_track:
            logger.info("Using already enqueued track from gapless")
            track = self.next_track
            self.next_track = None
            self.play_track(track, gapless=gapless)
            return

        if repeat_song and not gapless:
            self.seek(0)
            self.apply_replaygain_tags()
            return
        if repeat_song:
            self.play_track(self.playing_track, gapless=True)
            return

        if self.playing_track:
            self.played_songs.append(self.playing_track)

        if self.queue:
            track = self.queue.pop(0)
            self._last_queued_track = track
            self.play_track(track, gapless=gapless)
            return

        if not self.tracks_to_play and self._repeat_type == RepeatType.LIST:
            # The whole list again from its first song
            self._tracks_to_play = list(self._play_order) or self.played_songs
            self.played_songs = []
            self._update_shuffle_queue()

        if not self.tracks_to_play:
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

    def skip_hidden(self) -> None:
        """Leave out hidden tracks from what is left to play.

        Hidden tracks are the blocked ones, and AI-generated ones when they are
        set to be hidden. Removes them from the rest of the playing list and the
        played songs, and skips the playing track if it was just hidden, as the
        official apps do.
        """
        self._drop_hidden()

        if self.playing_track and utils.is_hidden_track(self.playing_track):
            has_next = (
                self.queue
                or self._tracks_to_play
                or (
                    self._repeat_type == RepeatType.LIST
                    and (self._play_order or self.played_songs)
                )
            )
            if self._repeat_type == RepeatType.SONG or not has_next:
                self.pause()
            else:
                self.play_next()
                # play_next adds the hidden track to the played songs
                self._drop_hidden()

        self.can_go_next = len(self._tracks_to_play) > 0
        self.emit("song-added-to-queue")

    def _autoplay_if_ending(self) -> None:
        """With autoplay on and repeat off, when the last song of the list starts,
        load its radio and add the songs not heard yet as the next songs, so the
        music goes on (and the change to them stays gapless)"""
        track = self.playing_track
        if (
            not self.autoplay
            or track is None
            or self._repeat_type != RepeatType.NONE
            or self.queue
            or self.tracks_to_play  # the list played from (the shuffled one too)
            or self._autoplay_loading_for == track.id
        ):
            return
        self._autoplay_loading_for = track.id
        heard = {t.id for t in self.played_songs} | {track.id}

        def load():
            try:
                mix = utils.get_track(track.id).get_radio_mix()
                songs = [
                    t
                    for t in mix.items()
                    if isinstance(t, Track)
                    and t.id not in heard
                    and getattr(t, "available", True)
                    and not utils.is_hidden_track(t)
                ]
            except Exception:
                logger.exception(f"Could not load the radio of {track.id} for autoplay")
                mix, songs = None, []
            GLib.idle_add(add, mix, songs)

        def add(mix, songs):
            self._autoplay_loading_for = None
            # Only if the list still ends with this song
            if (
                not songs
                or self.playing_track is not track
                or self.queue
                or self.tracks_to_play
                or self._repeat_type != RepeatType.NONE
            ):
                return False
            logger.info(f"Autoplay: {len(songs)} songs from the radio of {track.id}")
            for song in songs:
                self._autoplay_sources[song.id] = mix
            self._tracks_to_play.extend(songs)
            self._play_order.extend(songs)
            if self.shuffle:
                self._shuffled_tracks_to_play.extend(songs)
            self.tracks_to_play = (
                self._shuffled_tracks_to_play if self.shuffle else self._tracks_to_play
            )
            self.can_go_next = True
            self.notify("can-go-next")
            self.emit("next-songs-changed")
            return False

        threading.Thread(target=load, daemon=True).start()

    def _drop_hidden(self) -> None:
        for track_list in (
            self.queue,
            self._tracks_to_play,
            self._shuffled_tracks_to_play,
            self.played_songs,
            self._play_order,
        ):
            track_list[:] = [
                track for track in track_list if not utils.is_hidden_track(track)
            ]

    def get_playing_source(self):
        """What the playing track was played from: an Album, Playlist, Mix or
        Artist, or something else (a track or a list) when it was played on its own
        or from the queue"""
        if self.playing_from_queue:
            return self.playing_track
        return self.play_source

    def play_previous(self):
        """Play the previous track or restart current track if near beginning."""
        # if not in the first 2 seconds of the track restart song
        if self.query_position() > 2 * Gst.SECOND:
            self.seek(0)
            self.can_go_prev = self._can_go_back()
            # only notify when can't go to previous
            if not self.can_go_prev:
                self.notify("can-go-prev")
                GLib.timeout_add(2000, self.previous_timer_callback)
            return

        if self.played_songs:
            track = self.played_songs.pop()
        else:
            track = self._previous_in_order()
            if track is None:
                return
        if self.playing_track:
            self._tracks_to_play.insert(0, self.playing_track)
        self.play_track(track)

    def _previous_in_order(self) -> Track | None:
        """The song before the current one in the list played from, for Back
        when nothing was played before it: after picking a song in the middle of
        an album, the played songs only hold what was really played (#261)"""
        if self.shuffle or self.playing_from_queue or not self.playing_track:
            return None
        for position, track in enumerate(self._play_order):
            if track is self.playing_track:
                return self._play_order[position - 1] if position > 0 else None
        return None

    def _can_go_back(self) -> bool:
        return bool(self.played_songs) or self._previous_in_order() is not None

    def play_from_next_songs(self, index: int) -> None:
        """Play a track from the tracks to play, as shown in the queue.

        Same as pressing Next until it, but the queued tracks stay queued.
        """
        track_list = (
            self._shuffled_tracks_to_play if self.shuffle else self._tracks_to_play
        )
        if not 0 <= index < len(track_list):
            return
        if self.playing_track:
            self.played_songs.append(self.playing_track)
        self.played_songs.extend(track_list[:index])
        track = track_list[index]
        del track_list[: index + 1]
        # Clicking a song plays it, also when paused
        self.playing = True
        self.play_track(track)

    def play_from_queue(self, index: int) -> None:
        """Play a queued track now, the rest of the queue stays as it is"""
        if not 0 <= index < len(self.queue):
            return
        if self.playing_track:
            self.played_songs.append(self.playing_track)
        track = self.queue.pop(index)
        self._last_queued_track = track
        self.playing = True
        self.play_track(track)

    def play_from_played_songs(self, index: int) -> None:
        """Play a track from the played songs, same as pressing Previous until it"""
        if not 0 <= index < len(self.played_songs):
            return
        track = self.played_songs[index]
        back = self.played_songs[index + 1 :]
        if self.playing_track:
            back.append(self.playing_track)
        del self.played_songs[index:]
        track_list = (
            self._shuffled_tracks_to_play if self.shuffle else self._tracks_to_play
        )
        track_list[:0] = back
        self.playing = True
        self.play_track(track)

    def previous_timer_callback(self):
        """Send a notify Event after 2s of the song playing"""
        self.can_go_prev = True
        self.notify("can-go-prev")

    def _continue_in_order(self) -> None:
        """Make the tracks after the current one, in the list's order, play next.

        Used when shuffle is turned off: the official apps carry on from the
        current track instead of going back to where the list was started.
        """
        if self.playing_track and not self.playing_from_queue:
            current = self.playing_track
        else:
            # Playing something from the queue: continue after the last list track
            current = next(
                (t for t in reversed(self.played_songs) if self._in_play_order(t)),
                None,
            )
        for position, track in enumerate(self._play_order):
            if track is current:
                self._tracks_to_play = self._play_order[position + 1 :]
                self.can_go_next = len(self._tracks_to_play) > 0
                self.notify("can-go-next")
                return

    def _in_play_order(self, track: Track) -> bool:
        return any(t is track for t in self._play_order)

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
        self._on_upcoming_changed()

    def add_next(self, track):
        """Add a track to the top of the queue.

        Args:
            track: The Track object to play next
        """
        self.queue.insert(0, track)
        self._on_upcoming_changed()

    def add_tracks_to_queue(self, tracks: List[Track], next_up: bool = False) -> None:
        """Queue several songs in their order: at the end of the queue, or before
        everything queued with next_up (a whole album or playlist, #259)"""
        if next_up:
            self.queue[0:0] = tracks
        else:
            self.queue.extend(tracks)
        self._on_upcoming_changed()

    def remove_from_queue(self, index: int) -> None:
        """Remove a track from the queue"""
        if not 0 <= index < len(self.queue):
            return
        del self.queue[index]
        self._on_upcoming_changed()

    def move_in_queue(self, index: int, new_index: int) -> None:
        """Move a queued track to another place in the queue.

        Args:
            index: Where the track is now
            new_index: Where it goes, counted without the track itself
        """
        if not 0 <= index < len(self.queue):
            return
        track = self.queue.pop(index)
        self.queue.insert(max(0, min(new_index, len(self.queue))), track)
        self._on_upcoming_changed()

    def clear_queue(self) -> None:
        """Remove all tracks from the queue"""
        self.queue.clear()
        self._on_upcoming_changed()

    def remove_from_next_songs(self, index: int) -> None:
        """Remove a track from the rest of the playing list, as shown in the queue"""
        track_list = (
            self._shuffled_tracks_to_play if self.shuffle else self._tracks_to_play
        )
        if not 0 <= index < len(track_list):
            return
        track = track_list.pop(index)
        # Also from the other orders of the list, so it doesn't come back when
        # shuffle is turned off
        for other in (self._tracks_to_play, self._shuffled_tracks_to_play, self._play_order):
            if other is track_list:
                continue
            for position, t in enumerate(other):
                if t is track:
                    del other[position]
                    break
        self.can_go_next = len(self._tracks_to_play) > 0
        self.notify("can-go-next")
        self._on_upcoming_changed()

    def clear_next_songs(self) -> None:
        """Remove the rest of the playing list, as shown in the queue. The current
        track keeps playing, then the queued tracks, if any."""
        self._tracks_to_play.clear()
        self._shuffled_tracks_to_play.clear()
        # Nothing to continue from when shuffle is turned off
        self._play_order = []
        self.can_go_next = False
        self.notify("can-go-next")
        self._on_upcoming_changed()

    def move_in_next_songs(self, index: int, new_index: int) -> None:
        """Move a track to another place in the rest of the playing list.

        With shuffle on this changes the shuffled order only, and turning shuffle
        off goes back to the list's order. Without shuffle the new order is kept,
        also when shuffle is turned on and off again.

        Args:
            index: Where the track is now, as shown in the queue
            new_index: Where it goes, counted without the track itself
        """
        track_list = (
            self._shuffled_tracks_to_play if self.shuffle else self._tracks_to_play
        )
        if not 0 <= index < len(track_list):
            return
        track = track_list.pop(index)
        track_list.insert(max(0, min(new_index, len(track_list))), track)
        if not self.shuffle:
            # Turning shuffle off continues from this order
            self._play_order = [
                t for t in self._play_order if not any(t is x for x in track_list)
            ] + track_list
        self._on_upcoming_changed()

    def _on_upcoming_changed(self) -> None:
        """The tracks to play next changed: fetch the new next track early instead"""
        if self.prefetch_id is not None:
            track = self._peek_next_track()
            if not track or track.id != self.prefetch_id:
                self.prefetch_id = None
                self.prefetched = None
                if track:
                    self._prefetch_next_track()
        self.emit("song-added-to-queue")

    def query_volume(self):
        """Get the current playback volume.

        Returns:
            float: Current volume level (0.0 to 1.0), adjusted for quadratic scaling if enabled
        """
        if self.renderer:
            return self.remote_volume
        volume = self.playbin.get_property("volume")
        if self.quadratic_volume:
            return volume ** (1 / 2)
        return volume

    def change_volume(self, value):
        """Set the playback volume.

        Args:
            value (float): Volume level (0.0 to 1.0), will be squared if quadratic volume is enabled
        """
        if self.renderer:
            # The device's own volume, which has its own curve
            self.remote_volume = value
            with self._remote_volume_lock:
                self._remote_volume_pending += 1
            self._remote_command(self._set_remote_volume, self.renderer, round(value * 100))
        elif self.quadratic_volume:
            self.playbin.set_property("volume", value**2)
        else:
            self.playbin.set_property("volume", value)
        self.emit("volume-changed", value)

    def _update_slider_callback(self):
        """Update playback slider and duration."""
        if not self.duration:
            logger.warning("Duration missing, trying again")
            self.duration = self.query_duration()
        if not self.renderer:
            if self.gapless_enabled and self.duration:
                if self.duration - self.query_position() < 30 * Gst.SECOND:
                    self._prefetch_next_track()
            self._check_stream_stuck()
        self.emit("update-slider")
        if not self.playing:
            # Returning False removes the timer. While it keeps running, keep its id
            # so the next play() or track start replaces it instead of adding another
            self.update_timer = None
        return self.playing

    def _check_stream_stuck(self) -> None:
        """Continue from the music cache if the stream of the playing track is stuck.

        E.g. the internet went out: the track may have been cached in the meantime.
        """
        position = self.query_position(-1)
        now = time.monotonic()
        if not self.playing or position != self.last_position:
            self.last_position = position
            self.position_stuck_since = now
            return
        # During a gapless change the next track is loading, also when the track
        # already ended before it was ready
        if now - self.position_stuck_since < 3 or self.next_track or self.reached_eos:
            return
        cached_music = self._cached_music_path(self.playing_track)
        uri = self.playbin.get_property("current-uri") or ""
        if not cached_music or uri == f"file://{cached_music}":
            return

        self.position_stuck_since = now
        if position <= 0 and self.last_seek_position is not None:
            # Stuck right after a seek, before anything could be downloaded
            position = self.last_seek_position
        duration = self.query_duration()
        if duration and position > 0:
            self.seek_after_sink_reload = position / duration
        logger.warning("Stream stuck, continuing from the music cache")
        self._play_track_url(self.playing_track, f"file://{cached_music}")

    def query_duration(self):
        """Get the duration of the current track.

        Returns:
            int: Duration in nanoseconds, or 0 if query failed
        """
        if self.renderer:
            return int(self.remote_duration * Gst.SECOND)
        if self.released_at:
            return self.released_at[1]
        success, duration = self.playbin.query_duration(Gst.Format.TIME)
        return duration if success else 0

    def query_position(self, default=0) -> int | None:
        """Get the current playback position.

        Args:
            default (int): Default value to return if query fails (default: 0)

        Returns:
            int: Position in nanoseconds, or default value if query failed
        """
        if self.renderer:
            return int(self.remote_position * Gst.SECOND)
        if self.released_at:
            return self.released_at[0]
        success, position = self.playbin.query_position(Gst.Format.TIME)
        return position if success else default

    def seek(self, seek_fraction, accurate=False):
        """Seek to a position in the current track.

        Args:
            seek_fraction (float): Position as a fraction of total duration (0.0 to 1.0)
            accurate (bool): Seek to the exact position instead of the nearest
                keyframe, which can be seconds earlier in a stream
        """

        old_position = self.query_position(default=0)
        duration = self.query_duration()
        position = int(seek_fraction * duration)
        # A stream seeked to its very end can stop without ever ending, so land a
        # second before it: the song then ends and the next one starts as usual
        position = min(position, max(duration - Gst.SECOND, 0))
        if self.renderer:
            self.remote_position = position / Gst.SECOND
            if self._remote_resume_at:
                self._remote_resume_at = self.remote_position
            else:
                self._remote_command(self.renderer.seek, self.remote_position)
            self.emit("seeked", old_position / Gst.SECOND, position / Gst.SECOND)
            return
        if self.released_at:
            # Paused without the sound card: play() continues from here
            self.released_at = (position, self.released_at[1])
            return
        flags = Gst.SeekFlags.ACCURATE if accurate else Gst.SeekFlags.KEY_UNIT
        self.last_seek_position = position
        self.playbin.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | flags, position
        )
        self.emit("seeked", old_position / Gst.SECOND, position / Gst.SECOND)

        if self.discord_rpc_enabled:
            discord_rpc.set_activity(self.playing_track, position // 1_000_000_000)

    def set_renderer(self, renderer: "dlna.Renderer | cast.CastDevice | None") -> None:
        """Play on a DLNA or Google Cast device, or on this computer with None.

        The playing track continues at the same position on the new output.
        """
        if renderer == self.renderer:
            return
        position = self.query_position() / Gst.SECOND if self.playing_track else 0
        old = self.renderer
        self._remote_token += 1
        self._remote_resume_at = 0.0
        if old:
            self._remote_command(old.stop)
            if isinstance(old, cast.CastDevice):
                self._remote_command(old.close)
        else:
            self._cancel_release()
            self.released_at = None
            self.next_track = None
            self.handed_off_track = None
            self.pipeline.set_state(Gst.State.NULL)
        if renderer and not self._media_server:
            # Files left from an earlier run
            shutil.rmtree(Path(utils.CACHE_DIR, "dlna"), ignore_errors=True)
            self._media_server = dlna.MediaServer()
        self.renderer = renderer
        logger.info(f"Playing on {renderer.name if renderer else 'this computer'}")
        self.emit("renderer-changed")
        if renderer:
            # Unavailable until the device says its volume, so the slider can't send
            # this computer's level to it first
            self.volume_available = False
            self._remote_volume_set_at = 0.0
            self._remote_command(self._read_remote_volume, renderer)
        else:
            self.volume_available = True
            self.emit("volume-changed", self.query_volume())
        if not self.playing_track:
            return
        if renderer:
            self._play_remote(self.playing_track, position, switching=True)
        else:
            if self.playing_track.duration:
                self.seek_after_sink_reload = position / self.playing_track.duration
            self.play_track(self.playing_track)

    def _set_remote_volume(self, renderer, volume: int) -> None:
        try:
            renderer.set_volume(volume)
        finally:
            with self._remote_volume_lock:
                self._remote_volume_set_at = time.monotonic()
                self._remote_volume_pending -= 1

    def _read_remote_volume(self, renderer) -> None:
        volume = None
        try:
            volume = renderer.get_volume()
        finally:
            if volume is None:
                logger.info(f"No volume from {renderer.name}, the slider is off")
            GLib.idle_add(
                self._on_remote_volume, renderer, volume, time.monotonic(), True
            )

    def _on_remote_volume(
        self, renderer, volume: int | None, read_at: float, first=False
    ) -> bool:
        """Show the device's volume, read at read_at (None: it has none)"""
        if renderer != self.renderer:
            return False
        if volume is None:
            self.volume_available = False
            return False
        if self._remote_volume_pending or read_at - self._remote_volume_set_at < 2:
            # Read before a volume being sent had reached it
            self.volume_available = True
            return False
        changed = abs(volume / 100 - self.remote_volume) > 0.005
        self.remote_volume = volume / 100
        self.volume_available = True
        if changed or first:
            self.emit("volume-changed", self.remote_volume)
        return False

    def _remote_command(self, function, *args) -> None:
        def run():
            try:
                function(*args)
            except Exception as e:
                logger.warning(f"DLNA device: {e}")

        self._remote_commands.submit(run)

    def _play_remote(self, track: Track, position: float = 0, switching=False) -> None:
        self._remote_token += 1
        threading.Thread(
            target=self._remote_load,
            args=(self.renderer, track, position, self._remote_token, switching),
            daemon=True,
        ).start()

    def _remote_load(self, renderer, track, position, token, switching) -> None:
        """Get a track ready and send it to the device"""
        try:
            path = self._prepare_remote_file(track)
            if token != self._remote_token:
                return
            url = self._media_server.add(path, "audio/flac", renderer.host, "flac")
            cover_url = self._remote_cover_url(renderer, track)

            def load():
                if token != self._remote_token:
                    return
                renderer.load(url, "audio/flac", track, cover_url)
                if self.playing:
                    renderer.play()
                    if position > 1:
                        renderer.seek_when_playing(position)

            self._remote_commands.submit(load).result()
        except Exception:
            logger.exception("Couldn't play on the DLNA device")
            GLib.idle_add(self._remote_failed, renderer, token)
            return
        GLib.idle_add(self._remote_started, renderer, track, position, token, switching)

    def _remote_cover_url(self, renderer, track) -> str | None:
        """The album cover's address for the device, which can't open files here"""
        album = getattr(track, "album", None)
        if not album:
            return None
        try:
            cover = utils.get_image_url(album, 640)
        except Exception:
            logger.warning(f"Couldn't get the cover of {track.id} for the device")
            return None
        if not cover or not Path(cover).is_file():
            return None
        return self._media_server.add_cover(Path(cover), renderer.host)

    def _remote_started(self, renderer, track, position, token, switching) -> bool:
        if token != self._remote_token:
            return False
        self.remote_position = position
        self.remote_duration = float(track.duration or 0)
        if not self.playing and position > 1:
            self._remote_resume_at = position
        if switching and track is self.playing_track:
            # The same play, only on another output
            self.duration = self.query_duration()
        else:
            self.set_track(track)
        if self.playing and self.discord_rpc_enabled:
            discord_rpc.set_activity(track, position)
        if self.update_timer:
            GLib.source_remove(self.update_timer)
        self.update_timer = GLib.timeout_add(1000, self._update_slider_callback)
        threading.Thread(
            target=self._poll_remote, args=(renderer, token), daemon=True
        ).start()

        # Get the next track ready, so it starts without waiting
        keep = [self._remote_file_path(track)]
        next_track = self._peek_next_track()
        if next_track and next_track is not track:
            keep.append(self._remote_file_path(next_track))
            threading.Thread(
                target=self._prepare_next_remote_file, args=(next_track,), daemon=True
            ).start()
        self._media_server.remove_all_but(keep)
        return False

    def _remote_failed(self, renderer, token) -> bool:
        if token == self._remote_token:
            self.playing = False
            utils.send_toast(_("Couldn't play on {}").format(renderer.name), 5)
        return False

    def _poll_remote(self, renderer, token) -> None:
        """Follow the position on the device, play the next track at the end, and
        step back when another app takes the device over"""
        was_playing = False
        # Kodi starts a loaded track by itself, also when it was loaded paused
        settle_until = time.monotonic() + dlna.LOAD_GRACE
        while token == self._remote_token:
            try:
                position, duration = renderer.get_position()
                state = renderer.get_state()
            except Exception as e:
                logger.warning(f"DLNA device not answering: {e}")
                time.sleep(2)
                continue
            if token != self._remote_token:
                return
            if self.volume_available:
                # Follows changes made on the device itself or by another app
                read_at = time.monotonic()
                try:
                    volume = renderer.get_volume()
                except Exception as e:
                    logger.debug(f"Couldn't read the device's volume: {e}")
                else:
                    GLib.idle_add(self._on_remote_volume, renderer, volume, read_at)
            if state == "TAKEN_OVER":
                GLib.idle_add(self._remote_taken_over, renderer, token)
                return
            if (
                state == "PLAYING"
                and not self.playing
                and time.monotonic() < settle_until
            ):
                logger.info(f"{renderer.name} started by itself, pausing it")
                self._remote_command(renderer.pause)
            if state in ("PLAYING", "PAUSED_PLAYBACK"):
                was_playing = was_playing or state == "PLAYING"
                self.remote_position = position
                if duration:
                    self.remote_duration = duration
            elif state in ("STOPPED", "NO_MEDIA_PRESENT") and was_playing:
                if self.playing:
                    if self.remote_position < self.remote_duration - 5:
                        # Stopped from elsewhere (its remote, another app), not ended
                        GLib.idle_add(self._remote_taken_over, renderer, token)
                    else:
                        GLib.idle_add(self._remote_ended, token)
                    return
            time.sleep(1)

    def _remote_taken_over(self, renderer, token) -> bool:
        """Leave the device to the other app: pause here at the same position"""
        if token != self._remote_token:
            return False
        logger.info(f"{renderer.name} was taken over by another app")
        position = self.remote_position
        self._remote_token += 1
        self._remote_resume_at = 0.0
        self.renderer = None
        if isinstance(renderer, cast.CastDevice):
            # Only this app's connection: the other app keeps playing
            self._remote_command(renderer.close)
        self.playing = False
        self.emit("renderer-changed")
        self.volume_available = True
        self.emit("volume-changed", self.query_volume())
        if self.playing_track:
            if self.playing_track.duration:
                self.seek_after_sink_reload = position / self.playing_track.duration
            self.play_track(self.playing_track)
        utils.send_toast(_("{} is playing something else").format(renderer.name), 5)
        return False

    def _remote_ended(self, token) -> bool:
        if token != self._remote_token or not self.playing:
            return False
        logger.info("Track ended on the DLNA device")
        if self._repeat_type == RepeatType.SONG and self.playing_track:
            self._play_remote(self.playing_track)
        else:
            self.play_next()
        return False

    def _remote_file_path(self, track: Track) -> Path:
        quality = utils.session.audio_quality if utils.session else ""
        return Path(utils.CACHE_DIR, "dlna", f"{track.id}_{quality}.flac")

    def _prepare_next_remote_file(self, track: Track) -> None:
        try:
            self._prepare_remote_file(track)
        except Exception:
            logger.exception("Couldn't get the next track ready for the DLNA device")

    def _prepare_remote_file(self, track: Track) -> Path:
        """Turn a track into a FLAC file the device can play"""
        path = self._remote_file_path(track)
        lock = self._remote_prepare_locks.setdefault(str(track.id), threading.Lock())
        with lock:
            if path.exists():
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path = None
            cached = self._cached_music_path(track)
            if cached:
                source = cached.as_uri()
            else:
                stream = utils.get_stream(track)
                if stream.manifest_mime_type == ManifestMimeType.MPD:
                    manifest_path = path.with_suffix(".mpd")
                    manifest_path.write_text(stream.get_manifest_data())
                    source = manifest_path.as_uri()
                else:
                    urls = stream.get_stream_manifest().get_urls()
                    source = urls[0] if isinstance(urls, list) else urls
            start = time.monotonic()
            try:
                dlna.prepare_flac(source, path)
            finally:
                if manifest_path:
                    manifest_path.unlink(missing_ok=True)
            logger.info(
                f"Got {track.id} ready for the DLNA device in "
                f"{time.monotonic() - start:.1f} s"
            )
        return path

    def set_discord_rpc(self, enabled: bool = True):
        """Enable or disable Discord Rich Presence integration.

        Args:
            enabled (bool): Whether to enable Discord RPC (default: True)
        """
        self.discord_rpc_enabled = enabled
        if enabled and self.playing:
            discord_rpc.set_activity(
                self.playing_track,
                self.query_position() / 1_000_000_000,
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
