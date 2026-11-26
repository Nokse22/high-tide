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

import html
import threading
from concurrent.futures import ThreadPoolExecutor
from gettext import gettext as _
from pathlib import Path
from typing import Callable

import tidalapi
from gi.repository import Adw, Gio, GLib, GObject, Gst, Gtk, Pango, Xdp, Gdk
from tidalapi.media import Quality
from tidalapi.mix import MixV2

from .lib import (HTCache, LastFmClient, LastFmScrobbler, LastFmSecretStore,
                  ListenBrainzClient, ListenBrainzScrobbler,
                  ListenBrainzSecretStore, PlayerObject, RepeatType, SecretStore,
                  ai, utils)
from .lib import cast, dlna
from .lib.play_reporter import PlayReporter
from .lib.player_object import AudioSink
from .widgets.track_menu import TrackMenu
from .login import LoginDialog
from .mpris import MPRIS
from .pages import (HTAlbumPage, HTArtistPage, HTCollectionPage, HTCreditsPage,
                    HTExplorePage, HTFromFunctionPage, HTGenericPage, HTMixPage,
                    HTNotLoggedInPage, HTPlaylistPage)
from .widgets import (HTGenericTrackWidget, HTLinkLabelWidget, HTLyricsWidget,
                      HTQueueWidget)

import logging
logger = logging.getLogger(__name__)

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
    miniplayer_title_label = Gtk.Template.Child()
    sidebar_title_label = Gtk.Template.Child()
    playing_track_picture = Gtk.Template.Child()
    playing_track_image = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    miniplayer_artist_label = Gtk.Template.Child()
    volume_button = Gtk.Template.Child()
    output_button = Gtk.Template.Child()
    output_popover = Gtk.Template.Child()
    output_list = Gtk.Template.Child()
    output_searching_box = Gtk.Template.Child()
    in_my_collection_button = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()
    ai_label = Gtk.Template.Child()
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
    multilayout_view = Gtk.Template.Child()
    queue_split_view = Gtk.Template.Child()
    queue_panel_box = Gtk.Template.Child()
    queue_tab_box = Gtk.Template.Child()
    queue_page = Gtk.Template.Child()
    queue_button = Gtk.Template.Child()
    go_next_button = Gtk.Template.Child()
    go_prev_button = Gtk.Template.Child()
    track_radio_button = Gtk.Template.Child()
    block_button = Gtk.Template.Child()
    block_menu = Gtk.Template.Child()
    more_button = Gtk.Template.Child()
    playing_from_button = Gtk.Template.Child()
    playing_from_icon = Gtk.Template.Child()
    playing_from_label = Gtk.Template.Child()

    secret_portal_dialog = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Own copies of icons the icon theme only has in colour (Oxygen)
        utils.fix_theme_icons(self)

        self.settings = Gio.Settings.new("io.github.nokse22.high-tide")

        ai.set_hidden(self.settings.get_boolean("hide-ai-music"))
        self.settings.connect(
            "changed::hide-ai-music", self.on_hide_ai_music_changed
        )

        # Saved once a resize stops, not at every step of it: each save rewrites
        # the settings file, which can take a tenth of a second
        self.set_default_size(
            self.settings.get_int("window-width"),
            self.settings.get_int("window-height"),
        )
        self._window_size_timer: int | None = None
        self.connect("notify::default-width", self._on_window_resized)
        self.connect("notify::default-height", self._on_window_resized)
        self.connect("close-request", lambda *_: self.save_window_size() or False)
        # Quitting from the menu or with Ctrl+Q doesn't close the window first
        Gio.Application.get_default().connect(
            "shutdown", lambda *_: self.save_window_size()
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
            "push-folder-page", GLib.VariantType.new("s"), self.on_push_folder_page
        )

        self.create_action_with_target(
            "push-mix-page", GLib.VariantType.new("s"), self.on_push_mix_page
        )

        customize_home_action = Gio.SimpleAction.new("customize-home", None)
        customize_home_action.connect("activate", self.on_customize_home)
        self.add_action(customize_home_action)

        my_tracks_action = Gio.SimpleAction.new("push-my-tracks-page", None)
        my_tracks_action.connect("activate", self.on_push_my_tracks_page)
        self.add_action(my_tracks_action)

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

        self.create_action_with_target(
            "push-track-credits-page",
            GLib.VariantType.new("s"),
            self.on_push_track_credits_page,
        )

        self.create_action_with_target(
            "push-album-info-page",
            GLib.VariantType.new("s"),
            self.on_push_album_info_page,
        )
        
        self.create_action_with_target(
            "toggle-block-artist",
            GLib.VariantType.new("n"),
            self.on_toggle_block_playing_artist,
        )

        toggle_block_track_action = Gio.SimpleAction.new("toggle-block-track", None)
        toggle_block_track_action.connect("activate", self.on_toggle_block_playing_track)
        self.add_action(toggle_block_track_action)

        self.block_button.connect("notify::active", self.on_block_button_active)
        # Block artist opens beside the menu on hover, like the song menu's
        self.block_button.get_popover().set_flags(Gtk.PopoverMenuFlags.NESTED)

        # self.create_action_with_target(
        #     'play-next',
        #     GLib.VariantType.new("s"),
        #     self.on_play_next)

        if self.settings.get_int("preferred-sink") not in list(AudioSink):
            # An output that isn't offered anymore
            self.settings.set_int("preferred-sink", AudioSink.AUTO)

        self.player_object = PlayerObject(
            self.settings.get_int("preferred-sink"),
            self.settings.get_string("alsa-device"),
            self.settings.get_boolean("normalize"),
            self.settings.get_boolean("quadratic-volume"),
            self.settings.get_int("output-rate"),
            self.settings.get_string("jack-connect"),
        )
        utils.player_object = self.player_object

        utils.prefer_clean_versions = self.settings.get_boolean("prefer-clean-versions")
        self.settings.connect(
            "changed::prefer-clean-versions",
            lambda settings, key: setattr(
                utils, "prefer_clean_versions", settings.get_boolean(key)
            ),
        )
        self.player_object.set_discord_rpc(self.settings.get_boolean("discord-rpc"))
        self.lastfm_client = LastFmClient(LastFmSecretStore())
        self.lastfm_scrobbler = LastFmScrobbler(
            self.player_object, self.lastfm_client
        )
        self.listenbrainz_client = ListenBrainzClient(
            ListenBrainzSecretStore(), self.get_application().get_version() or ""
        )
        self.listenbrainz_scrobbler = ListenBrainzScrobbler(
            self.player_object, self.listenbrainz_client
        )

        if self.settings.get_user_value("volume") is None:
            # Saved in tenths by older versions
            volume = self.settings.get_int("last-volume") / 10
        else:
            volume = self.settings.get_double("volume")
        self._volume_from_player = False
        # See _save_volume
        self._volume_to_save: float | None = None
        self._volume_save_timer: int | None = None
        self.volume_button.get_adjustment().set_value(volume)
        self._setup_volume_button()
        self._setup_tab_shortcuts()
        # The slider shows the volume in use: this app's, or the device's while
        # playing on one; also when it's changed from elsewhere (media keys, the device)
        self.player_object.connect("volume-changed", self.on_player_volume_changed)
        self.player_object.bind_property(
            "volume-available",
            self.volume_button,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.player_object.connect("notify::shuffle", self.on_shuffle_changed)
        self.player_object.connect("update-slider", self.update_slider)
        self.player_object.connect("song-changed", self.on_song_changed)
        self.player_object.connect("renderer-changed", self.on_renderer_changed)
        self.player_object.connect("song-added-to-queue", self.on_song_added_to_queue)
        self.player_object.connect("next-songs-changed", self.on_next_songs_changed)
        self.settings.bind(
            "autoplay", self.player_object, "autoplay", Gio.SettingsBindFlags.DEFAULT
        )
        self.player_object.connect("notify::playing", self.update_controls)

        self.suspend_inhibit_cookie: int = 0
        self.player_object.connect(
            "notify::playing", lambda *_: self.update_suspend_inhibitor()
        )
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

        self.artist_label.connect("activate-link", utils.open_uri)
        self.miniplayer_artist_label.connect("activate-link", utils.open_uri)
        self.title_labels = (
            self.song_title_label,
            self.miniplayer_title_label,
            self.sidebar_title_label,
        )
        for label in self.title_labels:
            label.connect("activate-link", utils.open_uri)

        self.session = utils.create_tidal_session()

        utils.session = self.session
        utils.navigation_view = self.navigation_view
        utils.toast_overlay = self.toast_overlay
        utils.cache = HTCache(self.session)

        self.user = self.session.user

        self.play_reporter = PlayReporter(
            self.player_object,
            self.session,
            self.get_application().get_version() or "",
            Path(utils.CACHE_DIR, "plays-to-report.json"),
        )

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
        # Album whose moving cover waits for the window to be in front again
        self.video_cover_pending = None

        self.queue_widget_updated = False

        # The queue is a panel on the right on desktop, a tab in the phone layout
        self.settings.bind(
            "queue-panel-open",
            self.queue_split_view,
            "show-sidebar",
            Gio.SettingsBindFlags.DEFAULT,
        )
        self.multilayout_view.connect("notify::layout-name", self._place_queue)
        self._place_queue()

        try:
            self.secret_store = SecretStore(self.session)
            threading.Thread(target=self.th_login, args=()).start()
        except Exception:
            self.secret_portal_dialog.present(self)
            return

        MPRIS(self.player_object, self)

        self.portal = Xdp.Portal()
        self.portal.set_background_status(_("Playing Music"))

        self.connect("notify::is-active", self.stop_video_in_background)

        threading.Thread(target=utils.evict_cache, args=(utils.MUSIC_DIR, 5)).start()

    @Gtk.Template.Callback("copy_secret_service_override_command")
    def copy_secret_service_override_command (self, *args):
        clipboard = Gdk.Display().get_default().get_clipboard()
        clipboard.set("flatpak --user override --talk-name=org.freedesktop.secrets io.github.nokse22.high-tide")

    @Gtk.Template.Callback("secret_portal_dialog_response_cb")
    def secret_portal_dialog_response_cb(self, *args):
        self.get_application().quit()

    #
    #   LOGIN
    #

    def new_login(self):
        """Open a new login dialog for user authentication"""

        login_dialog = LoginDialog(self, self.session)
        login_dialog.present(self)

    def th_login(self):
        if not self.secret_store.token_dictionary:
            GLib.idle_add(self.on_login_failed)
            return

        # A browser login (PKCE) or a QR code one (TIDAL's device login), whose
        # songs come from another address (utils.get_stream)
        is_pkce = bool(self.secret_store.token_dictionary.get("is-pkce", False))
        utils.device_login = not is_pkce
        try:
            self.session.load_oauth_session(
                self.secret_store.token_dictionary["token-type"],
                self.secret_store.token_dictionary["access-token"],
                self.secret_store.token_dictionary["refresh-token"],
                self.secret_store.token_dictionary["expiry-time"],
                is_pkce=is_pkce,
            )
        except Exception:
            logger.exception("Error while logging in!")
            GLib.idle_add(self.on_login_failed)
        else:
            GLib.idle_add(self.on_logged_in)

    def logout(self):
        """Log out the current user and return to login screen.

        Clears stored authentication tokens and navigates back to the
        not logged in page.
        """
        self.secret_store.clear()
        utils.device_login = False

        page = HTNotLoggedInPage().load()
        self.navigation_view.replace([page])

    def on_logged_in(self):
        """Handle successful user login"""
        logger.info("logged in")

        # Read before Home is shown, which counts as using Home
        last_tab = self.settings.get_string("last-tab")
        page = HTGenericPage.new_from_function(utils.session.home)
        page.hideable = True
        page.load()
        page.set_tag("home")
        self.navigation_view.replace([page])

        self.player_lyrics_queue.set_sensitive(True)
        self.navigation_buttons.set_sensitive(True)

        # The home page doesn't need the favourites, so they load next to it.
        # Pages that show hearts wait for them (waits_for_favourites).
        utils.favourites_loaded.clear()
        threading.Thread(target=self.th_load_favourites, args=()).start()
        threading.Thread(target=self.th_set_last_playing_song, args=()).start()
        threading.Thread(target=utils.get_blocked, args=()).start()

        self.is_logged_in = True

        # Open on the tab used last, with Home under it for Back (#148)
        # (the page gets its tag only once loaded, so the button is set here)
        if last_tab == "explore":
            self.navigation_view.push(HTExplorePage().load())
            self.explore_button.set_active(True)
        elif last_tab == "collection":
            # The favourites are loading already
            self.navigation_view.push(HTCollectionPage().load())
            self.collection_button.set_active(True)
        # Showing Home above saved "home"
        self.settings.set_string("last-tab", last_tab)

        if self.queued_uri:
            utils.open_tidal_uri(self.queued_uri)

    def on_login_failed(self):
        """Handle failed login attempts"""
        logger.error("login failed")

        page = HTNotLoggedInPage().load()
        self.navigation_view.replace([page])

    def th_load_favourites(self):
        utils.get_favourites()
        GLib.idle_add(self.update_in_my_collection_button)

    def update_in_my_collection_button(self):
        track = self.player_object.playing_track
        if track is None:
            return

        utils.set_in_my_collection_button(
            self.in_my_collection_button, utils.is_favourited(track)
        )

    def th_set_last_playing_song(self):
        index = self.settings.get_int("last-playing-index")
        thing_id = self.settings.get_string("last-playing-thing-id")
        thing_type = self.settings.get_string("last-playing-thing-type")
        track_id = self.settings.get_string("last-playing-track-id")

        logger.info(
            f"Last playing: {thing_id} of type {thing_type} index: {index} track: {track_id}"
        )

        tracks = None
        source = None

        try:
            if thing_type == "mix":
                source = self.session.mix(thing_id)
                tracks = source.items()
            elif thing_type == "album":
                source = self.session.album(thing_id)
                tracks = source.tracks()
            elif thing_type == "playlist":
                source = self.session.playlist(thing_id)
                tracks = source.tracks()
            elif thing_type == "artist":
                source = self.session.artist(thing_id)
                tracks = source.get_top_tracks(limit=50)
            elif thing_type == "my-tracks":
                source = utils.MY_TRACKS
                utils.favourites_loaded.wait(15)
                tracks = list(utils.favourite_tracks)
            elif thing_type == "track":
                tracks = [self.session.track(thing_id)]
        except Exception:
            logger.exception("Error while setting last played song")

        if not tracks:
            return

        # Find the song itself: the list may be in another order or have changed
        # (saved tracks), and older versions saved only the position
        for position, track in enumerate(tracks):
            if track_id and str(track.id) == track_id:
                index = position
                break
        index = min(max(index, 0), len(tracks) - 1)

        shuffle = self.settings.get_boolean("shuffle")
        shuffle_order = self.settings.get_strv("last-playing-shuffle-order")

        def restore():
            # Shuffle first, so the other songs are the shuffled ones (#255)
            self.player_object.shuffle = shuffle
            # The source too, so the player shows what it's playing from
            self.player_object.play_this(tracks, index, source=source)
            if shuffle:
                self.player_object.restore_shuffled_order(shuffle_order)
            return False

        GLib.idle_add(restore)
        GLib.idle_add(self.player_object.pause)

    #
    #   UPDATES UI
    #

    def on_song_changed(self, *args):
        """Handle song change events from the player.

        Updates the UI elements when the currently playing song changes,
        including album art, track information, and video covers.
        """
        logger.info("song changed")
        album = self.player_object.song_album
        track = self.player_object.playing_track

        if track is None:
            return

        track_name = track.full_name if hasattr(track, "full_name") else track.name
        # The title links to its album, like the artists to theirs
        if album:
            markup = f"<a href='album:{album.id}'>{html.escape(track_name)}</a>"
        else:
            markup = html.escape(track_name)
        for label in self.title_labels:
            label.set_markup(markup)
            label.set_tooltip_text(track_name)
        self.artist_label.set_artists(track.artists)
        self.explicit_label.set_visible(track.explicit)
        self.ai_label.set_visible(ai.is_ai(track))

        self.set_quality_label()

        self.track_radio_button.set_action_target_value(
            GLib.Variant("s", str(track.id))
        )
        self.block_button.set_sensitive(True)
        self._set_more_menu(track)
        self._update_playing_from()

        self.update_in_my_collection_button()

        self.save_last_playing_thing()

        if self.image_canc:
            self.image_canc.cancel()
        self.image_canc = Gio.Cancellable.new()

        # Remove old video cover should maybe be threaded
        if self.video_covers_enabled:
            self.videoplayer.pause()
            self.videoplayer.clear()

        dimensions = utils.get_best_dimensions(self.playing_track_picture)

        self.video_cover_pending = None
        if self.video_covers_enabled and album.video_cover and not self.in_background:
            self._load_video_cover(album)
        else:
            if self.video_covers_enabled and album.video_cover:
                # Loading a video makes GTK decode it on the graphics card even
                # while paused, so the moving cover waits until the window is in
                # front again and the still cover is shown meanwhile
                self.video_cover_pending = album
            threading.Thread(
                target=utils.add_picture,
                args=(self.playing_track_picture, album, dimensions, self.image_canc),
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
        """Save what's playing so the app can continue it after a restart.

        Saves what the song is played from (an album, playlist, mix, artist or
        the saved tracks) and the song itself; a song played on its own or from
        search results is saved alone. A song from the queue isn't saved, so the
        list it interrupted continues.
        """
        player = self.player_object
        track = player.playing_track
        if track is None or player.playing_from_queue:
            return

        source = player.play_source
        if source is utils.MY_TRACKS:
            thing_type, thing_id = "my-tracks", ""
        elif isinstance(source, (tidalapi.Album, tidalapi.Playlist, tidalapi.Mix,
                                 MixV2, tidalapi.Artist)):
            kind = "mix" if isinstance(source, MixV2) else utils.get_type(source)
            thing_type, thing_id = kind, str(source.id)
        else:
            # Can't be fetched again (search results, a single song): the song alone
            thing_type, thing_id = "track", str(track.id)

        self.settings.set_string("last-playing-thing-type", thing_type)
        self.settings.set_string("last-playing-thing-id", thing_id)
        self.settings.set_string("last-playing-track-id", str(track.id))
        self.settings.set_int("last-playing-index", player.get_index())
        # The shuffled order too, so it continues the same after a restart (#255)
        order = [str(t.id) for t in player.tracks_to_play] if player.shuffle else []
        self.settings.set_strv("last-playing-shuffle-order", order)

    def _load_video_cover(self, album) -> None:
        threading.Thread(
            target=utils.add_video_cover,
            args=(
                self.playing_track_picture,
                self.videoplayer,
                album,
                utils.get_best_dimensions(self.playing_track_picture),
                self.in_background,
                self.image_canc,
            ),
        ).start()

    def stop_video_in_background(self, window, param):
        self.in_background = not self.is_active()
        album = self.player_object.song_album
        if self.video_cover_pending is not None and not self.in_background:
            pending = self.video_cover_pending
            self.video_cover_pending = None
            if self.video_covers_enabled and pending is album:
                # The still cover may still be loading: it mustn't replace the video
                self.image_canc.cancel()
                self.image_canc = Gio.Cancellable.new()
                self._load_video_cover(album)
            return
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
        if not stream and not self.player_object.manifest:
            # Played from the music cache without TIDAL (e.g. offline)
            self.quality_label.set_visible(False)
            return
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

    def update_suspend_inhibitor(self, *args):
        """Inhibit system suspend while a track is playing"""
        application = self.get_application()
        if not application:
            return

        if self.player_object.playing:
            if not self.suspend_inhibit_cookie:
                self.suspend_inhibit_cookie = application.inhibit(
                    self,
                    Gtk.ApplicationInhibitFlags.SUSPEND,
                    _("Playback of music is in progress"),
                )
                if self.suspend_inhibit_cookie:
                    logger.debug(
                        "Acquired suspend inhibitor (cookie %d)",
                        self.suspend_inhibit_cookie,
                    )
        elif self.suspend_inhibit_cookie:
            application.uninhibit(self.suspend_inhibit_cookie)
            logger.debug("Released suspend inhibitor")
            self.suspend_inhibit_cookie = 0

    def update_repeat_button(self, player, repeat_type):
        """Update the repeat button icon and tooltip based on current repeat mode.
        It's lit like the shuffle button while repeat is on."""
        if player.repeat_type == RepeatType.SONG:
            self.repeat_button.set_icon_name("playlist-repeat-one-symbolic")
            self.repeat_button.set_tooltip_text(_("Repeat One"))
        else:
            self.repeat_button.set_icon_name("playlist-repeat-symbolic")
            if player.repeat_type == RepeatType.LIST:
                self.repeat_button.set_tooltip_text(_("Repeat All"))
            else:
                self.repeat_button.set_tooltip_text(_("Repeat Off"))
        # A click toggles the button by itself: it follows the mode instead
        self.repeat_button.set_active(player.repeat_type != RepeatType.NONE)

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

    def _update_playing_from(self) -> None:
        """Show what the playing track is played from (an album, playlist, mix or
        artist), as TIDAL does; clicking it opens that page"""
        source = self.player_object.get_playing_source()
        kinds = (
            (tidalapi.Album, "album", "library-music-symbolic", "name"),
            (tidalapi.Playlist, "playlist", "view-list-bullet-symbolic", "name"),
            ((tidalapi.Mix, MixV2), "mix", "audio-x-generic-symbolic", "title"),
            (tidalapi.Artist, "artist", "music-artist-symbolic", "name"),
        )
        if source is utils.MY_TRACKS:
            name = source.name
            self.playing_from_icon.set_from_icon_name("heart-filled-symbolic")
            self.playing_from_label.set_label(name)
            self.playing_from_button.set_tooltip_text(
                _("Playing from: {}").format(name)
            )
            self.playing_from_button.set_action_name("win.push-my-tracks-page")
            self.playing_from_button.set_action_target_value(None)
            self.playing_from_button.set_visible(True)
            return
        for cls, kind, icon, name_attr in kinds:
            if isinstance(source, cls):
                name = getattr(source, name_attr, None) or ""
                self.playing_from_icon.set_from_icon_name(icon)
                self.playing_from_label.set_label(name)
                self.playing_from_button.set_tooltip_text(
                    _("Playing from: {}").format(name)
                )
                self.playing_from_button.set_action_name(f"win.push-{kind}-page")
                self.playing_from_button.set_action_target_value(
                    GLib.Variant("s", str(source.id))
                )
                self.playing_from_button.set_visible(True)
                return
        # A track played on its own or from the queue
        self.playing_from_button.set_visible(False)

    def _set_more_menu(self, track) -> None:
        """Give the More button the song menu of the playing track, as on song rows
        (add to a playlist, play next, credits, copy share url, block...)"""
        for obj, handler in getattr(self, "_more_menu_signals", []):
            if obj.handler_is_connected(handler):
                obj.disconnect(handler)
        self._more_menu_signals = []
        self._more_menu = TrackMenu(
            self.more_button, self.more_button, track, self._more_menu_signals
        )
        self.more_button.set_sensitive(True)

    @Gtk.Template.Callback("on_skip_forward_button_clicked")
    def on_skip_forward_button_clicked_func(self, widget):
        self.player_object.play_next(skip=True)

    @Gtk.Template.Callback("on_skip_backward_button_clicked")
    def on_skip_backward_button_clicked_func(self, widget):
        self.player_object.play_previous()

    @Gtk.Template.Callback("on_home_button_clicked")
    def on_home_button_clicked_func(self, widget):
        self.navigation_view.pop_to_tag("home")

    @Gtk.Template.Callback("on_explore_button_clicked")
    def on_explore_button_clicked_func(self, widget):
        # Saved here: a new page gets its tag only once it's loaded
        self.settings.set_string("last-tab", "explore")
        if self.navigation_view.find_page("explore"):
            self.navigation_view.pop_to_tag("explore")
            return

        page = HTExplorePage().load()
        self.navigation_view.push(page)

    @Gtk.Template.Callback("on_collection_button_clicked")
    def on_collection_button_clicked_func(self, widget):
        self.settings.set_string("last-tab", "collection")
        utils.refresh_favourites()
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

    def on_block_button_active(self, btn, *args):
        track = self.player_object.playing_track
        if btn.get_active() and track is not None:
            utils.fill_block_menu(self.block_menu, track, "win")

    def on_toggle_block_playing_track(self, *args):
        if self.player_object.playing_track:
            utils.toggle_blocked(self.player_object.playing_track)

    def on_toggle_block_playing_artist(self, action, parameter):
        if self.player_object.playing_track:
            artists = utils.get_track_artists(self.player_object.playing_track)
            utils.toggle_blocked(artists[parameter.get_int16()])

    @Gtk.Template.Callback("on_shuffle_button_toggled")
    def on_shuffle_button_toggled(self, btn):
        self.player_object.shuffle = btn.get_active()

    @Gtk.Template.Callback("on_volume_changed")
    def on_volume_changed_func(self, widget, value):
        if self._volume_from_player:
            return
        # Saved by on_player_volume_changed, which change_volume calls
        self.player_object.change_volume(value)

    def on_player_volume_changed(self, player, value):
        if not player.renderer:
            # The device's own volume isn't this app's
            self._save_volume(value)
        self._show_volume(value)

    def _save_volume(self, value: float) -> None:
        """Save the volume once it stops changing. Each save rewrites the
        settings file, which can take a tenth of a second, and dragging the
        slider changes the volume dozens of times a second."""
        self._volume_to_save = value
        if self._volume_save_timer is not None:
            GLib.source_remove(self._volume_save_timer)
        self._volume_save_timer = GLib.timeout_add(500, self._on_volume_save_timer)

    def _on_volume_save_timer(self) -> bool:
        self._volume_save_timer = None
        self.save_pending_volume()
        return False

    def save_pending_volume(self) -> None:
        """Save a volume change still waiting in _save_volume"""
        if self._volume_save_timer is not None:
            GLib.source_remove(self._volume_save_timer)
            self._volume_save_timer = None
        if self._volume_to_save is not None:
            self.settings.set_double("volume", self._volume_to_save)
            self._volume_to_save = None

    def _show_volume(self, value):
        """Move the slider without sending the value back to the player.
        Returns whether it moved."""
        adjustment = self.volume_button.get_adjustment()
        if abs(adjustment.get_value() - value) < 0.005:
            return False
        self._volume_from_player = True
        try:
            adjustment.set_value(value)
        finally:
            self._volume_from_player = False
        return True

    def _on_window_resized(self, *_args) -> None:
        if self._window_size_timer is not None:
            GLib.source_remove(self._window_size_timer)
        self._window_size_timer = GLib.timeout_add(500, self._on_window_size_timer)

    def _on_window_size_timer(self) -> bool:
        self._window_size_timer = None
        self.save_window_size()
        return False

    def save_window_size(self) -> None:
        if self._window_size_timer is not None:
            GLib.source_remove(self._window_size_timer)
            self._window_size_timer = None
        width, height = self.get_default_size()
        if width > 0 and height > 0:
            if self.settings.get_int("window-width") != width:
                self.settings.set_int("window-width", width)
            if self.settings.get_int("window-height") != height:
                self.settings.set_int("window-height", height)

    def _setup_tab_shortcuts(self) -> None:
        """Alt+1, Alt+2 and Alt+3 open Home, Explore and Collection (#189)"""
        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
        for number, button in enumerate(
            (self.home_button, self.explore_button, self.collection_button), 1
        ):

            def open_tab(_widget, _args, button=button):
                if not self.is_logged_in:
                    return False
                button.emit("clicked")
                return True

            shortcuts.add_shortcut(
                Gtk.Shortcut.new(
                    Gtk.ShortcutTrigger.parse_string(f"<Alt>{number}"),
                    Gtk.CallbackAction.new(open_tab),
                )
            )
        self.add_controller(shortcuts)

    def _setup_volume_button(self) -> None:
        """Let the volume slider move in 1% steps (GTK rounds it to tenths), open it
        when the pointer rests on its button for a moment, as tidal.com does, and
        close it shortly after the pointer leaves the button and slider"""
        widgets = [self.volume_button.get_popup()]
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, Gtk.Scale):
                widget.set_round_digits(2)
                break
            child = widget.get_first_child()
            while child:
                widgets.append(child)
                child = child.get_next_sibling()

        self._volume_open_id = 0
        self._volume_close_id = 0
        self._volume_motions = []
        for widget in (self.volume_button, self.volume_button.get_popup()):
            motion = Gtk.EventControllerMotion()
            motion.connect("enter", self._on_volume_pointer_enter)
            motion.connect("leave", self._on_volume_pointer_leave)
            widget.add_controller(motion)
            self._volume_motions.append(motion)

    @staticmethod
    def _from_touch(motion) -> bool:
        device = motion.get_current_event_device()
        return bool(device) and device.get_source() == Gdk.InputSource.TOUCHSCREEN

    def _on_volume_pointer_enter(self, motion, x, y) -> None:
        if self._from_touch(motion):
            return
        if self._volume_close_id:
            GLib.source_remove(self._volume_close_id)
            self._volume_close_id = 0
        popup_open = self.volume_button.get_popup().get_visible()
        if not popup_open and not self._volume_open_id:
            # a short wait, so passing over the button on the way elsewhere
            # doesn't open it
            self._volume_open_id = GLib.timeout_add(250, self._open_volume_popup)

    def _on_volume_pointer_leave(self, motion) -> None:
        if self._from_touch(motion):
            return
        if self._volume_open_id:
            GLib.source_remove(self._volume_open_id)
            self._volume_open_id = 0
        if self._volume_close_id:
            return
        self._volume_close_id = GLib.timeout_add(300, self._close_volume_popup)

    def _open_volume_popup(self) -> bool:
        self._volume_open_id = 0
        if self._volume_motions[0].contains_pointer():
            self.volume_button.emit("popup")
        return False

    def _close_volume_popup(self) -> bool:
        self._volume_close_id = 0
        if not any(motion.contains_pointer() for motion in self._volume_motions):
            self.volume_button.emit("popdown")
        return False

    @Gtk.Template.Callback("on_output_popover_shown")
    def on_output_popover_shown(self, *args):
        """Look for DLNA devices each time the list is opened"""
        if getattr(self, "_searching_outputs", False):
            return
        self._searching_outputs = True
        self.output_searching_box.set_visible(True)
        self._fill_output_list(getattr(self, "_found_renderers", []))

        def search():
            with ThreadPoolExecutor(max_workers=2) as pool:
                found = [pool.submit(dlna.discover), pool.submit(cast.discover)]
                renderers = []
                for future in found:
                    try:
                        renderers += future.result()
                    except Exception:
                        logger.exception("Couldn't search for devices")
            renderers.sort(key=lambda r: r.name.lower())
            GLib.idle_add(self._on_outputs_found, renderers)

        threading.Thread(target=search, daemon=True).start()

    def _on_outputs_found(self, renderers):
        self._searching_outputs = False
        self._found_renderers = renderers
        self.output_searching_box.set_visible(False)
        self._fill_output_list(renderers)
        return False

    def _fill_output_list(self, renderers):
        current = self.player_object.renderer
        if current and all(r != current for r in renderers):
            # Still playing on it, even if it didn't answer this time
            renderers = [current, *renderers]
        self.output_list.remove_all()
        for renderer in [None, *renderers]:
            box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6)
            box.append(
                Gtk.Image(
                    icon_name="audio-speakers-symbolic" if renderer else "computer-symbolic"
                )
            )
            box.append(
                Gtk.Label(
                    label=renderer.name if renderer else _("This Computer"),
                    xalign=0,
                    hexpand=True,
                    ellipsize=Pango.EllipsizeMode.END,
                )
            )
            check = Gtk.Image(icon_name="object-select-symbolic")
            check.set_visible(renderer == current)
            box.append(check)
            row = Gtk.ListBoxRow(child=box)
            row.renderer = renderer
            self.output_list.append(row)

    @Gtk.Template.Callback("on_output_row_activated")
    def on_output_row_activated(self, _list, row):
        self.output_popover.popdown()
        self.player_object.set_renderer(row.renderer)

    def on_renderer_changed(self, *args):
        renderer = self.player_object.renderer
        if renderer:
            self.output_button.add_css_class("accent")
            self.output_button.set_tooltip_text(_("Playing on {}").format(renderer.name))
        else:
            self.output_button.remove_css_class("accent")
            self.output_button.set_tooltip_text(_("Play On"))

    @Gtk.Template.Callback("on_slider_seek")
    def on_slider_seek(self, *args):
        seek_fraction = self.progress_bar.get_value()

        if abs(seek_fraction - self.previous_fraction) == 0.0:
            return

        logger.info(f"seeking: {abs(seek_fraction - self.previous_fraction)}")

        self.player_object.seek(seek_fraction)

        duration_secs = self.duration / Gst.SECOND
        position_secs = seek_fraction * duration_secs
        self.time_played_label.set_label(utils.pretty_duration(position_secs))
        self.lyrics_widget.set_time(position_secs)
        self.small_progress_bar.set_fraction(seek_fraction)
        self.previous_fraction = seek_fraction

    @Gtk.Template.Callback("on_seek_from_lyrics")
    def on_seek_from_lyrics(self, lyrics_widget, time_ms):
        end_value = self.duration / Gst.SECOND

        if end_value == 0:
            return

        position = time_ms / 1000

        self.player_object.seek(position / end_value)

    def on_next_songs_changed(self, *args):
        if self.queue_widget.get_mapped():
            self.queue_widget.update_next_songs(self.player_object)
        else:
            self.queue_widget_updated = False

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
        self.queue_widget.scroll_to_playing()

    @Gtk.Template.Callback("on_navigation_view_page_popped")
    def on_navigation_view_page_popped_func(self, nav_view, nav_page):
        nav_page.disconnect_all()

    @Gtk.Template.Callback("on_visible_page_changed")
    def on_visible_page_changed(self, nav_view, *args):
        tag = self.navigation_view.get_visible_page().get_tag()
        match tag:
            case "home":
                self.home_button.set_active(True)
            case "explore":
                self.explore_button.set_active(True)
            case "collection":
                self.collection_button.set_active(True)
        if tag in ("home", "explore", "collection"):
            # Opened again at the next start (also when Back leads to it)
            self.settings.set_string("last-tab", tag)

    def _place_queue(self, *args) -> None:
        """Put the queue in the right-side panel on desktop, and in the Queue tab
        in the phone layout"""
        desktop = self.multilayout_view.get_layout_name() == "desktop"
        target = self.queue_panel_box if desktop else self.queue_tab_box
        if self.queue_widget.get_parent() is not target:
            self.queue_widget.get_parent().remove(self.queue_widget)
            target.append(self.queue_widget)
            # A new parent only adds its state: the queue would stay greyed out
            # and unclickable from the player panel, which is off until login.
            # Turning it off and on takes its state from the new parent again.
            self.queue_widget.set_sensitive(False)
            self.queue_widget.set_sensitive(True)
        self.queue_widget.set_drag_whole_rows(desktop)
        self.queue_page.set_visible(not desktop)
        self.queue_button.set_visible(desktop)
        if desktop and self.sidebar_stack.get_visible_child_name() == "queue":
            self.sidebar_stack.set_visible_child_name("player")

    @Gtk.Template.Callback("on_sidebar_page_changed")
    def on_sidebar_page_changed(self, *args):
        if self.sidebar_stack.get_visible_child_name() == "player":
            self.playing_track_widget.set_visible(False)
        else:
            self.playing_track_widget.set_visible(True)

    def on_shuffle_changed(self, *args):
        self.shuffle_button.set_active(self.player_object.shuffle)
        self.settings.set_boolean("shuffle", self.player_object.shuffle)
        self.save_last_playing_thing()

    def update_slider(self, *args):
        """Update the progress bar and playback information.

        Called periodically to update the progress bar, song duration, current position
        and volume level.
        """
        # Just copy the duration from player here to avoid ui desync from player object
        self.duration = self.player_object.duration
        end_value = self.duration / Gst.SECOND

        # Follow changes from elsewhere (the system's mixer)
        if self.player_object.volume_available:
            volume = self.player_object.query_volume()
            if self._show_volume(volume) and not self.player_object.renderer:
                self._save_volume(volume)
        self.duration_label.set_label(utils.pretty_duration(end_value))

        position_ns = self.player_object.query_position(default=None)
        if position_ns is None:
            self.time_played_label.set_label(utils.pretty_duration(0))
            return
        position = position_ns / Gst.SECOND

        self.lyrics_widget.set_time(position)
        self.time_played_label.set_label(utils.pretty_duration(position))

        fraction = position / end_value if end_value else 0
        self.small_progress_bar.set_fraction(fraction)
        self.progress_bar.get_adjustment().set_value(fraction)
        self.previous_fraction = fraction

    def th_add_lyrics_to_page(self):
        try:
            lyrics = self.player_object.playing_track.lyrics()
            if lyrics:
                if lyrics.subtitles:
                    GLib.idle_add(self.lyrics_widget.set_lyrics, lyrics.subtitles)
                elif lyrics.text:
                    GLib.idle_add(self.lyrics_widget.set_lyrics, lyrics.text)
            else:
                GLib.idle_add(self.lyrics_widget.clear)
        except Exception:
            GLib.idle_add(self.lyrics_widget.clear)

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

    def change_jack_connect(self, destination: str) -> None:
        if self.settings.get_string("jack-connect") != destination:
            self.settings.set_string("jack-connect", destination)
            self.player_object.jack_connect = destination
            if self.settings.get_int("preferred-sink") == AudioSink.JACK:
                self.player_object.change_audio_sink(AudioSink.JACK)

    def on_customize_home(self, *_args) -> None:
        """Pick which of TIDAL's rows Home shows. A row stays hidden by its id,
        so rows whose title changes (the genre rows) stay hidden too."""
        home = self.navigation_view.find_page("home")
        rows = getattr(home, "rows", None) or []
        hidden = dict(self.settings.get_value("home-hidden-rows").unpack())

        dialog = Adw.PreferencesDialog(title=_("Customize Home"))
        page = Adw.PreferencesPage()

        my_tracks_group = Adw.PreferencesGroup()
        my_tracks_row = Adw.SwitchRow(
            title=_("My Tracks"),
            subtitle=_("Always show a button to your liked songs at the top"),
        )
        self.settings.bind(
            "home-my-tracks", my_tracks_row, "active", Gio.SettingsBindFlags.DEFAULT
        )
        my_tracks_row.connect(
            "notify::active",
            lambda *_: home.apply_hidden_rows() if home is not None else None,
        )
        my_tracks_group.add(my_tracks_row)
        page.add(my_tracks_group)

        group = Adw.PreferencesGroup(
            description=_("Turn off the rows you don't want on Home")
        )
        page.add(group)
        dialog.add(page)

        def add_row(module_id, title, subtitle=None):
            row = Adw.SwitchRow(title=title or module_id, active=module_id not in hidden)
            if subtitle:
                row.set_subtitle(subtitle)
            row.connect("notify::active", on_toggled, module_id, title)
            group.add(row)

        def on_toggled(row, _pspec, module_id, title):
            if row.get_active():
                hidden.pop(module_id, None)
            else:
                hidden[module_id] = title
            self.settings.set_value(
                "home-hidden-rows", GLib.Variant("a{ss}", hidden)
            )
            if home is not None:
                home.apply_hidden_rows()

        shown_ids = set()
        for module_id, title, _widget in rows:
            if module_id in shown_ids:
                continue
            shown_ids.add(module_id)
            subtitle = None
            if module_id.startswith("BASED_ON_YOUR_INTERESTS"):
                subtitle = _("Genre picks based on what you listen to")
            add_row(module_id, title, subtitle)
        # Hidden rows TIDAL didn't send today, so they can be turned back on
        for module_id, title in hidden.items():
            if module_id not in shown_ids:
                add_row(module_id, title, _("Not on Home today"))

        dialog.present(self)

    def change_normalization(self, state):
        if self.player_object.normalize != state:
            self.player_object.normalize = state
            self.settings.set_boolean("normalize", state)
            # recreate audio pipeline, kinda dirty ngl
            self.player_object.change_audio_sink(
                self.settings.get_int("preferred-sink")
            )

    def change_output_rate(self, rate: int) -> None:
        if self.settings.get_int("output-rate") != rate:
            self.settings.set_int("output-rate", rate)
            self.player_object.output_rate = rate
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

            dimensions = utils.get_best_dimensions(self.playing_track_picture)

            if self.video_covers_enabled and album.video_cover:
                threading.Thread(
                    target=utils.add_video_cover,
                    args=(
                        self.playing_track_picture,
                        self.videoplayer,
                        album,
                        dimensions,
                        self.in_background,
                        self.image_canc,
                    ),
                ).start()
            else:
                threading.Thread(
                    target=utils.add_picture,
                    args=(
                        self.playing_track_picture,
                        album,
                        dimensions,
                        self.image_canc,
                    ),
                ).start()

    def change_discord_rpc_enabled(self, state):
        if self.settings.get_boolean("discord-rpc") != state:
            self.settings.set_boolean("discord-rpc", state)
            self.player_object.set_discord_rpc(state)

    def on_hide_ai_music_changed(self, settings, key):
        ai.set_hidden(settings.get_boolean(key))
        if ai.get_hidden():
            utils.send_toast(_("AI-generated tracks are now hidden"), 2)
        self.player_object.skip_hidden()

    #
    #   PAGES ACTIONS CALLBACKS
    #

    def on_push_artist_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"artist-{item_id}", lambda: HTArtistPage.new_from_id(item_id).load()
        )

    def on_push_album_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"album-{item_id}", lambda: HTAlbumPage.new_from_id(item_id).load()
        )

    def on_push_track_credits_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"track-credits-{item_id}",
            lambda: HTCreditsPage.new_for_track(item_id).load(),
        )

    def on_push_album_info_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"album-info-{item_id}", lambda: HTCreditsPage.new_for_album(item_id).load()
        )

    def on_push_folder_page(self, action, parameter):
        """Open one of the user's playlist folders: its playlists and folders"""
        folder = utils.folders.get(parameter.get_string())
        if folder is None:
            return

        def make_page():
            page = HTFromFunctionPage(folder.name or _("Folder"))
            contents = []

            def load(limit=50, offset=0):
                # All at once in the chosen order (asked again from the start)
                if offset == 0:
                    contents[:] = utils.folder_contents(folder.id)
                return contents[offset : offset + limit]

            page.set_function(load)
            page.enable_search(_("Filter by name"), 50)
            page.enable_sort("playlists")

            def on_deleted():
                if self.navigation_view.find_page("collection"):
                    self.navigation_view.pop_to_tag("collection")
                else:
                    self.navigation_view.pop()

            menu, actions = utils.folder_menu(folder, on_deleted)
            button = Gtk.MenuButton(
                icon_name="view-more-symbolic", tooltip_text=_("Folder Options")
            )
            button.insert_action_group("folder", actions)
            page.builder.get_object("_header_bar").pack_end(button)
            button.set_menu_model(menu)

            def on_folders_changed():
                if page.get_root() is None:
                    utils.folder_listeners.remove(on_folders_changed)
                    return
                page.set_title(folder.name or _("Folder"))
                page._on_sort_changed()  # loads what's in it again

            utils.folder_listeners.append(on_folders_changed)
            return page.load()

        utils.push_page(f"folder-{folder.id}", make_page)

    def on_push_playlist_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"playlist-{item_id}", lambda: HTPlaylistPage.new_from_id(item_id).load()
        )

    def on_push_my_tracks_page(self, *args):
        """Open the saved tracks, newest first, as the Collection page's Tracks"""

        def make_page():
            page = HTFromFunctionPage(_("My Tracks"))
            tracks = utils.sorted_fetch("tracks", utils.session.user.favorites.tracks)
            page.set_function(
                lambda limit=50, offset=0: tracks(limit=limit, offset=offset)
            )
            page.auto_load.source = utils.MY_TRACKS
            page.enable_play(utils.MY_TRACKS)
            page.enable_search(_("Filter by title, artist or album"), 1000)
            page.enable_sort("tracks")
            return page.load()

        utils.push_page("my-tracks", make_page)

    def on_push_mix_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"mix-{item_id}", lambda: HTMixPage.new_from_id(item_id).load()
        )

    def on_push_track_radio_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"track-radio-{item_id}", lambda: HTMixPage.new_from_track(item_id).load()
        )

    def on_push_artist_radio_page(self, action, parameter):
        item_id = parameter.get_string()
        if item_id == "":
            return
        utils.push_page(
            f"artist-radio-{item_id}", lambda: HTMixPage.new_from_artist(item_id).load()
        )

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
