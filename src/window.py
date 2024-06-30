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

from .mpris import MPRIS

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

from .login import LoginDialog
from .new_playlist import NewPlaylistWindow

from .pages import homePage, explorePage, artistPage, notLoggedInPage
from .pages import searchPage, trackRadioPage, playlistPage, startUpPage, fromFunctionPage

import threading
import requests
import random

from .lib import SecretStore
from .lib import variables

from .widgets import GenericTrackWidget
from .widgets import LinkLabelWidget
from .widgets import QueueWidget

@Gtk.Template(resource_path='/io/github/nokse22/HighTide/ui/window.ui')
class HighTideWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'HighTideWindow'

    # homepage_box = Gtk.Template.Child()
    split_view = Gtk.Template.Child()
    progress_bar = Gtk.Template.Child()
    sidebar_list = Gtk.Template.Child()
    duration_label = Gtk.Template.Child()
    time_played_label = Gtk.Template.Child()
    shuffle_button = Gtk.Template.Child()
    navigation_view = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    # search_entry = Gtk.Template.Child()
    small_progress_bar = Gtk.Template.Child()
    song_title_label = Gtk.Template.Child()
    playing_track_image = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    mobile_artist_label = Gtk.Template.Child()
    sidebar_collection = Gtk.Template.Child()
    sidebar_playlists = Gtk.Template.Child()
    volume_button = Gtk.Template.Child()
    in_my_collection_button = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()
    main_view_stack = Gtk.Template.Child()
    playbar_main_box = Gtk.Template.Child()
    # navigation_carousel = Gtk.Template.Child()
    # previous_carousel_picture = Gtk.Template.Child()
    current_carousel_picture = Gtk.Template.Child()
    # next_carousel_picture = Gtk.Template.Child()
    queue_widget = Gtk.Template.Child()
    mobile_stack = Gtk.Template.Child()
    lyrics_label = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings = Gio.Settings.new('io.github.nokse22.HighTide')

        self.settings.bind("window-width", self, "default-width", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("window-height", self, "default-height", Gio.SettingsBindFlags.DEFAULT)

        self.player_object = playerObject()
        variables.player_object = self.player_object
        # variables.search_entry = self.search_entry

        self.volume_button.get_adjustment().set_value(self.settings.get_int("last-volume")/10)

        # self.shuffle_button.connect("toggled", self.on_shuffle_button_toggled)

        self.player_object.bind_property("shuffle_mode", self.shuffle_button, "active", GObject.BindingFlags.DEFAULT)
        self.player_object.connect("update-slider", self.update_slider)
        self.player_object.connect("song-changed", self.on_song_changed)
        self.player_object.connect("song-changed",self.queue_widget.update_all)
        self.player_object.connect("song-added-to-queue", self.queue_widget.update_queue)
        self.player_object.connect("play-changed", self.update_controls)

        self.artist_label.connect("activate-link", variables.open_uri)
        self.mobile_artist_label.connect("activate-link", variables.open_uri)
        self.mobile_artist_label.connect("activate-link", self.toggle_mobile_view)

        self.session = tidalapi.Session()

        variables.session = self.session
        variables.navigation_view = self.navigation_view
        variables.stack = self.main_view_stack

        self.user = self.session.user

        self.select_quality(self.settings.get_int("quality"))

        self.current_mix = None
        self.player_object.current_song_index = 0
        self.previous_time = 0
        self.favourite_playlists = []
        self.my_playlists = []

        self.queue_widget_updated = False

        self.secret_store = SecretStore(self.session)

        # TO REMOVE UNSECURED TOKENS set in early development
        self.settings.set_string("token-type", "")
        self.settings.set_string("access-token", "")
        self.settings.set_string("refresh-token", "")
        self.settings.set_string("expiry-time", "")

        page = startUpPage(None, "Loading")
        page.load()
        self.navigation_view.push(page)

        th = threading.Thread(target=self.login, args=())
        th.deamon = True
        th.start()

        MPRIS(self.player_object)

    def on_logged_in(self):
        print("on logged in")
        variables.get_favourites()
        # FIXME if it doesn't login fast enough it doesn't let the user login

        self.sidebar_list.set_sensitive(True)

        page = homePage(self)
        page.load()
        self.navigation_view.replace([page])

        th = threading.Thread(target=self._set_last_playing_song, args=())
        th.deamon = True
        th.start()

        self.update_my_playlists()

    def on_login_failed(self):
        print("login failed")

        page = notLoggedInPage(self)
        page.load()
        self.navigation_view.replace([page])

    def on_create_new_playlist_requested(self, window, playlist_title, playlist_description):
        self.session.user.create_playlist(playlist_title, playlist_description)
        self.update_my_playlists()
        window.close()

    def update_my_playlists(self):
        child = self.sidebar_playlists.get_first_child()
        while child != None:
            self.sidebar_playlists.remove(child)
            del child
            child = self.sidebar_playlists.get_first_child()

        playlists = self.session.user.favorites.playlists()

        for index, playlist in enumerate(playlists):
            if playlist.creator:
                if playlist.creator.name != "me":
                    playlists.remove(playlist)
                    continue
            label = Gtk.Label(xalign=0, label=playlist.name, name=index)
            self.sidebar_playlists.append(label)

        self.my_playlists = playlists

    def _set_last_playing_song(self):
        track_id = self.settings.get_int("last-playing-song-id")
        list_id = self.settings.get_string("last-playing-list-id")
        list_type = self.settings.get_string("last-playing-list-type")

        album_mix_playlist = None

        if list_type == "mix":
            album_mix_playlist = self.session.mix(list_id)
        elif list_type == "album":
            album_mix_playlist = self.session.album(track_id)
        elif list_type == "playlist":
            album_mix_playlist = self.session.playlist(track_id)

        if track_id == -1:
            return

        self.playbar_main_box.set_visible(True)

        # track = self.session.track(track_id)
        self.player_object.play_this(album_mix_playlist, 0)

        self.player_object.pause()

        # TODO Set last playing playlist/mix/album as current playing thing

        # self.player_object. = self.session.track(track_id)

    def on_song_changed(self, *args):
        print("song changed")
        album = self.player_object.song_album
        track = self.player_object.playing_track
        self.song_title_label.set_label(track.name)
        self.artist_label.set_artists(track.artists)
        self.explicit_label.set_visible(track.explicit)

        if variables.is_favourited(track):
            self.in_my_collection_button.set_icon_name("heart-filled-symbolic")
        else:
            self.in_my_collection_button.set_icon_name("heart-outline-thick-symbolic")

        self.settings.set_int("last-playing-song-id", track.id)

        threading.Thread(target=utils.add_image, args=(self.playing_track_image, album)).start()
        threading.Thread(target=utils.add_picture, args=(self.current_carousel_picture, album)).start()

        # next_track = self.player_object.get_next_track()
        # if next_track:
        #     threading.Thread(target=utils.add_picture, args=(self.next_carousel_picture, next_track.album)).start()

        # prev_track = self.player_object.get_prev_track()
        # if prev_track:
        #     threading.Thread(target=utils.add_picture, args=(self.previous_carousel_picture, prev_track.album)).start()

        if self.player_object.is_playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

        th = threading.Thread(target=self.add_lyrics_to_page, args=())
        th.deamon = True
        th.start()

        self.control_bar_artist = track.artist
        self.update_slider()

    def update_controls(self, is_playing, *arg):
        self.playbar_main_box.set_visible(True)
        if not is_playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            print("pause")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")
            print("play")

    def new_login(self):
        """Opens a LoginDialog"""

        login_dialog = LoginDialog(self, self.session)
        login_dialog.present(self)

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

        self.sidebar_list.set_sensitive(False)

        page = notLoggedInPage(self)
        page.load()
        self.navigation_view.replace([page])

    def explore_page(self):
        explore = session.explore()

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
            self.duration = self.player_object.query_duration()
            end_value = self.duration / Gst.SECOND
            self.progress_bar.set_range(0, end_value)

            self.duration_label.set_label(utils.pretty_duration(end_value))

            position = self.player_object.query_position()
            position = position / Gst.SECOND
            self.progress_bar.get_adjustment().set_value(position)
            if end_value != 0:
                self.small_progress_bar.set_fraction(position/end_value)
            self.previous_time = position

            self.time_played_label.set_label(utils.pretty_duration(position))
        return True

    @Gtk.Template.Callback("on_lyrics_button_clicked")
    def on_lyrics_button_clicked_func(self, widget):
        self.main_view_stack.set_visible_child_name("mobile_view")
        self.mobile_stack.set_visible_child_name("lyrics_page")

        th = threading.Thread(target=self.add_lyrics_to_page, args=())
        th.deamon = True
        th.start()

    def add_lyrics_to_page(self):
        try:
            lyrics = self.player_object.playing_track.lyrics()
            self.lyrics_label.set_label(lyrics.text)
        except:
            return

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
        new_playlist_win = NewPlaylistWindow()
        new_playlist_win.connect("create-playlist", self.on_create_new_playlist_requested)
        new_playlist_win.present(self)

    @Gtk.Template.Callback("on_track_radio_button_clicked")
    def on_track_radio_button_clicked_func(self, widget):
        track = self.player_object.playing_track
        page = trackRadioPage(track, f"{track.name} Radio")
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

        playlist = self.my_playlists[int(index)]

        page = playlistPage(playlist, playlist.name)
        page.load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_sidebar_row_selected_clicked")
    def on_sidebar_row_selected_clicked_func(self, list_box, row):
        if row == None:
            return

        name = row.get_child().get_last_child().get_name()

        if name == "HOME":
            self.navigation_view.pop_to_tag("home")
        elif name == "EXPLORE":
            page = explorePage(None, "Explore")
            page.load()
            self.navigation_view.push(page)
        elif name == "F-TRACK":
            page = fromFunctionPage("track", _("Favorite Tracks"))
            page.set_function(self.session.user.favorites.tracks)
            page.load()
            self.navigation_view.push(page)
        elif name == "F-MIX":
            page = fromFunctionPage("mix", _("Favorite Mixes"))
            page.set_function(self.session.user.favorites.mixes)
            page.load()
            self.navigation_view.push(page)
        elif name == "F-ARTIST":
            page = fromFunctionPage("artist", _("Favorite Artists"))
            page.set_function(self.session.user.favorites.artists)
            page.load()
            self.navigation_view.push(page)
        elif name == "F-PLAYLIST":
            page = fromFunctionPage("playlist", _("Favorite Playlists"))
            page.set_function(self.session.user.favorites.playlists)
            page.load()
            self.navigation_view.push(page)
        elif name == "F-ALBUM":
            page = fromFunctionPage("album", _("Favorite Albums"))
            page.set_function(self.session.user.favorites.albums)
            page.load()
            self.navigation_view.push(page)

    @Gtk.Template.Callback("show_sidebar")
    def show_sidebar_func(self, btn):
        self.split_view.set_show_sidebar(True)

    @Gtk.Template.Callback("on_mobile_view_button_clicked")
    def toggle_mobile_view(self, *args):
        if self.main_view_stack.get_visible_child_name() == "normal_view":
            self.main_view_stack.set_visible_child_name("mobile_view")
        else:
            self.main_view_stack.set_visible_child_name("normal_view")

        return True
