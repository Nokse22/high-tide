# window.py
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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GObject
# from gi.repository import Secret

from gi.repository import Gst, GLib

import base64
import json

import tidalapi
from tidalapi.page import PageItem, PageLink
from tidalapi.mix import Mix, MixType
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track, Quality
from tidalapi.playlist import Playlist

from .lib import playerObject
from .lib import utils

import os
import sys

from .login import LoginWindow
from .new_playlist import NewPlaylistWindow

from .pages import homePage, singleTypePage, explorePage, artistPage, notLoggedInPage
from .pages import searchPage, trackRadioPage, playlistPage, startUpPage

import threading
import requests
import random

from .lib import SecretStore

from .widgets.generic_track_widget import GenericTrackWidget

@Gtk.Template(resource_path='/io/github/nokse22/high-tide/window.ui')
class TidalWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'TidalWindow'

    # homepage_box = Gtk.Template.Child()
    split_view = Gtk.Template.Child()
    progress_bar = Gtk.Template.Child()
    sidebar_list = Gtk.Template.Child()
    duration_label = Gtk.Template.Child()
    time_played_label = Gtk.Template.Child()
    shuffle_button = Gtk.Template.Child()
    navigation_view = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    small_progress_bar = Gtk.Template.Child()
    song_title_label = Gtk.Template.Child()
    artist_button = Gtk.Template.Child()
    playing_track_image = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    sidebar_collection = Gtk.Template.Child()
    right_sidebar_split_view = Gtk.Template.Child()
    lyrics_box = Gtk.Template.Child()
    sidebar_playlists = Gtk.Template.Child()
    volume_button = Gtk.Template.Child()
    in_my_collection_button = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()
    queue_list = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings = Gio.Settings.new('io.github.nokse22.high-tide')

        self.settings.bind("window-width", self, "default-width", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("window-height", self, "default-height", Gio.SettingsBindFlags.DEFAULT)

        self.player_object = playerObject()

        self.volume_button.get_adjustment().set_value(self.settings.get_int("last-volume")/10)

        # self.shuffle_button.connect("toggled", self.on_shuffle_button_toggled)

        self.player_object.bind_property("shuffle_mode", self.shuffle_button, "active", GObject.BindingFlags.DEFAULT)
        self.player_object.connect("update-slider", self.update_slider)
        self.player_object.connect("song-changed", self.on_song_changed)
        self.player_object.connect("song-added-to-queue", self.update_queue)
        self.player_object.connect("play-changed", self.update_controls)
        self.artist_button.connect("clicked", self.on_toolbar_artist_button_clicked)

        self.search_entry.connect("activate", self.on_search_activated)

        self.session = tidalapi.Session()

        self.user = self.session.user

        self.select_quality(self.settings.get_int("quality"))

        self.current_mix = None
        self.player_object.current_song_index = 0
        self.previous_time = 0
        self.favourite_playlists = []
        self.favourite_tracks = []

        self.secret_store = SecretStore(self.session)

        # TO REMOVE UNSECURED TOKENS set in early development
        self.settings.set_string("token-type", "")
        self.settings.set_string("access-token", "")
        self.settings.set_string("refresh-token", "")
        self.settings.set_string("expiry-time", "")

        page = startUpPage(self, None, "Loading")
        page.load()
        self.navigation_view.push(page)

        th = threading.Thread(target=self.login, args=())
        th.deamon = True
        th.start()

    def on_logged_in(self):
        print("on logged in")
        # self.favourite_tracks = self.session.user.favorites.tracks()
        # FIXME if it doesn't login fast enough it doesn't let the user login

        self.search_entry.set_sensitive(True)

        page = homePage(self)
        page.load()
        self.navigation_view.replace([page])

        th = threading.Thread(target=self._set_last_playing_song, args=())
        th.deamon = True
        th.start()

        self.add_favourite_playlists()

    def on_login_failed(self):
        print("login failed")

        page = notLoggedInPage(self)
        page.load()
        self.navigation_view.replace([page])

    def add_favourite_playlists(self):
        playlists = self.session.user.favorites.playlists()

        child = self.sidebar_playlists.get_first_child()
        while child != None:
            self.sidebar_playlists.remove(child)
            child = self.sidebar_playlists.get_first_child()

        for index, playlist in enumerate(playlists):
            label = Gtk.Label(xalign=0, label=playlist.name, name=index)
            self.sidebar_playlists.append(label)

        self.favourite_playlists = playlists

    def _set_last_playing_song(self):
        track_id = self.settings.get_int("last-playing-song-id")
        list_id = self.settings.get_string("last-playing-list-id")

        if track_id == '':
            return

        track = self.session.track(track_id)
        self.player_object.play_track(track)

        # TODO Set last playing playlist/mix/album as current playing thing

        # self.player_object. = self.session.track(track_id)

    def on_song_changed(self, *args):
        print("song changed")
        album = self.player_object.song_album
        track = self.player_object.playing_track
        self.song_title_label.set_label(track.name)
        self.artist_label.set_label(track.artist.name)
        self.in_my_collection_button.set_icon_name("heart-outline-thick-symbolic")
        self.explicit_label.set_visible(track.explicit)

        self.settings.set_int("last-playing-song-id", track.id)

        album_image_link = album.image()
        if album_image_link:
            th = threading.Thread(target=self.add_image, args=(self.playing_track_image, album_image_link))
            th.deamon = True
            th.start()

        if self.player_object.is_playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

        if self.right_sidebar_split_view.get_show_sidebar():
            th = threading.Thread(target=self.add_lyrics_to_page, args=())
            th.deamon = True
            th.start()

        self.control_bar_artist = track.artist
        self.update_slider()
        self.update_queue()

    def update_queue(self, *args):
        """Creates and populates the right sidebar queue view, if there is nothing in played_songs, queue or songs_to_play lists in player_object
        it doesn't add that section"""

        box = Gtk.Box(orientation=1)
        played_songs_list_box = Gtk.ListBox(css_classes=["boxed-list"], margin_top=6,
                margin_bottom=6, margin_start=6, margin_end=6)
        queue_list_box = Gtk.ListBox(css_classes=["boxed-list"], margin_top=6,
                margin_bottom=6, margin_start=6, margin_end=6)
        songs_to_play_list_box = Gtk.ListBox(css_classes=["boxed-list"], margin_top=6,
                margin_bottom=6, margin_start=6, margin_end=6)

        for index, track in enumerate(self.player_object.played_songs):
            listing = GenericTrackWidget(track, self, False)
            listing.set_name(str(index))
            played_songs_list_box.append(listing)

        for index, track in enumerate(self.player_object.queue):
            listing = GenericTrackWidget(track, self, False)
            listing.set_name(str(index))
            queue_list_box.append(listing)

        for index, track in enumerate(self.player_object.tracks_to_play):
            listing = GenericTrackWidget(track, self, False)
            listing.set_name(str(index))
            songs_to_play_list_box.append(listing)

        box.append(Gtk.Label(label="Played songs"))
        box.append(played_songs_list_box)
        box.append(Gtk.Label(label="Queue"))
        box.append(queue_list_box)
        box.append(Gtk.Label(label="Songs to play"))
        box.append(songs_to_play_list_box)

        self.queue_list.set_child(box)

    def on_toolbar_artist_button_clicked(self, btn):
        self.sidebar_list.select_row(None)
        artist = self.player_object.playing_track.artist
        page = artistPage(self, artist, artist.name)
        page.load()
        self.navigation_view.push(page)
        print("clicked on artist")

    def on_search_activated(self, *args):
        page = searchPage(self, None, "Search")
        page.load()
        self.navigation_view.push(page)

    def update_controls(self, is_playing, *arg):
        if not is_playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            print("pause")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")
            print("play")

    def new_login(self):
        """Opens a LoginWindow"""

        login_window = LoginWindow(self, self.session)
        login_window.set_transient_for(self)
        login_window.set_modal(self)
        login_window.present()

    def login(self):
        """Logs the user in, if it doesn't work it calls on_login_failed()"""
        try:
            result = self.session.load_oauth_session(
                self.secret_store.token_dictionary["token-type"],
                self.secret_store.token_dictionary["access-token"],
                self.secret_store.token_dictionary["refresh-token"],
                self.secret_store.token_dictionary["expiry-time"])
        except Exception as e:
            print(f"error! {e}")
            GLib.idle_add(self.on_login_failed)
        else:
            self.on_logged_in()

    def logout(self):
        self.secret_store.clear()

        self.search_entry.set_sensitive(False)

        page = notLoggedInPage(self)
        page.load()
        self.navigation_view.replace([page])

    def explore_page(self):
        explore = session.explore()

    def add_image(self, image_widget, image_url):
        try:
            response = requests.get(image_url)
        except:
            return
        if response.status_code == 200:
            image_data = response.content
            file_path = f"tmp_img/{random.randint(0, 100)}.jpg"
            with open(file_path, "wb") as file:
                file.write(image_data)

            GLib.idle_add(self._add_image, image_widget, file_path)

    def _add_image(self, image_widget, file_path):
        image_widget.set_from_file(file_path)

    @Gtk.Template.Callback("on_play_button_clicked")
    def on_play_button_clicked(self, btn):
        if not self.player_object.is_playing:
            self.player_object.play()
            btn.set_icon_name("media-playback-pause-symbolic")
            print("pause")
        else:
            self.player_object.pause()
            btn.set_icon_name("media-playback-start-symbolic")
            print("play")

    def update_slider(self, *args):
        """Called on a timer, it updates the progress bar and
            adds the song duration and position."""
        if not self.player_object.is_playing:
            return False # cancel timeout
        else:
            success, self.duration = self.player_object.query_duration(Gst.Format.TIME)
            if not success:
                end_value = 100
                pass
            else:
                end_value = self.duration / Gst.SECOND
                self.progress_bar.set_range(0, end_value)

                self.duration_label.set_label(utils.pretty_duration(end_value))

            success, position = self.player_object.query_position(Gst.Format.TIME)
            if not success:
                pass
            else:
                position = position / Gst.SECOND
                self.progress_bar.get_adjustment().set_value(position)
                self.small_progress_bar.set_fraction(position/end_value)
                self.previous_time = position

                self.time_played_label.set_label(utils.pretty_duration(position))
        return True

    @Gtk.Template.Callback("on_lyrics_button_clicked")
    def on_lyrics_button_clicked_func(self, widget):
        # self.right_sidebar_split_view.set_collapsed(False)
        self.right_sidebar_split_view.set_show_sidebar(not self.right_sidebar_split_view.get_show_sidebar())

        th = threading.Thread(target=self.add_lyrics_to_page, args=())
        th.deamon = True
        th.start()

    def add_lyrics_to_page(self):
        lyrics = self.player_object.playing_track.lyrics()
        label = Gtk.Label(label=lyrics.text, wrap=True, justify=2, opacity=0.6,
                margin_start=12, margin_end=12, css_classes=["lyrics"])
        self.lyrics_box.set_child(label)

    def download_song(self):
        """Added to check the streamed song quality, triggered with ctrl+d"""

        song = self.player_object.playing_track
        song_url = song.get_url()
        try:
            response = requests.get(song_url)
        except:
            return
        if response.status_code == 200:
            image_data = response.content
            file_path = f"{song.id}.flac"
            with open(file_path, "wb") as file:
                file.write(image_data)

    def select_quality(self, pos):
        match pos:
            case 0:
                self.session.audio_quality = Quality.low_96k
            case 1:
                self.session.audio_quality = Quality.low_320k
            case 2:
                self.session.audio_quality = Quality.high_lossless
            case 3:
                self.session.audio_quality = Quality.hi_res
            case 4:
                self.session.audio_quality = Quality.hi_res_lossless

        self.settings.set_int("quality", pos)

    @Gtk.Template.Callback("on_in_my_collection_button_clicked")
    def on_in_my_collection_button_clicked(self, btn):
        if self.in_my_collection_button.get_icon_name() == "heart-outline-thick-symbolic":
            th = threading.Thread(target=self.add_track_to_my_collection, args=(self.player_object.playing_track.id,))
            self.in_my_collection_button.set_icon_name("heart-filled-symbolic")
        else:
            th = threading.Thread(target=self.remove_track_from_my_collection, args=(self.player_object.playing_track.id,))
            self.in_my_collection_button.set_icon_name("heart-outline-thick-symbolic")
        th.deamon = True
        th.start()

    def add_track_to_my_collection(self, track_id):
        result = self.session.user.favorites.add_track(track_id)
        if result:
            print("successfully added to my collection")

    def remove_track_from_my_collection(self, track_id):
        result = self.session.user.favorites.remove_track(track_id)
        if result:
            print("successfully removed from my collection")

    @Gtk.Template.Callback("on_volume_changed")
    def on_volume_changed_func(self, widget, value):
        print(f"volume changed to {value}")
        self.player_object.change_volume(value)
        self.settings.set_int("last-volume", int(value*10))

    @Gtk.Template.Callback("on_new_playlist_button_clicked")
    def on_new_playlist_button_clicked_func(self, btn):
        new_playlist_win = NewPlaylistWindow(self, self.session)
        new_playlist_win.set_transient_for(self)
        new_playlist_win.set_modal(self)
        new_playlist_win.present()

    @Gtk.Template.Callback("on_track_radio_button_clicked")
    def on_track_radio_button_clicked_func(self, widget):
        track = self.player_object.playing_track
        page = trackRadioPage(self, track, f"{track.name} Radio")
        page.load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_slider_seek")
    def on_slider_seek(self, *args):
        seek_time_secs = self.progress_bar.get_value()
        if abs(seek_time_secs - self.previous_time) > 6:
            print("seeking")
            print(abs(seek_time_secs - self.previous_time))
            self.player_object.seek(Gst.Format.TIME,  Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, seek_time_secs * Gst.SECOND)
            self.previous_time = seek_time_secs

    @Gtk.Template.Callback("on_skip_forward_button_clicked")
    def on_skip_forward_button_clicked_func(self, widget):
        print("skip forward")
        self.player_object.play_next()

    @Gtk.Template.Callback("on_skip_backward_button_clicked")
    def on_skip_backward_button_clicked_func(self, widget):
        print("skip backward")
        self.player_object.play_previous()

    @Gtk.Template.Callback("on_playlists_sidebar_row_activated")
    def on_playlists_sidebar_row_activated_func(self, list_box, row):
        """Handles the click on an user playlist on the sidebar"""

        if row == None:
            return
        index = row.get_child().get_name()

        playlist = self.favourite_playlists[int(index)]

        page = playlistPage(self, playlist, playlist.name)
        page.load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_sidebar_row_selected_clicked")
    def on_sidebar_row_selected_clicked_func(self, list_box, row):
        if row == None:
            return
        if row.get_child().get_name() == "HOME":
            self.navigation_view.pop_to_tag("home")
        elif row.get_child().get_name() == "EXPLORE":
            page = explorePage(self, None, "Explore")
            page.load()
            self.navigation_view.push(page)
        elif row.get_child().get_name() == "F-TRACK":
            page = singleTypePage(self, "track", "Favourite Tracks")
            page.load()
            self.navigation_view.push(page)
        elif row.get_child().get_name() == "F-MIX":
            page = singleTypePage(self, "mix", "Favourite Mixes")
            page.load()
            self.navigation_view.push(page)
        elif row.get_child().get_name() == "F-ARTIST":
            page = singleTypePage(self, "artist", "Favourite Artists")
            page.load()
            self.navigation_view.push(page)
        elif row.get_child().get_name() == "F-PLAYLIST":
            page = singleTypePage(self, "playlist", "Favourite Playlists")
            page.load()
            self.navigation_view.push(page)
        elif row.get_child().get_name() == "F-ALBUM":
            page = singleTypePage(self, "album", "Favourite Albums")
            page.load()
            self.navigation_view.push(page)

    @Gtk.Template.Callback("show_sidebar")
    def func(self, btn):
        self.split_view.set_show_sidebar(True)
