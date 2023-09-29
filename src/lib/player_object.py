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

from tidalapi.mix import Mix
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track

from gi.repository import GObject
from gi.repository import Gst, GLib

import random
import threading

class playerObject(GObject.GObject):
    """This class handles all the player logic, queue..."""

    shuffle_mode = GObject.Property(type=bool, default=False)
    current_song_index = GObject.Property(type=int, default=-1)
    is_playing = GObject.Property(type=bool, default=False)

    __gsignals__ = {
        'songs-list-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'update-slider': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'song-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'play-changed': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.queue = []  # List to store queued songs
        self.current_mix_album = None  # Information about the currently playing mix/album
        self.tracks_from_list_to_play = []
        self.shuffled_queue = []  # Shuffled version of the queue
        self.shuffle_mode = False
        self.is_playing = False
        self.playing_track = None
        self.song_album = None
        self.played_songs = []

        Gst.init()

        self.playbin = Gst.ElementFactory.make("playbin", "playbin")

        GLib.timeout_add(3000, self.print_queue_and_list)

    def play(self):
        self.is_playing = True
        self.notify("is_playing")

        self.emit("play-changed", self.is_playing)
        self.playbin.set_state(Gst.State.PLAYING)

        GLib.timeout_add(1000, self.update_slider_call)

    def play_shuffle(self):
        self.shuffle_mode = True
        self.shuffled_queue = self.tracks_from_list_to_play.copy()

        random.shuffle(self.shuffled_queue)

        self.play_track(self.shuffled_queue[0])
        self.play()

    def pause(self):
        self.is_playing = False
        self.notify("is_playing")

        self.emit("play-changed", self.is_playing)
        self.playbin.set_state(Gst.State.PAUSED)

    def play_track(self, track):
        th = threading.Thread(target=self._play_track, args=(track,))
        th.deamon = True
        th.start()

    def _play_track(self, track):
        print(f"play track: {track.name} by {track.artist.name}\n{track.media_metadata_tags}\n{track.audio_quality}\n{track.id}")
        music_url = track.get_url()
        self.playbin.set_state(Gst.State.NULL)

        self.playbin.set_property("uri", music_url)

        if self.is_playing:
            self.play()

        self.playing_track = track
        self.song_album = track.album
        self.emit("song-changed")

        GLib.timeout_add(1000, self.update_slider_call)

    def play_next(self):
        """Play the next song in the queue or from the currently playing album/mix/playlist."""

        if self.playing_track in self.tracks_from_list_to_play:
            self.played_songs.append(self.playing_track)

        if len(self.queue) != 0:
            track = self.queue[0]
            self.queue.pop(0)
        else:
            if self.shuffle_mode:
                # track = self.shuffled_queue[0]
                pass
            else:
                self.tracks_from_list_to_play.remove(self.playing_track)
                if self.tracks_from_list_to_play == []:
                    self.tracks_from_list_to_play = self.played_songs
                    self.played_songs = []
                track = self.tracks_from_list_to_play[0]
        self.play_track(track)

    def play_previous(self):
        """Play the previous song in the queue."""
        # if self.shuffle_mode:
        #     self.current_song_index = random.randint(0, len(self.current_mix_album.items()))
        # else:
        self.current_song_index += 1
        track = self.played_songs[len(self.played_songs) - 1]
        # self.played_songs.remove(self.playing_track)
        self.tracks_from_list_to_play.append(self.playing_track)
        self.play_track(track)

    def print_queue_and_list(self):
        return
        print("----------played songs----------")
        for track in self.played_songs:
            print(track.name)
        print("-------------queue--------------")
        for track in self.queue:
            print(track.name)
        print("---------songs to play----------")
        for track in self.tracks_from_list_to_play:
            print(track.name)

        return True

    def add_to_queue(self, track):
        self.queue.append(track)

    def add_next(self, track):
        self.queue.insert(0, track)

    def change_volume(self, value):
        self.playbin.set_property("volume", value)

    def shuffle(self, state):
        """Enable or disable shuffle mode."""
        print(f"shuffle toggled to {state}")
        self.shuffle_mode = state

        self.notify("shuffle_mode")

        # self.emit("songs-list-changed", self.shuffle_mode)

    def get_current_song(self):
        """Get information about the currently playing song."""
        return self.current_mix_album.items()[self.current_song_index]

    def clear_queue(self):
        """Clear the queue."""
        self.queue = []
        self.shuffled_queue = []
        self.current_song_index = -1

    def set_current_mix_album(self, mix_album):
        """Set information about the currently playing mix/album."""
        self.current_mix_album = mix_album

    def update_slider_call(self):
        self.emit("update-slider")
        if self.is_playing:
            return True
        return False

    def query_duration(self, time_format):
        return self.playbin.query_duration(Gst.Format.TIME)

    def query_position(self, time_format):
        return self.playbin.query_position(Gst.Format.TIME)

    def seek(self, time_format, something, seek_time):
        self.playbin.seek_simple(time_format, something, seek_time)
