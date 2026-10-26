# generic_track_widget.py
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

from gi.repository import Gio, GLib, GObject, Gtk

from ..disconnectable_iface import IDisconnectable
from ..lib import utils

import logging

logger = logging.getLogger(__name__)


@Gtk.Template(
    resource_path="/io/github/nokse22/high-tide/ui/widgets/generic_track_widget.ui"
)
class HTGenericTrackWidget(Gtk.ListBoxRow, IDisconnectable):
    """A widget for displaying a single track with playback and menu options.

    This widget shows track information including title, artist, album, duration,
    and cover art. It provides context menu actions for playing, adding to queue,
    adding to playlists, and other track-related operations.
    """

    __gtype_name__ = "HTGenericTrackWidget"

    image = Gtk.Template.Child()
    track_title_label = Gtk.Template.Child()
    track_duration_label = Gtk.Template.Child()
    playlists_submenu = Gtk.Template.Child()
    _grid = Gtk.Template.Child()
    explicit_label = Gtk.Template.Child()

    artist_label = Gtk.Template.Child()
    artist_label_2 = Gtk.Template.Child()
    track_album_label = Gtk.Template.Child()

    menu_button = Gtk.Template.Child()
    track_menu = Gtk.Template.Child()

    index = GObject.Property(type=int, default=0)

    def __init__(self, track):
        IDisconnectable.__init__(self)
        super().__init__()

        self.menu_activated = False
        self.block_section = None
        self.track = track
        self.playlist = None
        self.on_removed_from_playlist = None

        self.signals.append(
            (
                self.artist_label,
                self.artist_label.connect("activate-link", utils.open_uri),
            )
        )
        self.signals.append(
            (
                self.artist_label_2,
                self.artist_label_2.connect("activate-link", utils.open_uri),
            )
        )
        self.signals.append(
            (
                self.track_album_label,
                self.track_album_label.connect("activate-link", utils.open_uri),
            )
        )

        self.signals.append(
            (
                self.menu_button,
                self.menu_button.connect("notify::active", self._on_menu_activate),
            )
        )

        self.track_album_label.set_album(self.track.album)
        self.track_title_label.set_label(
            self.track.full_name
            if hasattr(self.track, "full_name")
            else self.track.name
        )
        self.artist_label.set_artists(self.track.artists)

        self.explicit_label.set_visible(self.track.explicit)

        self.track_duration_label.set_label(utils.pretty_duration(self.track.duration))

        if not self.track.available:
            self.set_activatable(False)
            self.set_sensitive(False)

        self._update_now_playing()
        self.signals.append((
            utils.player_object,
            utils.player_object.connect("song-changed", self._on_player_song_changed),
        ))
        self.signals.append((
            utils.player_object,
            utils.player_object.connect(
                "notify::playing", self._on_playing_changed
            ),
        ))

        threading.Thread(
            target=utils.add_image, args=(self.image, self.track.album)
        ).start()

        self.action_group = Gio.SimpleActionGroup()
        self.insert_action_group("trackwidget", self.action_group)

    def _on_player_song_changed(self, *args):
        self._update_now_playing()

    def _on_playing_changed(self, *args):
        self._update_now_playing()

    def _update_now_playing(self):
        is_now = (
            utils.player_object.playing_track is not None
            and self.track.id == utils.player_object.playing_track.id
        )
        if is_now:
            self.add_css_class("now-playing")
        else:
            self.remove_css_class("now-playing")

    def _on_menu_activate(self, *args):
        self._update_block_section()
        self._update_playlists_submenu()

        if self.menu_activated:
            return

        self.menu_activated = True

        self.track_menu.prepend(
            _("Go to track radio"), f"win.push-track-radio-page::{self.track.id}"
        )

        self.track_menu.prepend(
            _("Go to album"), f"win.push-album-page::{self.track.album.id}"
        )

        self.track_menu.insert(
            2, _("Show credits"), f"win.push-track-credits-page::{self.track.id}"
        )

        action_entries = [
            ("play-next", self._play_next),
            ("add-to-queue", self._add_to_queue),
            ("add-to-my-collection", self._th_add_to_my_collection),
            ("copy-share-url", self._copy_share_url),
        ]

        add_to_playlist_action = Gio.SimpleAction.new(
            "add-to-playlist", GLib.VariantType.new("n")
        )
        self.signals.append(
            (
                add_to_playlist_action,
                add_to_playlist_action.connect("activate", self._add_to_playlist),
            )
        )
        self.action_group.add_action(add_to_playlist_action)

        if self.playlist is not None:
            remove_section = Gio.Menu()
            remove_section.append(
                _("Remove from this playlist"), "trackwidget.remove-from-playlist"
            )
            self.track_menu.append_section(None, remove_section)
            action_entries.append(("remove-from-playlist", self._remove_from_playlist))

        action_entries.append(("new-playlist", self._new_playlist))

        for name, callback in action_entries:
            action = Gio.SimpleAction.new(name, None)
            self.signals.append((action, action.connect("activate", callback)))
            self.action_group.add_action(action)

    def set_playlist(self, playlist, on_removed=None):
        """Show a "Remove from this playlist" option for one of the user's
        playlists.

        Args:
            playlist: The playlist the track is shown in
            on_removed: Called after the track is removed from the playlist
        """
        self.playlist = playlist
        self.on_removed_from_playlist = on_removed

    def _update_playlists_submenu(self):
        # Rebuilt every time, so playlists created meanwhile show up
        self.playlists_submenu.remove_all()

        new_section = Gio.Menu()
        new_section.append(_("New playlist…"), "trackwidget.new-playlist")
        self.playlists_submenu.append_section(None, new_section)

        playlists_section = Gio.Menu()
        for index, playlist in enumerate(utils.user_playlists):
            item = Gio.MenuItem.new()
            item.set_label(playlist.name)
            item.set_action_and_target_value(
                "trackwidget.add-to-playlist", GLib.Variant.new_int16(index)
            )
            playlists_section.append_item(item)
        self.playlists_submenu.append_section(None, playlists_section)

    def _new_playlist(self, *args):
        utils.new_playlist(self.track)

    def _remove_from_playlist(self, *args):
        threading.Thread(
            target=utils.th_remove_from_playlist,
            args=(
                self.playlist,
                self.track,
                self.index,
                self.on_removed_from_playlist,
            ),
        ).start()

    def _update_block_section(self):
        if self.block_section is None:
            self.block_section = Gio.Menu()
            self.track_menu.append_section(None, self.block_section)

            block_track_action = Gio.SimpleAction.new("toggle-block-track", None)
            block_artist_action = Gio.SimpleAction.new(
                "toggle-block-artist", GLib.VariantType.new("n")
            )
            for action, callback in (
                (block_track_action, self._toggle_block_track),
                (block_artist_action, self._toggle_block_artist),
            ):
                self.signals.append((action, action.connect("activate", callback)))
                self.action_group.add_action(action)

        utils.fill_block_menu(self.block_section, self.track, "trackwidget")

    def _toggle_block_track(self, *args):
        utils.toggle_blocked(self.track)

    def _toggle_block_artist(self, action, parameter):
        artists = utils.get_track_artists(self.track)
        utils.toggle_blocked(artists[parameter.get_int16()])

    def _play_next(self, *args):
        utils.player_object.add_next(self.track)

    def _add_to_queue(self, *args):
        utils.player_object.add_to_queue(self.track)

    def _th_add_to_my_collection(self, *args):
        threading.Thread(target=self.th_add_to_my_collection, args=()).start()

    def th_add_to_my_collection(self):
        utils.session.user.favorites.add_track(self.track.id)

    def _add_to_playlist(self, action, parameter):
        playlist_index = parameter.get_int16()
        selected_playlist = utils.user_playlists[playlist_index]

        threading.Thread(
            target=utils.th_add_to_playlist, args=(selected_playlist, self.track)
        ).start()

    def _copy_share_url(self, *args):
        utils.share_this(self.track)
