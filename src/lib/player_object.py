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
from tidalapi.playlist import Playlist

from tidalapi.user import Favorites

from gi.repository import GObject
from gi.repository import Gst, GLib

import random
import threading

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
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.queue = []  # List to store queued songs (Not the next songs in an album/playlist/mix, but the ones added with play next/add to queue)

        self.current_mix_album_playlist = None  # Information about the currently playing mix/album

        self.tracks_to_play = [] # List of all the tracks to play in the current album/mix/playlist
        self.shuffled_tracks_to_play = []  # Shuffled version of the next tracks to play

        self.played_songs = [] # List of played songs when not shuffling
        self.shuffled_played_songs = [] # List of played songs when shuffling

        self.shuffle_mode = False
        self.is_playing = False
        self.playing_track = None
        self.song_album = None

        Gst.init()

        self.playbin = Gst.ElementFactory.make("playbin", "playbin")

        # GLib.timeout_add(4000, self.print_queue_and_list)
        GLib.timeout_add(1000, self.check_for_end_of_stream)

    def play_this(self, thing, index = 0): # Used to play albums, playlists, mixes
        self.current_mix_album_playlist = thing
        tracks = self.get_track_list(thing)
        self.tracks_to_play = tracks[index:] + tracks[:index]
        track = self.tracks_to_play[0]
        self.tracks_to_play.pop(0)
        self.play_track(track)
        self.play()

    def shuffle_this(self, thing): # Same as play_this, but on shuffle
        self.shuffle_mode = True

        self.current_mix_album_playlist = thing
        self.tracks_to_play = self.get_track_list(thing)
        self.shuffled_tracks_to_play = self.tracks_to_play.copy()
        random.shuffle(self.shuffled_tracks_to_play)
        track = self.shuffled_tracks_to_play[0]
        self.shuffled_tracks_to_play.pop(0)
        self.play_track(track)
        self.play()

    def get_track_list(self, thing): # Converts albums, playlists, mixes in a list of tracks
        if isinstance(thing, Mix):
            tracks = thing.items()
        elif isinstance(thing, Album):
            tracks = thing.tracks()
        elif isinstance(thing, Playlist):
            tracks = thing.tracks()
        else: # For radios
            tracks = thing

        return tracks

    def play(self):
        self.is_playing = True
        self.notify("is_playing")

        self.emit("play-changed", self.is_playing)
        self.playbin.set_state(Gst.State.PLAYING)

        GLib.timeout_add(1000, self.update_slider_call)

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
        print(f"play track: {track.name} by {track.artist.name}, {track.media_metadata_tags}, {track.audio_quality}, {track.id}")
        music_url = track.get_url()
        self.playbin.set_state(Gst.State.NULL)

        self.playbin.set_property("uri", music_url)

        if self.is_playing:
            self.play()

        self.playing_track = track
        self.song_album = track.album
        self.emit("song-changed")

    def play_next(self):
        """Play the next song in the queue or from the currently playing album/mix/playlist."""

        # FIXME when not on shuffle it works, on shuffle it doesn't, but I thing the shuffle is not registered

        # Appends the track that just finished playing or was skipped to the played_songs list
        self.played_songs.append(self.playing_track)

        print(f"Shuffle mode is {self.shuffle_mode}")

        # If the queue is not empty it plays the first song in the queue
        if len(self.queue) != 0:
            track = self.queue[0]
            self.queue.pop(0)
            self.play_track(track)
            return

        # If the tracks_to_play list is empty it refills it with the played songs and empties the played_songs
        if self.tracks_to_play == []:
            self.tracks_to_play = self.played_songs
            self.played_songs = []

        # If it's shuffling it plays the first song in the shuffled_tracks_to_play. If it's not on shuffle it will play the first song from tracks_to_play
        if self.shuffle_mode:
            track = self.shuffled_tracks_to_play[0]
            self.shuffled_tracks_to_play.pop(0)
            self.tracks_to_play.remove(self.playing_track)
            self.play_track(track)
            return
        else:
            track = self.tracks_to_play[0]
            self.play_track(track)
            self.tracks_to_play.pop(0)
            return

    def play_previous(self):
        """Play the previous song in the queue."""
        last_index = len(self.played_songs) - 1
        track = self.played_songs[last_index]
        self.played_songs.pop(last_index)
        self.tracks_to_play.insert(0, self.playing_track)
        self.play_track(track)

    def check_for_end_of_stream(self):
        # FIXME Gstreamer position/duration don't update instantly after changing song (it still returns the previous values)
        success1, duration = self.query_duration(Gst.Format.TIME)
        success2, position = self.query_position(Gst.Format.TIME)

        # print(f"{position} and {duration}")

        if success1 and success2:
            if position >= duration - 1:
                print("song ended")
                self.play_next()
                # return False

        return True

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
        for track in self.tracks_to_play:
            print(track.name)

        return True

    def add_to_queue(self, track):
        self.queue.append(track)
        self.emit("song-added-to-queue")

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
        return self.current_mix_album_playlist.items()[self.current_song_index]

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
        if self.is_playing:
            return True
        return False

    def query_duration(self, time_format):
        return self.playbin.query_duration(Gst.Format.TIME)

    def query_position(self, time_format):
        return self.playbin.query_position(Gst.Format.TIME)

    def seek(self, time_format, something, seek_time):
        self.playbin.seek_simple(time_format, something, seek_time)
