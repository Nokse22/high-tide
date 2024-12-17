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

from tidalapi.mix import Mix
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.playlist import Playlist

from gi.repository import GObject
from gi.repository import Gst, GLib

from enum import IntEnum


class RepeatType(IntEnum):
    NONE = 0
    SONG = 1
    LIST = 2


class playerObject(GObject.GObject):
    """This class handles all the player logic, queue, shuffle..."""

    shuffle_mode = GObject.Property(type=bool, default=False)
    current_song_index = GObject.Property(type=int, default=-1)
    is_playing = GObject.Property(type=bool, default=False)

    __gsignals__ = {
        'songs-list-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'update-slider': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'song-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'song-added-to-queue': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'play-changed': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        'duration-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'shuffle-changed': (GObject.SignalFlags.RUN_FIRST, None, (bool,))
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        # TODO Rename all player_object to something like GstPlayer

        Gst.init()

        self._player = Gst.ElementFactory.make('playbin3', 'player')
        self._bus = self._player.get_bus()
        self._bus.add_signal_watch()

        # List to store queued songs (Not the next songs in an
        #   album/playlist/mix, but the ones added with play next/add to queue)
        self.queue = []

        # Information about the currently playing mix/album
        self.current_mix_album_playlist = None

        # The tracks to play in the correct order
        self._tracks_to_play = []
        # List of all the tracks to play in the current album/mix/playlist
        self.tracks_to_play = []
        # Shuffled version of the next tracks to play
        self._shuffled_tracks_to_play = []

        # List of played songs when not shuffling
        self.played_songs = []

        self.shuffle_mode = False
        self.is_playing = False
        self.playing_track = None
        self.song_album = None

        self.repeat = RepeatType.NONE

        self.duration = self.query_duration()

        self.can_next = False
        self.can_prev = False

        self._bus.connect('message::eos', self._on_bus_eos)

        # ---------------------------- FROM GNOME-MUSIC ----------------------------
        #
        #
        # self._bus = self._player.get_bus()
        # self._bus.add_signal_watch()
        # self._setup_replaygain()

        # self._settings.connect(
        #     'changed::replaygain', self._on_replaygain_setting_changed)
        # self._on_replaygain_setting_changed(
        #     None, self._settings.get_value('replaygain'))

        # self._bus.connect('message::async-done', self._on_async_done)
        # self._bus.connect('message::error', self._on_bus_error)
        # self._bus.connect('message::element', self._on_bus_element)
        # self._bus.connect('message::eos', self._on_bus_eos)
        # self._bus.connect('message::new-clock', self._on_new_clock)
        # self._bus.connect("message::state-changed", self._on_state_changed)
        # self._bus.connect("message::stream-start", self._on_bus_stream_start)

        # self._player.connect("about-to-finish", self._on_about_to_finish)

    def _on_bus_eos(self, *args):
        self.play_next()

    def play_this(self, thing, index=0):
        """Used to play albums, playlists, mixes"""
        self.current_mix_album_playlist = thing
        tracks = self.get_track_list(thing)
        self._tracks_to_play = tracks[index:] + tracks[:index]
        track = self._tracks_to_play[0]
        self._tracks_to_play.pop(0)

        self.tracks_to_play = self._tracks_to_play
        self.emit("song-changed")

        self.played_songs = []
        self.play_track(track)
        self.play()

    def shuffle_this(self, thing):
        """Same as play_this, but on shuffle"""
        tracks = self.get_track_list(thing)
        self.play_this(tracks, random.randint(0, len(tracks)))
        self.shuffle(True)

    def get_track_list(self, thing):
        """Converts albums, playlists, mixes in a list of tracks"""
        if isinstance(thing, Mix):
            tracks = thing.items()
        elif isinstance(thing, Album):
            tracks = thing.tracks()
        elif isinstance(thing, Playlist):
            tracks = thing.tracks()
        elif isinstance(thing, Artist):
            tracks = thing.top_tracks()
        elif isinstance(thing, list):
            tracks = thing

        return tracks

    def play(self):
        self.is_playing = True
        self.notify("is_playing")

        self.emit("play-changed", self.is_playing)
        self._player.set_state(Gst.State.PLAYING)

        GLib.timeout_add(1000, self.update_slider_call)

    def pause(self):
        self.is_playing = False
        self.notify("is_playing")

        self.emit("play-changed", self.is_playing)
        self._player.set_state(Gst.State.PAUSED)

    def play_pause(self):
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def play_track(self, track):
        th = threading.Thread(target=self.th_play_track, args=(track,))
        th.deamon = True
        th.start()

    def th_play_track(self, track):
        print(f"""play track: {track.name} by {track.artist.name}""" +
              f"""{track.media_metadata_tags}, {track.audio_quality}""")

        music_url = track.get_url()
        self._player.set_state(Gst.State.NULL)

        self._player.set_property("uri", music_url)

        self.duration = self.query_duration()

        if self.is_playing:
            self.play()

        self.playing_track = track
        self.song_album = track.album

        if len(self._tracks_to_play) > 0:
            self.can_next = True
        else:
            self.can_next = False

        if len(self.played_songs) > 0:
            self.can_prev = True
        else:
            self.can_prev = False

        self.emit("song-changed")

    def play_next(self):
        """Play the next song in the queue or from the currently
        playing album/mix/playlist."""

        print(f"Shuffle mode is {self.shuffle_mode}")

        print(f"The queue is {len(self.queue)} long and the tracks to play are {len(self._tracks_to_play)}")

        if self.repeat == RepeatType.SONG:
            self.seek(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                0)
            return

        # Appends the track that just finished playing or was skipped to the
        #   played_songs list
        self.played_songs.append(self.playing_track)

        # If the queue is not empty it plays the first song in the queue
        if len(self.queue) != 0:
            track = self.queue[0]
            self.queue.pop(0)
            self.play_track(track)
            return

        # If the tracks_to_play list is empty it refills it with the
        #   played songs and empties the played_songs
        if self._tracks_to_play == []:
            if self.repeat == RepeatType.LIST:
                self._tracks_to_play = self.played_songs
                self.tracks_to_play = self._tracks_to_play
                self.played_songs = []
            elif self.repeat == RepeatType.NONE:
                self.pause()
                return

        # If it's shuffling it plays the first song in the
        #   shuffled_tracks_to_play. If it's not on shuffle it will play
        #   the first song from tracks_to_play
        if self.shuffle_mode:
            track = self._shuffled_tracks_to_play[0]
            self.play_track(track)
            self._shuffled_tracks_to_play.pop(0)
            return
        else:
            track = self._tracks_to_play[0]
            self.play_track(track)
            self._tracks_to_play.pop(0)
            return

    def play_previous(self):
        """Play the previous song in the queue."""
        last_index = len(self.played_songs) - 1
        track = self.played_songs[last_index]
        self.played_songs.pop(last_index)
        self._tracks_to_play.insert(0, self.playing_track)
        self.play_track(track)

    def print_queue_and_list(self):
        return
        print("----------played songs----------")
        for track in self.played_songs:
            print(track.name)
        print(f"PLAYING: {self.playing_track.name}")
        print("-------------queue--------------")
        for track in self.queue:
            print(track.name)
        print("---------songs to play----------")
        for track in self._tracks_to_play:
            print(track.name)

        return True

    def add_to_queue(self, track):
        self.queue.append(track)
        self.emit("song-added-to-queue")

    def add_next(self, track):
        self.queue.insert(0, track)
        self.emit("song-added-to-queue")

    def change_volume(self, value):
        self._player.set_property("volume", value)

    def shuffle(self, state):
        """Enable or disable shuffle mode."""
        print(f"shuffle toggled to {state}")
        self.shuffle_mode = state

        self.emit("shuffle-changed", self.shuffle_mode)

        if state:
            self._shuffled_tracks_to_play = self._tracks_to_play.copy()
            random.shuffle(self._shuffled_tracks_to_play)
            self.tracks_to_play = self._shuffled_tracks_to_play
        else:
            self.tracks_to_play = self._tracks_to_play

        self.emit("song-changed")

        # self.emit("songs-list-changed", self.shuffle_mode)

    def get_current_song(self):
        """Get the currently playing song."""
        return self.playing_track

    def get_prev_track(self):
        if len(self.played_songs) != 0:
            return self.played_songs[-1]
        return None

    def get_next_track(self):
        if len(self.queue) != 0:
            return self.queue[0]
        if len(self._tracks_to_play) != 0:
            return self._tracks_to_play[0]
        return None

    def clear_queue(self):
        """Clear the queue."""
        self.queue = []
        self.shuffled_queue = []
        self.current_song_index = -1

    def set_current_mix_album_playlist(self, mix_album):
        """Set information about the currently playing mix/album."""
        self.current_mix_album_playlist = mix_album

    def update_slider_call(self):
        self.emit("update-slider")

        duration = self.query_duration()
        if duration != self.duration:
            self.emit("duration-changed")

        if self.is_playing:
            return True
        return False

    def query_duration(self):
        success, duration = self._player.query_duration(Gst.Format.TIME)
        if success:
            print(duration)
            return duration
        else:
            return 0

    def query_position(self):
        success, position = self._player.query_position(Gst.Format.TIME)
        if success:
            return position
        else:
            return 0

    def seek(self, time_format, something, seek_time):
        self._player.seek_simple(time_format, something, seek_time)
