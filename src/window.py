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

import threading
import requests
import tidalapi

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import Gst, GLib

from .mpris import MPRIS

from tidalapi.media import Quality

from .lib import PlayerObject, RepeatType
from .lib import utils

from .login import LoginDialog
from .new_playlist import NewPlaylistWindow

from .pages import homePage, explorePage, notLoggedInPage, collectionPage
from .pages import trackRadioPage, playlistPage, startUpPage, fromFunctionPage

from .lib import SecretStore
from .lib import variables

from .widgets import HTGenericTrackWidget
from .widgets import HTLinkLabelWidget
from .widgets import HTQueueWidget
from .widgets import HTLyricsWidget

from gettext import gettext as _


@Gtk.Template(resource_path='/io/github/nokse22/HighTide/ui/window.ui')
class HighTideWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'HighTideWindow'

    progress_bar = Gtk.Template.Child()
    duration_label = Gtk.Template.Child()
    time_played_label = Gtk.Template.Child()
    shuffle_button = Gtk.Template.Child()
    navigation_view = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    small_progress_bar = Gtk.Template.Child()
    song_title_label = Gtk.Template.Child()
    playing_track_picture = Gtk.Template.Child()
    playing_track_image = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    miniplayer_artist_label = Gtk.Template.Child()
    volume_button = Gtk.Template.Child()
    in_my_collection_button = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()
    queue_widget = Gtk.Template.Child()
    lyrics_widget = Gtk.Template.Child()
    repeat_button = Gtk.Template.Child()
    home_button = Gtk.Template.Child()
    explore_button = Gtk.Template.Child()
    collection_button = Gtk.Template.Child()
    player_lyrics_queue = Gtk.Template.Child()
    navigation_buttons = Gtk.Template.Child()
    buffer_spinner = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings = Gio.Settings.new('io.github.nokse22.HighTide')

        self.settings.bind(
            "window-width", self,
            "default-width", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind(
            "window-height", self,
            "default-height", Gio.SettingsBindFlags.DEFAULT)

        self.player_object = PlayerObject(
            self.settings.get_int('preferred-sink'),
            self.settings.get_boolean('normalize'))
        variables.player_object = self.player_object

        self.volume_button.get_adjustment().set_value(
            self.settings.get_int("last-volume")/10)

        self.shuffle_button.connect("toggled", self.on_shuffle_button_toggled)

        self.player_object.connect(
            "shuffle-changed", self.on_shuffle_changed)
        self.player_object.connect(
            "update-slider", self.update_slider)
        self.player_object.connect(
            "song-changed", self.on_song_changed)
        self.player_object.connect(
            "song-added-to-queue", self.on_song_added_to_queue)
        self.player_object.connect(
            "play-changed", self.update_controls)
        self.player_object.connect(
            "buffering", self.on_song_buffering)

        self.player_object.repeat = self.settings.get_int("repeat")
        if self.player_object.repeat == RepeatType.NONE:
            self.repeat_button.set_icon_name(
                "media-playlist-consecutive-symbolic")
        elif self.player_object.repeat == RepeatType.LIST:
            self.repeat_button.set_icon_name(
                "media-playlist-repeat-symbolic")
        elif self.player_object.repeat == RepeatType.SONG:
            self.repeat_button.set_icon_name(
                "playlist-repeat-song-symbolic")

        self.queue_widget.connect(
            "map", self.on_queue_widget_mapped)

        self.artist_label.connect(
            "activate-link", variables.open_uri)
        self.miniplayer_artist_label.connect(
            "activate-link", variables.open_uri)

        self.session = tidalapi.Session()

        variables.session = self.session
        variables.navigation_view = self.navigation_view

        self.user = self.session.user

        self.select_quality(self.settings.get_int("quality"))

        self.current_mix = None
        self.player_object.current_song_index = 0
        self.previous_fraction = 0
        self.favourite_playlists = []
        self.my_playlists = []

        self.image_canc = None

        self.queue_widget_updated = False

        self.secret_store = SecretStore(self.session)

        page = startUpPage(None, "Loading")
        page.load()
        self.navigation_view.push(page)

        self.navigation_view.connect(
            "notify::visible-page", self.on_visible_page_changed)

        threading.Thread(target=self.th_login, args=()).start()

        MPRIS(self.player_object)

    def on_logged_in(self):
        print("on logged in")
        variables.get_favourites()
        # FIXME if it doesn't login fast enough it doesn't let the user login

        page = homePage(self)
        page.load()
        self.navigation_view.replace([page])

        self.player_lyrics_queue.set_sensitive(True)
        self.navigation_buttons.set_sensitive(True)

        threading.Thread(target=self.th_set_last_playing_song, args=()).start()

    def on_login_failed(self):
        print("login failed")

        page = notLoggedInPage(self)
        page.load()
        self.navigation_view.replace([page])

    def th_set_last_playing_song(self):
        track_id = self.settings.get_int("last-playing-song-id")
        list_id = self.settings.get_string("last-playing-list-id")
        list_type = self.settings.get_string("last-playing-list-type")

        album_mix_playlist = None

        try:
            if list_type == "mix":
                album_mix_playlist = self.session.mix(list_id)
            elif list_type == "album":
                album_mix_playlist = self.session.album(track_id)
            elif list_type == "playlist":
                album_mix_playlist = self.session.playlist(track_id)
        except Exception as e:
            print(e)

        if track_id == -1:
            return

        # track = self.session.track(track_id)
        self.player_object.play_this(album_mix_playlist, 0)

        self.player_object.pause()

        # TODO Set last playing playlist/mix/album as current playing thing

        # self.player_object. = self.session.track(track_id)

    def on_song_changed(self, *args):
        print("song changed")
        album = self.player_object.song_album
        track = self.player_object.playing_track

        if track is None:
            return

        self.song_title_label.set_label(track.name)
        self.artist_label.set_artists(track.artists)
        self.explicit_label.set_visible(track.explicit)

        if variables.is_favourited(track):
            self.in_my_collection_button.set_icon_name(
                "heart-filled-symbolic")
        else:
            self.in_my_collection_button.set_icon_name(
                "heart-outline-thick-symbolic")

        self.settings.set_int("last-playing-song-id", track.id)

        if self.image_canc:
            self.image_canc.cancel()
            self.image_canc = Gio.Cancellable.new()

        threading.Thread(
            target=utils.add_picture,
            args=(self.playing_track_picture, album, self.image_canc)).start()

        threading.Thread(
            target=utils.add_image,
            args=(self.playing_track_image, album)).start()

        if self.player_object.is_playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

        threading.Thread(target=self.th_add_lyrics_to_page, args=()).start()

        self.control_bar_artist = track.artist
        self.update_slider()

        if self.queue_widget.get_mapped():
            self.queue_widget.update_all(self.player_object)
            self.queue_widget_updated = True
        else:
            self.queue_widget_updated = False

    def update_controls(self, is_playing, *args):
        if not is_playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            print("pause")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")
            print("play")

    def on_song_buffering(self, player, percentage):
        if percentage != 100:
            self.buffer_spinner.set_visible(True)
        else:
            self.buffer_spinner.set_visible(False)

    def new_login(self):
        """Opens a LoginDialog"""

        login_dialog = LoginDialog(self, self.session)
        login_dialog.present(self)

    def th_login(self):
        """Logs the user in, if it doesn't work it calls on_login_failed()"""
        try:
            self.session.load_oauth_session(
                self.secret_store.token_dictionary["token-type"],
                self.secret_store.token_dictionary["access-token"],
                self.secret_store.token_dictionary["refresh-token"],
                self.secret_store.token_dictionary["expiry-time"])
        except Exception as e:
            print(f"error! {e}")
            GLib.idle_add(self.on_login_failed)
        else:
            GLib.idle_add(self.on_logged_in)

    def logout(self):
        self.secret_store.clear()

        page = notLoggedInPage(self)
        page.load()
        self.navigation_view.replace([page])

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

    def on_shuffle_button_toggled(self, btn):
        state = btn.get_active()
        self.player_object.shuffle(state)

    def on_shuffle_changed(self, player, state):
        print("SHUFFLE CHANGED")
        self.shuffle_button.set_active(state)

    def update_slider(self, *args):
        """Called on a timer, it updates the progress bar and
            adds the song duration and position."""
        self.duration = self.player_object.query_duration()

        end_value = self.duration / Gst.SECOND
        position = self.player_object.query_position() / Gst.SECOND
        fraction = 0

        self.lyrics_widget.set_current_line(position)

        self.duration_label.set_label(utils.pretty_duration(end_value))

        if end_value != 0:
            fraction = position/end_value
        self.small_progress_bar.set_fraction(fraction)
        self.progress_bar.get_adjustment().set_value(fraction)

        self.previous_fraction = fraction

        self.time_played_label.set_label(utils.pretty_duration(position))

    def th_add_lyrics_to_page(self):
        try:
            lyrics = self.player_object.playing_track.lyrics()
            GLib.idle_add(self.lyrics_widget.set_lyrics, lyrics.subtitles)
        except Exception:
            return

    def th_download_song(self):
        """Added to check the streamed song quality, triggered with ctrl+d"""

        song = self.player_object.playing_track
        song_url = song.get_url()
        try:
            response = requests.get(song_url)
        except Exception:
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
                self.session.audio_quality = Quality.hi_res_lossless

        self.settings.set_int("quality", pos)

    def change_audio_sink(self, sink):
        self.player_object.change_audio_sink(sink)
        self.settings.set_int("preferred-sink", sink)

    def change_normalization(self, state):
        if self.player_object.normalize != state:
            self.player_object.normalize = state
            self.settings.set_boolean("normalize", state)
            # recreate audio pipeline, kinda dirty ngl
            self.player_object.change_audio_sink(
                self.settings.get_int("preferred-sink"))

    @Gtk.Template.Callback("on_track_radio_button_clicked")
    def on_track_radio_button_clicked_func(self, widget):
        track = self.player_object.playing_track
        page = trackRadioPage(track, f"{track.name} Radio")
        page.load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_in_my_collection_button_clicked")
    def on_in_my_collection_button_clicked(self, btn):
        icon_name = self.in_my_collection_button.get_icon_name()

        if icon_name == "heart-outline-thick-symbolic":
            threading.Thread(
                target=self.th_add_track_to_my_collection,
                args=(self.player_object.playing_track.id,)).start()
        else:
            threading.Thread(
                target=self.th_remove_track_from_my_collection,
                args=(self.player_object.playing_track.id,)).start()

    def th_add_track_to_my_collection(self, track_id):
        result = self.session.user.favorites.add_track(track_id)
        if result:
            self.in_my_collection_button.set_icon_name(
                "heart-filled-symbolic")
            print("successfully added to my collection")

    def th_remove_track_from_my_collection(self, track_id):
        result = self.session.user.favorites.remove_track(track_id)
        if result:
            self.in_my_collection_button.set_icon_name(
                "heart-outline-thick-symbolic")
            print("successfully removed from my collection")

    @Gtk.Template.Callback("on_volume_changed")
    def on_volume_changed_func(self, widget, value):
        self.player_object.change_volume(value)
        self.settings.set_int("last-volume", int(value*10))

    @Gtk.Template.Callback("on_slider_seek")
    def on_slider_seek(self, *args):
        seek_fraction = self.progress_bar.get_value()

        if abs(seek_fraction - self.previous_fraction) == 0.0:
            return

        print("seeking: ", abs(seek_fraction - self.previous_fraction))

        self.player_object.seek(seek_fraction)
        self.previous_fraction = seek_fraction

    @Gtk.Template.Callback("on_seek_from_lyrics")
    def on_seek_from_lyrics(self, lyrics_widget, time_ms):
        end_value = self.duration / Gst.SECOND

        position = time_ms / 1000

        self.player_object.seek(position/end_value)

    @Gtk.Template.Callback("on_skip_forward_button_clicked")
    def on_skip_forward_button_clicked_func(self, widget):
        print("skip forward")
        self.player_object.play_next()

    @Gtk.Template.Callback("on_skip_backward_button_clicked")
    def on_skip_backward_button_clicked_func(self, widget):
        print("skip backward")
        self.player_object.play_previous()

    @Gtk.Template.Callback("on_home_button_clicked")
    def on_home_button_clicked_func(self, widget):
        self.navigation_view.pop_to_tag("home")

    @Gtk.Template.Callback("on_explore_button_clicked")
    def on_explore_button_clicked_func(self, widget):
        if self.navigation_view.find_page("explore"):
            self.navigation_view.pop_to_tag("explore")
            return

        page = explorePage(None, "Explore")
        page.load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_collection_button_clicked")
    def on_collection_button_clicked_func(self, widget):
        if self.navigation_view.find_page("collection"):
            self.navigation_view.pop_to_tag("collection")
            return

        page = collectionPage(None, "Collection")
        page.load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_repeat_clicked")
    def on_repeat_clicked(self, *args):
        if self.player_object.repeat == RepeatType.NONE:
            self.repeat_button.set_icon_name(
                "playlist-repeat-song-symbolic")
            self.player_object.repeat = RepeatType.SONG
        elif self.player_object.repeat == RepeatType.LIST:
            self.repeat_button.set_icon_name(
                "media-playlist-consecutive-symbolic")
            self.player_object.repeat = RepeatType.NONE
        elif self.player_object.repeat == RepeatType.SONG:
            self.repeat_button.set_icon_name(
                "media-playlist-repeat-symbolic")
            self.player_object.repeat = RepeatType.LIST

        self.settings.set_int("repeat", self.player_object.repeat)

    def on_song_added_to_queue(self, *args):
        if self.queue_widget.get_mapped():
            self.queue_widget.update_queue(self.player_object)
            self.queue_widget_updated = True
        else:
            self.queue_widget_updated = False

    def on_queue_widget_mapped(self, *args):
        print("queue mapped")
        if not self.queue_widget_updated:
            self.queue_widget.update_all(self.player_object)
            self.queue_widget_updated = True

    @Gtk.Template.Callback("on_navigation_view_page_popped")
    def on_navigation_view_page_popped_func(self, nav_view, nav_page):
        nav_page.disconnect_all()

    def on_visible_page_changed(self, nav_view, *args):
        match self.navigation_view.get_visible_page().get_tag():
            case "home":
                self.home_button.set_active(True)
            case "explore":
                self.explore_button.set_active(True)
            case "collection":
                self.collection_button.set_active(True)
