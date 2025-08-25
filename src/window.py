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
from gettext import gettext as _
from typing import Callable

import tidalapi
from gi.repository import Adw, Gio, GLib, GObject, Gst, Gtk, Xdp
from tidalapi import Quality

from .lib import HTCache, PlayerObject, RepeatType, SecretStore, utils
from .login import LoginDialog
from .mpris import MPRIS
from .pages import (HTAlbumPage, HTArtistPage, HTCollectionPage, HTExplorePage,
                    HTGenericPage, HTMixPage, HTNotLoggedInPage,
                    HTPlaylistPage)
from .widgets import (HTGenericTrackWidget, HTLinkLabelWidget, HTLyricsWidget,
                      HTQueueWidget)

# from .new_playlist import NewPlaylistWindow

GObject.type_register(HTGenericTrackWidget)
GObject.type_register(HTLinkLabelWidget)
GObject.type_register(HTQueueWidget)
GObject.type_register(HTLyricsWidget)


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/window.ui")
class HighTideWindow(Adw.ApplicationWindow):
    __gtype_name__ = "HighTideWindow"

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
    track_radio_button = Gtk.Template.Child()
    album_button = Gtk.Template.Child()
    copy_share_link = Gtk.Template.Child()

    app_id_dialog = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.settings = Gio.Settings.new("io.github.nokse22.high-tide")

        self.settings.bind(
            "window-width", self, "default-width", Gio.SettingsBindFlags.DEFAULT
        )
        self.settings.bind(
            "window-height", self, "default-height", Gio.SettingsBindFlags.DEFAULT
        )
        self.settings.bind(
            "run-background", self, "hide-on-close", Gio.SettingsBindFlags.DEFAULT
        )

        self.create_action_with_target(
            "push-artist-page", GLib.VariantType.new("s"), self.on_push_artist_page
        )

        self.create_action_with_target(
            "push-album-page", GLib.VariantType.new("s"), self.on_push_album_page
        )

        self.create_action_with_target(
            "push-playlist-page", GLib.VariantType.new("s"), self.on_push_playlist_page
        )

        self.create_action_with_target(
            "push-mix-page", GLib.VariantType.new("s"), self.on_push_mix_page
        )

        self.create_action_with_target(
            "push-track-radio-page",
            GLib.VariantType.new("s"),
            self.on_push_track_radio_page,
        )

        self.create_action_with_target(
            "push-artist-radio-page",
            GLib.VariantType.new("s"),
            self.on_push_artist_radio_page,
        )

        # self.create_action_with_target(
        #     'play-next',
        #     GLib.VariantType.new("s"),
        #     self.on_play_next)

        self.player_object = PlayerObject(
            self.settings.get_int("preferred-sink"),
            self.settings.get_string("alsa-device"),
            self.settings.get_boolean("normalize"),
            self.settings.get_boolean("quadratic-volume"),
        )
        utils.player_object = self.player_object
        self.player_object.set_discord_rpc(self.settings.get_boolean("discord-rpc"))

        self.volume_button.get_adjustment().set_value(
            self.settings.get_int("last-volume") / 10
        )

        self.player_object.connect("notify::shuffle", self.on_shuffle_changed)
        self.player_object.connect("update-slider", self.update_slider)
        self.player_object.connect("song-changed", self.on_song_changed)
        self.player_object.connect("song-added-to-queue", self.on_song_added_to_queue)
        self.player_object.connect("notify::playing", self.update_controls)
        self.player_object.connect("buffering", self.on_song_buffering)
        self.player_object.connect("notify::repeat-type", self.update_repeat_button)
        self.player_object.connect(
            "notify::can-go-next",
            lambda *_: self.go_next_button.set_sensitive(
                self.player_object.can_go_next
            ),
        )
        self.player_object.connect(
            "notify::can-go-prev",
            lambda *_: self.go_prev_button.set_sensitive(
                self.player_object.can_go_prev
            ),
        )

        self.player_object.repeat_type = self.settings.get_int("repeat")
        if self.player_object.repeat_type == RepeatType.NONE:
            self.repeat_button.set_icon_name("media-playlist-consecutive-symbolic")
        elif self.player_object.repeat_type == RepeatType.LIST:
            self.repeat_button.set_icon_name("media-playlist-repeat-symbolic")
        elif self.player_object.repeat_type == RepeatType.SONG:
            self.repeat_button.set_icon_name("playlist-repeat-song-symbolic")

        self.artist_label.connect("activate-link", utils.open_uri)
        self.miniplayer_artist_label.connect("activate-link", utils.open_uri)

        self.session = tidalapi.Session()

        utils.session = self.session
        utils.navigation_view = self.navigation_view
        utils.toast_overlay = self.toast_overlay
        utils.cache = HTCache(self.session)

        self.user = self.session.user

        self.select_quality(self.settings.get_int("quality"))

        self.current_mix = None
        self.player_object.current_song_index = 0
        self.previous_fraction = 0
        self.favourite_playlists = []
        self.my_playlists = []

        self.image_canc = None

        self.queued_uri = None
        self.is_logged_in = False

        self.videoplayer = Gtk.MediaFile.new()

        self.video_covers_enabled = self.settings.get_boolean("video-covers")
        self.in_background = False

        self.queue_widget_updated = False

        self.secret_store = SecretStore(self.session)

        threading.Thread(target=self.th_login, args=()).start()

        MPRIS(self.player_object)

        self.portal = Xdp.Portal()

        self.portal.set_background_status(_("Playing Music"))

        self.connect("notify::is-active", self.stop_video_in_background)

        if not self.settings.get_boolean("app-id-change-understood"):
            self.app_id_dialog.present(self)

    @Gtk.Template.Callback("on_app_id_response_cb")
    def on_app_id_response_cb(self, dialog, response):
        self.app_id_dialog.close()

    @Gtk.Template.Callback("on_app_id_check_toggled_cb")
    def on_app_id_check_toggled_cb(self, check_btn):
        self.app_id_dialog.set_response_enabled("close", check_btn.get_active())

    @Gtk.Template.Callback("on_app_id_closed_cb")
    def on_app_id_closed_cb(self, dialog):
        self.settings.set_boolean("app-id-change-understood", True)

    #
    #   LOGIN
    #

    def new_login(self):
        """Open a new login dialog for user authentication"""

        login_dialog = LoginDialog(self, self.session)
        login_dialog.present(self)

    def th_login(self):
        try:
            self.session.load_oauth_session(
                self.secret_store.token_dictionary["token-type"],
                self.secret_store.token_dictionary["access-token"],
                self.secret_store.token_dictionary["refresh-token"],
                self.secret_store.token_dictionary["expiry-time"],
            )
        except Exception as e:
            print(f"error! {e}")
            GLib.idle_add(self.on_login_failed)
        else:
            utils.get_favourites()
            GLib.idle_add(self.on_logged_in)

    def logout(self):
        """Log out the current user and return to login screen.

        Clears stored authentication tokens and navigates back to the
        not logged in page.
        """
        self.secret_store.clear()

        page = HTNotLoggedInPage().load()
        self.navigation_view.replace([page])

    def on_logged_in(self):
        """Handle successful user login"""
        print("logged in")

        page = HTGenericPage.new_from_function(utils.session.home).load()
        page.set_tag("home")
        self.navigation_view.replace([page])

        self.player_lyrics_queue.set_sensitive(True)
        self.navigation_buttons.set_sensitive(True)

        threading.Thread(target=self.th_set_last_playing_song, args=()).start()

        self.is_logged_in = True

        if self.queued_uri:
            utils.open_tidal_uri(self.queued_uri)

    def on_login_failed(self):
        """Handle failed login attempts"""
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
        """Handle song change events from the player.

        Updates the UI elements when the currently playing song changes,
        including album art, track information, and video covers.
        """
        print("song changed")
        album = self.player_object.song_album
        track = self.player_object.playing_track

        if track is None:
            return

        track_name = track.full_name if hasattr(track, "full_name") else track.name
        self.song_title_label.set_label(track_name)
        self.song_title_label.set_tooltip_text(track_name)
        self.artist_label.set_artists(track.artists)
        self.explicit_label.set_visible(track.explicit)

        self.set_quality_label()

        self.track_radio_button.set_action_target_value(
            GLib.Variant("s", str(track.id))
        )
        self.album_button.set_action_target_value(GLib.Variant("s", str(album.id)))

        if utils.is_favourited(track):
            self.in_my_collection_button.set_icon_name("heart-filled-symbolic")
        else:
            self.in_my_collection_button.set_icon_name("heart-outline-thick-symbolic")

        self.save_last_playing_thing()

        if self.image_canc:
            self.image_canc.cancel()
            self.image_canc = Gio.Cancellable.new()

        # Remove old video cover should maybe be threaded
        if self.video_covers_enabled:
            self.videoplayer.pause()
            self.videoplayer.clear()

        if self.video_covers_enabled and album.video_cover:
            threading.Thread(
                target=utils.add_video_cover,
                args=(
                    self.playing_track_picture,
                    self.videoplayer,
                    album,
                    self.in_background,
                    self.image_canc,
                ),
            ).start()
        else:
            threading.Thread(
                target=utils.add_picture,
                args=(self.playing_track_picture, album, self.image_canc),
            ).start()

        threading.Thread(
            target=utils.add_image, args=(self.playing_track_image, album)
        ).start()

        threading.Thread(target=self.th_add_lyrics_to_page, args=()).start()

        self.control_bar_artist = track.artist
        self.update_slider()

        if self.queue_widget.get_mapped():
            self.queue_widget.update_all(self.player_object)
            self.queue_widget_updated = True
        else:
            self.queue_widget_updated = False

    def save_last_playing_thing(self):
        """Save the current playing context to settings for persistence.

        Stores information about the currently playing track and its source
        (album, playlist, mix, etc.) so playback can resume on app restart.
        """
        mix_album_playlist = self.player_object.current_mix_album_playlist
        track = self.player_object.playing_track

        if mix_album_playlist is not None and not isinstance(mix_album_playlist, list):
            self.settings.set_string(
                "last-playing-thing-id", str(mix_album_playlist.id)
            )
            self.settings.set_string(
                "last-playing-thing-type", utils.get_type(mix_album_playlist)
            )
        if track is not None:
            self.settings.set_int("last-playing-index", self.player_object.get_index())

    def stop_video_in_background(self, window, param):
        self.in_background = not self.is_active()
        album = self.player_object.song_album
        if not self.video_covers_enabled or not album or not album.video_cover:
            return

        if self.is_active():
            self.videoplayer.play()
        else:
            self.videoplayer.pause()

    def set_quality_label(self):
        """Update the quality label with current track's audio information.

        Displays information about the current track's codec, bit depth,
        sample rate, and audio quality in the UI.
        """
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

    def update_controls(self, *args):
        """Update playback control button states based on player status"""
        if self.player_object.playing:
            self.play_button.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_button.set_icon_name("media-playback-start-symbolic")

    def update_repeat_button(self, player, repeat_type):
        """Update the repeat button icon based on current repeat mode"""
        if player.repeat_type == RepeatType.NONE:
            self.repeat_button.set_icon_name("media-playlist-consecutive-symbolic")
        elif player.repeat_type == RepeatType.LIST:
            self.repeat_button.set_icon_name("media-playlist-repeat-symbolic")
        elif player.repeat_type == RepeatType.SONG:
            self.repeat_button.set_icon_name("playlist-repeat-song-symbolic")

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
            btn, self.player_object.playing_track
        )

    @Gtk.Template.Callback("on_shuffle_button_toggled")
    def on_shuffle_button_toggled(self, btn):
        self.player_object.shuffle = btn.get_active()

    @Gtk.Template.Callback("on_volume_changed")
    def on_volume_changed_func(self, widget, value):
        self.player_object.change_volume(value)
        self.settings.set_int("last-volume", int(value * 10))

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

        if end_value == 0:
            return

        position = time_ms / 1000

        self.player_object.seek(position / end_value)

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
        """Update the progress bar and playback information.

        Called periodically to update the progress bar, song duration, current position
        and volume level.
        """
        # Just copy the duration from player here to avoid ui desync from player object
        self.duration = self.player_object.duration
        end_value = self.duration / Gst.SECOND

        self.volume_button.get_adjustment().set_value(self.player_object.query_volume())
        position = self.player_object.query_position(default=None)
        if position is None:
            return
        position = position / Gst.SECOND
        fraction = 0

        self.lyrics_widget.set_time(position)

        self.duration_label.set_label(utils.pretty_duration(end_value))

        if end_value != 0:
            fraction = position / end_value
        self.small_progress_bar.set_fraction(fraction)
        self.progress_bar.get_adjustment().set_value(fraction)

        self.previous_fraction = fraction

        self.time_played_label.set_label(utils.pretty_duration(position))

    def th_add_lyrics_to_page(self):
        try:
            lyrics = self.player_object.playing_track.lyrics()
            if lyrics:
                if lyrics.subtitles:
                    GLib.idle_add(self.lyrics_widget.set_lyrics, lyrics.subtitles)
                elif lyrics.text:
                    GLib.idle_add(self.lyrics_widget.set_lyrics, lyrics.text)
            else:
                self.lyrics_widget.clear()
        except Exception:
            self.lyrics_widget.clear()

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

    def change_alsa_device(self, device: str):
        if self.settings.get_string("alsa-device") != device:
            self.settings.set_string("alsa-device", device)
            self.player_object.alsa_device = device
            self.player_object.change_audio_sink(
                self.settings.get_int("preferred-sink")
            )

    def change_normalization(self, state):
        if self.player_object.normalize != state:
            self.player_object.normalize = state
            self.settings.set_boolean("normalize", state)
            # recreate audio pipeline, kinda dirty ngl
            self.player_object.change_audio_sink(
                self.settings.get_int("preferred-sink")
            )

    def change_quadratic_volume(self, state):
        if self.settings.get_boolean("quadratic-volume") != state:
            self.player_object.quadratic_volume = state
            self.settings.set_boolean("quadratic-volume", state)

    def change_video_covers_enabled(self, state):
        if self.settings.get_boolean("video-covers") != state:
            self.video_covers_enabled = state
            self.settings.set_boolean("video-covers", state)

            album = self.player_object.song_album
            if not album:
                return

            self.videoplayer.pause()
            self.videoplayer.clear()

            if self.video_covers_enabled and album.video_cover:
                threading.Thread(
                    target=utils.add_video_cover,
                    args=(
                        self.playing_track_picture,
                        self.videoplayer,
                        album,
                        self.image_canc,
                    ),
                ).start()
            else:
                threading.Thread(
                    target=utils.add_picture,
                    args=(self.playing_track_picture, album, self.image_canc),
                ).start()

    def change_discord_rpc_enabled(self, state):
        if self.settings.get_boolean("discord-rpc") != state:
            self.settings.set_boolean("discord-rpc", state)
            self.player_object.set_discord_rpc(state)

    #
    #   PAGES ACTIONS CALLBACKS
    #

    def on_push_artist_page(self, action, parameter):
        if parameter.get_string() == "":
            return
        page = HTArtistPage.new_from_id(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_album_page(self, action, parameter):
        if parameter.get_string() == "":
            return
        page = HTAlbumPage.new_from_id(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_playlist_page(self, action, parameter):
        if parameter.get_string() == "":
            return
        page = HTPlaylistPage.new_from_id(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_mix_page(self, action, parameter):
        if parameter.get_string() == "":
            return
        page = HTMixPage.new_from_id(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_track_radio_page(self, action, parameter):
        if parameter.get_string() == "":
            return
        page = HTMixPage.new_from_track(parameter.get_string()).load()
        self.navigation_view.push(page)

    def on_push_artist_radio_page(self, action, parameter):
        if parameter.get_string() == "":
            return
        page = HTMixPage.new_from_artist(parameter.get_string()).load()
        self.navigation_view.push(page)

    #
    #
    #

    def create_action_with_target(
        self, name: str, target_type: GLib.VariantType, callback: Callable
    ):
        """Create a new GAction with a target parameter.

        Args:
            name (str): The action name
            target_type: The GVariant type for the target parameter
            callback: The callback function to execute when action is triggered
        """

        action = Gio.SimpleAction.new(name, target_type)
        action.connect("activate", callback)
        self.add_action(action)
        return action
