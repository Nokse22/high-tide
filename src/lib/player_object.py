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

import random
import threading
from enum import IntEnum
from pathlib import Path

from tidalapi.mix import Mix
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.playlist import Playlist
from tidalapi.media import ManifestMimeType, Track

from gi.repository import GObject
from gi.repository import Gst, GLib

from . import utils
from . import discord_rpc



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


class PlayerObject(GObject.GObject):
    """Handles player logic, queue, and shuffle functionality."""

    current_song_index = GObject.Property(type=int, default=-1)

    __gsignals__ = {
        'songs-list-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'update-slider': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'song-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'song-added-to-queue': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'duration-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'volume-changed': (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        'buffering': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, preferred_sink=AudioSink.AUTO, normalize=False, quadratic_volume=False):
        GObject.GObject.__init__(self)

        Gst.init(None)

        version_str = Gst.version_string()
        print(f"GStreamer version: {version_str}")

        self.pipeline = Gst.Pipeline.new("dash-player")

        self.playbin = Gst.ElementFactory.make("playbin3", "playbin")
        if not self.playbin:
            print("Could not create playbin3 element, trying playbin...")
            self.playbin = Gst.ElementFactory.make("playbin", "playbin")

        self.pipeline.add(self.playbin)

        self.normalize = normalize
        self.quadratic_volume = quadratic_volume
        self.most_recent_rg_tags = ""

        # Configure audio sink
        self._setup_audio_sink(preferred_sink)

        # Set up message bus
        self._bus = self.pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect('message::eos', self._on_bus_eos)
        self._bus.connect('message::error', self._on_bus_error)
        self._bus.connect('message::buffering', self._on_buffering_message)

        # Initialize state utils
        self._shuffle = False
        self._playing = False
        self._repeat_type = RepeatType.NONE

        self.id_list = []

        self.queue = []
        self.current_mix_album_playlist = None
        self._tracks_to_play = []
        self.tracks_to_play = []
        self._shuffled_tracks_to_play = []
        self.played_songs = []
        self.playing_track: Track | None = None
        self.song_album = None
        self.duration = self.query_duration()
        self.can_next = False
        self.can_prev = False
        self.manifest = None
        self.stream = None
        self.update_timer = None

    @GObject.Property(type=bool, default=False)
    def playing(self):
        return self._playing

    @playing.setter
    def playing(self, _playing):
        self._playing = _playing
        self.notify("playing")

    @GObject.Property(type=bool, default=False)
    def shuffle(self):
        return self._shuffle

    @shuffle.setter
    def shuffle(self, _shuffle):
        if self._shuffle == _shuffle:
            return

        self._shuffle = _shuffle
        self.notify("shuffle")
        self._update_shuffle_queue()
        self.emit("song-changed")

    @GObject.Property(type=int, default=0)
    def repeat_type(self):
        return self._repeat_type

    @repeat_type.setter
    def repeat_type(self, _repeat_type):
        self._repeat_type = _repeat_type
        self.notify("repeat-type")

    def _setup_audio_sink(self, sink_type):
        """Configure the audio sink using parse_launch for simplicity."""
        sink_map = {
            AudioSink.AUTO: 'autoaudiosink',
            AudioSink.PULSE: 'pulsesink',
            AudioSink.ALSA: 'alsasink',
            AudioSink.JACK: 'jackaudiosink',
            AudioSink.OSS: 'osssink'
        }

        sink_name = sink_map.get(sink_type, 'autoaudiosink')

        # add normalization to pipeline if set by settings
        normalization = ""
        if self.normalize:
            # the pre-amp value is set to match tidal webs volume
            normalization =  f"taginject name=rgtags {self.most_recent_rg_tags} ! rgvolume name=rgvol pre-amp=4.0 headroom=6.0 ! rglimiter ! audioconvert !"

        pipeline_str = f"queue max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! audioconvert ! {normalization} audioresample ! {sink_name}"

        try:
            audio_bin = Gst.parse_bin_from_description(pipeline_str, True)
            if not audio_bin:
                raise RuntimeError("Failed to create audio bin")

            self.playbin.set_property('audio-sink', audio_bin)
        except GLib.Error as e:
            print(f"Error creating pipeline: {e}")
            self.playbin.set_property(
                'audio-sink', Gst.ElementFactory.make('autoaudiosink', None))

    def change_audio_sink(self, sink_type):
        """Change the audio sink while maintaining playback state."""
        was_playing = self.playing
        position = self.query_position()
        duration = self.query_duration()

        self.pipeline.set_state(Gst.State.NULL)
        self._setup_audio_sink(sink_type)

        if was_playing and duration != 0:
            self.pipeline.set_state(Gst.State.PLAYING)
            self.seek(position / duration)

    def _on_bus_eos(self, *args):
        """Handle end of stream."""
        GLib.idle_add(self.play_next)

    def _on_bus_error(self, bus, message):
        """Handle pipeline errors."""
        err, debug = message.parse_error()
        print(f"Error: {err.message}")
        print(f"Debug info: {debug}")

    def _on_buffering_message(self, bus, message):
        buffer_per = message.parse_buffering()
        mode, avg_in, avg_out, buff_left = message.parse_buffering_stats()

        self.emit("buffering", buffer_per)

    def play_this(self, thing, index=0):
        """Play tracks from a mix, album, playlist, or artist."""
        self.current_mix_album_playlist = thing
        tracks = self.get_track_list(thing)

        if not tracks:
            print("No tracks found to play")
            return

        self._tracks_to_play = tracks[index:] + tracks[:index]
        if not self._tracks_to_play:
            return

        track = self._tracks_to_play.pop(0)
        self.tracks_to_play = self._tracks_to_play
        self.played_songs = []

        if self.shuffle:
            self._update_shuffle_queue()

        self.play_track(track)
        self.play()
        self.emit("song-changed")

    def shuffle_this(self, thing):
        """Same as play_this, but on shuffle"""
        tracks = self.get_track_list(thing)
        self.play_this(thing, random.randint(0, len(tracks)))
        self.shuffle = True

    def get_track_list(self, thing):
        """Convert various sources into a list of tracks."""
        tracks_list = None

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

        self.id_list = [track.id for track in tracks_list]

        return tracks_list

    def play(self):
        """Start playback."""
        self.playing = True
        self.pipeline.set_state(Gst.State.PLAYING)
        if self.update_timer:
            GLib.source_remove(self.update_timer)
        self.update_timer = GLib.timeout_add(1000, self._update_slider_callback)

        if self.playing_track:
            discord_rpc.set_activity(self.playing_track, self.query_position() / 1_000_000)

    def pause(self):
        """Pause playback."""
        self.playing = False
        self.pipeline.set_state(Gst.State.PAUSED)

        discord_rpc.set_activity()

    def play_pause(self):
        """Toggle between play and pause states."""
        if self.playing:
            self.pause()
        else:
            self.play()

    def play_track(self, track):
        """Play a specific track."""
        threading.Thread(target=self._play_track_thread, args=(track,)).start()

    def _play_track_thread(self, track):
        """Thread for loading and playing a track."""

        self.stream = None
        self.manifest = None

        try:
            self.stream = track.get_stream()
            self.manifest = self.stream.get_stream_manifest()
            urls = self.manifest.get_urls()

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

            GLib.idle_add(self._play_track_url, track, music_url)
        except Exception as e:
            print(f"Error getting track URL: {e}")

    def apply_replaygain_tags(self):
        audio_sink = self.playbin.get_property("audio-sink")

        if audio_sink:
            rgtags = audio_sink.get_by_name("rgtags")

        tags = (
            f"replaygain-album-gain={self.stream.album_replay_gain},"
            f"replaygain-album-peak={self.stream.album_peak_amplitude}"
        )
        if rgtags:
            rgtags.set_property("tags", tags)
            print(f"Applied RG Tags: {tags}")
        # Save replaygain tags for every song to avoid missing tags when
        # toggling the option
        self.most_recent_rg_tags = f"tags={tags}"

    def _play_track_url(self, track, music_url):
        """Set up and play track from URL."""
        self.pipeline.set_state(Gst.State.NULL)
        self.playbin.set_property("uri", music_url)
        self.playbin.set_property("volume", self.playbin.get_property("volume"))
        self.duration = self.query_duration()

        print(music_url)

        self.playing_track = track
        self.song_album = track.album

        if self.playing:
            self.play()

        self.can_next = bool(self._tracks_to_play)
        self.can_prev = bool(self.played_songs)
        self.emit("song-changed")

    def play_next(self):
        """Play the next track."""
        if self._repeat_type == RepeatType.SONG:
            self.seek(0)
            self.apply_replaygain_tags()
            return

        if self.playing_track:
            self.played_songs.append(self.playing_track)

        if self.queue:
            track = self.queue.pop(0)
            self.play_track(track)
            return

        if not self._tracks_to_play and self._repeat_type == RepeatType.LIST:
            self._tracks_to_play = self.played_songs
            self.tracks_to_play = self._tracks_to_play
            self.played_songs = []

        if not self._tracks_to_play:
            self.pause()
            return

        track = (self._shuffled_tracks_to_play if self.shuffle else self._tracks_to_play).pop(0)
        self.play_track(track)

    def play_previous(self):
        """Play the previous track."""
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
        self.queue.append(track)
        self.emit("song-added-to-queue")

    def add_next(self, track):
        self.queue.insert(0, track)
        self.emit("song-added-to-queue")

    def query_volume(self):
        volume = self.playbin.get_property("volume")
        if self.quadratic_volume:
            return volume ** (1/2)
        else:
            return volume

    def change_volume(self, value):
        if self.quadratic_volume:
            self.playbin.set_property("volume", value**2)
        else:
            self.playbin.set_property("volume", value)
        self.emit("volume-changed", value)

    def _update_slider_callback(self):
        """Update playback slider and duration."""
        self.emit("update-slider")
        duration = self.query_duration()
        if duration != self.duration:
            self.duration = duration
            self.emit("duration-changed")
        return self.playing

    def query_duration(self):
        """Get the duration of the current track."""
        success, duration = self.playbin.query_duration(Gst.Format.TIME)
        return duration if success else 0

    def query_position(self, default=0) -> int | None:
        """Get the current playback position."""
        success, position = self.playbin.query_position(Gst.Format.TIME)
        return position if success else default

    def seek(self, seek_fraction):
        """Seek to a position in the current track."""

        position = int(seek_fraction * self.query_duration())
        self.playbin.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            position
        )

        discord_rpc.set_activity(self.playing_track, position / 1_000_000)

    def get_index(self):
        for index, track_id in enumerate(self.id_list):
            if track_id == self.playing_track.id:
                return index
        return 0
