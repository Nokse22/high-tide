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
from gi.repository import Xdp

from .mpris import MPRIS

from tidalapi.media import Quality

from .lib import PlayerObject, RepeatType, SecretStore, utils

from .login import LoginDialog
# from .new_playlist import NewPlaylistWindow

from .pages import HTHomePage, HTExplorePage, HTNotLoggedInPage
from .pages import HTCollectionPage
from .pages import HTArtistPage, HTMixPage, HTHrackRadioPage, HTPlaylistPage
from .pages import HTAlbumPage

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
    quality_label = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    playing_track_widget = Gtk.Template.Child()
    sidebar_stack = Gtk.Template.Child()
    go_next_button = Gtk.Template.Child()
    go_prev_button = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings = Gio.Settings.new('io.github.nokse22.HighTide')

        self.settings.bind(
            "window-width", self,
            "default-width", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind(
            "window-height", self,
            "default-height", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind(
            "run-background", self,
            "hide-on-close", Gio.SettingsBindFlags.DEFAULT)

        self.create_action_with_target(
            'push-artist-page',
            GLib.VariantType.new("s"),
            self.on_push_artist_page)

        self.create_action_with_target(
            'push-album-page',
            GLib.VariantType.new("s"),
            self.on_push_album_page)

        self.create_action_with_target(
            'push-playlist-page',
            GLib.VariantType.new("s"),
            self.on_push_playlist_page)

        self.create_action_with_target(
            'push-mix-page',
            GLib.VariantType.new("s"),
            self.on_push_mix_page)

        self.create_action_with_target(
            'push-track-radio-page',
            GLib.VariantType.new("s"),
            self.on_push_track_radio_page)

        # self.create_action_with_target(
        #     'play-next',
        #     GLib.VariantType.new("s"),
        #     self.on_play_next)

        self.player_object = PlayerObject(
            self.settings.get_int('preferred-sink'),
            self.settings.get_boolean('normalize'),
            self.settings.get_boolean('quadratic-volume'))
        utils.player_object = self.player_object

        self.volume_button.get_adjustment().set_value(
            self.settings.get_int("last-volume")/10)

        self.player_object.connect(
            "notify::shuffle", self.on_shuffle_changed)
        self.player_object.connect(
            "update-slider", self.update_slider)
        self.player_object.connect(
            "song-changed", self.on_song_changed)
        self.player_object.connect(
            "song-added-to-queue", self.on_song_added_to_queue)
        self.player_object.connect(
            "notify::playing", self.update_controls)
        self.player_object.connect(
            "buffering", self.on_song_buffering)
        self.player_object.connect(
            "notify::repeat-type", self.update_repeat_button)
        self.player_object.connect(
            "notify::can-go-next",
            lambda *_: self.go_next_button.set_sensitive(
                self.player_object.can_go_next))
        self.player_object.connect(
            "notify::can-go-prev",
            lambda *_: self.go_prev_button.set_sensitive(
                self.player_object.can_go_prev))

        self.player_object.repeat_type = self.settings.get_int("repeat")
        if self.player_object.repeat_type == RepeatType.NONE:
            self.repeat_button.set_icon_name(
                "media-playlist-consecutive-symbolic")
        elif self.player_object.repeat_type == RepeatType.LIST:
            self.repeat_button.set_icon_name(
                "media-playlist-repeat-symbolic")
        elif self.player_object.repeat_type == RepeatType.SONG:
            self.repeat_button.set_icon_name(
                "playlist-repeat-song-symbolic")

        self.artist_label.connect(
            "activate-link", utils.open_uri)
        self.miniplayer_artist_label.connect(
            "activate-link", utils.open_uri)

        self.session = tidalapi.Session()

        utils.session = self.session
        utils.navigation_view = self.navigation_view
        utils.toast_overlay = self.toast_overlay

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

        threading.Thread(target=self.th_login, args=()).start()

        MPRIS(self.player_object)

        self.portal = Xdp.Portal()

        self.portal.set_background_status(_("Playing Music"))

    #
    #   LOGIN
    #

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
            utils.get_favourites()
            GLib.idle_add(self.on_logged_in)

    def logout(self):
        self.secret_store.clear()

        page = HTNotLoggedInPage().load()
        self.navigation_view.replace([page])

    def on_logged_in(self):
        print("logged in")

        page = HTHomePage().load()
        self.navigation_view.replace([page])

        self.player_lyrics_queue.set_sensitive(True)
        self.navigation_buttons.set_sensitive(True)

        threading.Thread(target=self.th_set_last_playing_song, args=()).start()

    def on_login_failed(self):
        print("login failed")

        page = HTNotLoggedInPage().load()
        self.navigation_view.replace([page])

    def th_set_last_playing_song(self):
        index = self.settings.get_int("last-playing-index")
        thing_id = self.settings.get_string("last-playing-thing-id")
        thing_type = self.settings.get_string("last-playing-thing-type")

        print(f"Last playing: {thing_id} of type {thing_type} index: {index}")

        thing = None

        try:
            if thing_type == "mix":
                thing = self.session.mix(thing_id)
            elif thing_type == "album":
                thing = self.session.album(thing_id)
            elif thing_type == "playlist":
                thing = self.session.playlist(thing_id)
            elif thing_type == "track":
                thing = self.session.track(thing_id)
        except Exception as e:
            print(e)

        self.player_object.play_this(thing, index)

        self.player_object.pause()

    #
    #   UPDATES UI
    #

    def on_song_changed(self, *args):
        print("song changed")
        album = self.player_object.song_album
        track = self.player_object.playing_track

        if track is None:
            return

        self.song_title_label.set_label(track.full_name if hasattr(track, 'full_name') else track.name)
        self.song_title_label.set_tooltip_text(track.full_name if hasattr(track, 'full_name') else track.name)
        self.artist_label.set_artists(track.artists)
        self.explicit_label.set_visible(track.explicit)

        self.set_quality_label()

        if utils.is_favourited(track):
            self.in_my_collection_button.set_icon_name(
                "heart-filled-symbolic")
        else:
            self.in_my_collection_button.set_icon_name(
                "heart-outline-thick-symbolic")

        self.save_last_playing_thing()

        if self.image_canc:
            self.image_canc.cancel()
            self.image_canc = Gio.Cancellable.new()

        threading.Thread(
            target=utils.add_picture,
            args=(self.playing_track_picture, album, self.image_canc)).start()

        threading.Thread(
            target=utils.add_image,
            args=(self.playing_track_image, album)).start()

        threading.Thread(target=self.th_add_lyrics_to_page, args=()).start()

        self.control_bar_artist = track.artist
        self.update_slider()

        if self.queue_widget.get_mapped():
            self.queue_widget.update_all(self.player_object)
            self.queue_widget_updated = True
        else:
            self.queue_widget_updated = False

    def save_last_playing_thing(self):
        mix_album_playlist = self.player_object.current_mix_album_playlist
        track = self.player_object.playing_track

        if (mix_album_playlist is not None and
                not isinstance(mix_album_playlist, list)):
            self.settings.set_string(
                "last-playing-thing-id",
                str(mix_album_playlist.id))
            self.settings.set_string(
                "last-playing-thing-type",
                utils.get_type(mix_album_playlist))
        if track is not None:
            self.settings.set_int(
                "last-playing-index",
                self.player_object.get_index())

    def set_quality_label(self):
        codec = None
        bit_depth = None
        sample_rate = None

        stream = self.player_object.stream
        if stream:
            if stream.bit_depth:
                bit_depth = f"{stream.bit_depth}-bit"
            if stream.sample_rate:
                sample_rate = f"{stream.sample_rate / 1000:.1f} kHz"
            if stream.audio_quality:
                match stream.audio_quality:
                    case "LOW":
                        bitrate = "96 kbps"
                    case "HIGH":
                        bitrate = "320 kbps"
                    case _:
                        bitrate = "Lossless"

        manifest = self.player_object.manifest
        if manifest:
            if manifest.codecs:
                codec = manifest.codecs
                if codec == "MP4A":
                    codec = "AAC"
                self.quality_label.set_visible(False)

        quality_text = f"{codec}"

        if bit_depth or sample_rate:
            quality_details = []
            if bit_depth and codec != "AAC":
                quality_details.append(bit_depth)
            if sample_rate and codec != "AAC":
                quality_details.append(sample_rate)
            if bitrate and codec == "AAC":
                quality_details.append(bitrate)

            if quality_details:
                quality_text += f" ({' / '.join(quality_details)})"

        self.quality_label.set_label(quality_text)
        self.quality_label.set_visible(True)

    def update_controls(self, player, *args):
        if player.playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

    def update_repeat_button(self, player, repeat_type):
        if player.repeat_type == RepeatType.NONE:
            self.repeat_button.set_icon_name(
                "media-playlist-consecutive-symbolic")
        elif player.repeat_type == RepeatType.LIST:
            self.repeat_button.set_icon_name(
                "media-playlist-repeat-symbolic")
        elif player.repeat_type == RepeatType.SONG:
            self.repeat_button.set_icon_name(
                "playlist-repeat-song-symbolic")

    def on_song_buffering(self, player, percentage):
        if percentage != 100:
            self.buffer_spinner.set_visible(True)
        else:
            self.buffer_spinner.set_visible(False)

    #
    #   CALLBACKS
    #

    @Gtk.Template.Callback("on_play_button_clicked")
    def on_play_button_clicked(self, btn):
        self.player_object.play_pause()

    @Gtk.Template.Callback("on_share_clicked")
    def on_share_clicked(self, *args):
        track = self.player_object.playing_track
        if track:
            utils.share_this(track)

    @Gtk.Template.Callback("on_track_radio_button_clicked")
    def on_track_radio_button_clicked_func(self, widget):
        track = self.player_object.playing_track
        page = HTHrackRadioPage(track.id).load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_album_button_clicked")
    def on_album_button_clicked_func(self, widget):
        track = self.player_object.playing_track
        page = HTAlbumPage(track.album.id).load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_skip_forward_button_clicked")
    def on_skip_forward_button_clicked_func(self, widget):
        self.player_object.play_next()

    @Gtk.Template.Callback("on_skip_backward_button_clicked")
    def on_skip_backward_button_clicked_func(self, widget):
        self.player_object.play_previous()

    @Gtk.Template.Callback("on_home_button_clicked")
    def on_home_button_clicked_func(self, widget):
        self.navigation_view.pop_to_tag("home")

    @Gtk.Template.Callback("on_explore_button_clicked")
    def on_explore_button_clicked_func(self, widget):
        if self.navigation_view.find_page("explore"):
            self.navigation_view.pop_to_tag("explore")
            return

        page = HTExplorePage().load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_collection_button_clicked")
    def on_collection_button_clicked_func(self, widget):
        if self.navigation_view.find_page("collection"):
            self.navigation_view.pop_to_tag("collection")
            return

        page = HTCollectionPage().load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_repeat_clicked")
    def on_repeat_clicked(self, *args):
        if self.player_object.repeat_type == RepeatType.NONE:
            self.player_object.repeat_type = RepeatType.SONG
        elif self.player_object.repeat_type == RepeatType.LIST:
            self.player_object.repeat_type = RepeatType.NONE
        elif self.player_object.repeat_type == RepeatType.SONG:
            self.player_object.repeat_type = RepeatType.LIST

        self.settings.set_int("repeat", self.player_object.repeat_type)

    @Gtk.Template.Callback("on_in_my_collection_button_clicked")
    def on_in_my_collection_button_clicked(self, btn):
        utils.on_in_to_my_collection_button_clicked(
            btn, self.player_object.playing_track)

    @Gtk.Template.Callback("on_shuffle_button_toggled")
    def on_shuffle_button_toggled(self, btn):
        self.player_object.shuffle = btn.get_active()

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

    def on_song_added_to_queue(self, *args):
        if self.queue_widget.get_mapped():
            self.queue_widget.update_queue(self.player_object)
            self.queue_widget_updated = True
        else:
            self.queue_widget_updated = False

    @Gtk.Template.Callback("on_queue_widget_mapped")
    def on_queue_widget_mapped(self, *args):
        if not self.queue_widget_updated:
            self.queue_widget.update_all(self.player_object)
            self.queue_widget_updated = True

    @Gtk.Template.Callback("on_navigation_view_page_popped")
    def on_navigation_view_page_popped_func(self, nav_view, nav_page):
        nav_page.disconnect_all()

    @Gtk.Template.Callback("on_visible_page_changed")
    def on_visible_page_changed(self, nav_view, *args):
        match self.navigation_view.get_visible_page().get_tag():
            case "home":
                self.home_button.set_active(True)
            case "explore":
                self.explore_button.set_active(True)
            case "collection":
                self.collection_button.set_active(True)

    @Gtk.Template.Callback("on_sidebar_page_changed")
    def on_sidebar_page_changed(self, *args):
        if self.sidebar_stack.get_visible_child_name() == "player":
            self.playing_track_widget.set_visible(False)
        else:
            self.playing_track_widget.set_visible(True)

    def on_shuffle_changed(self, *args):
        self.shuffle_button.set_active(self.player_object.shuffle)

    def update_slider(self, *args):
        """Called on a timer, it updates the progress bar and
            adds the song duration and position."""
        self.duration = self.player_object.query_duration()
        end_value = self.duration / Gst.SECOND

        position = self.player_object.query_position(default=None)
        if position is None:
            return
        position = position / Gst.SECOND
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
            if lyrics and lyrics.subtitles:
                GLib.idle_add(self.lyrics_widget.set_lyrics, lyrics.subtitles)
            else:
                self.lyrics_widget.clear()
        except Exception:
            self.lyrics_widget.clear()

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
        if self.settings.get_int("preferred-sink") != sink:
            self.player_object.change_audio_sink(sink)
            self.settings.set_int("preferred-sink", sink)

    def change_normalization(self, state):
        if self.player_object.normalize != state:
            self.player_object.normalize = state
            self.settings.set_boolean("normalize", state)
            # recreate audio pipeline, kinda dirty ngl
            self.player_object.change_audio_sink(
                self.settings.get_int("preferred-sink"))

    def change_quadratic_volume(self, state):
        if self.settings.get_boolean("quadratic-volume") != state:
            self.player_object.quadratic_volume = state
            self.settings.set_boolean("quadratic-volume", state)

    #
    #   PAGES ACTIONS CALLBACKS
    #

    def on_push_artist_page(self, action, parameter):
        page = HTArtistPage(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_album_page(self, action, parameter):
        page = HTAlbumPage(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_playlist_page(self, action, parameter):
        page = HTPlaylistPage(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_mix_page(self, action, parameter):
        page = HTMixPage(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_track_radio_page(self, action, parameter):
        page = HTHrackRadioPage(parameter.get_string()).load()
        self.navigation_view.push(page)

    #
    #
    #

    def create_action_with_target(self, name, target_type, callback):
        """Used to create a new action with a target"""

        action = Gio.SimpleAction.new(name, target_type)
        action.connect("activate", callback)
        self.add_action(action)
        return action
