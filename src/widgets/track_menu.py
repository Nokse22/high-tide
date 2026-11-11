# track_menu.py
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
from typing import Any, Callable, List, Tuple

from gi.repository import Gio, GLib, Gtk

from ..lib import utils


class TrackMenu:
    """The menu of a track (go to album, add to queue, add to a playlist, block...).

    Fills the model of menu_button and adds the actions it uses to owner, under
    the "trackwidget" prefix. The menu is built when it's first opened.
    """

    def __init__(
        self,
        owner: Gtk.Widget,
        menu_button: Gtk.MenuButton,
        track: Any,
        signals: List[Tuple[Any, int]],
    ) -> None:
        self.owner = owner
        self.track = track
        self.signals = signals
        self.playlist = None
        self.on_removed_from_playlist: Callable | None = None
        self.built = False
        self.block_section = None

        self.menu = Gio.Menu()
        self.playlists_submenu = Gio.Menu()
        menu_button.set_menu_model(self.menu)

        self.action_group = Gio.SimpleActionGroup()
        owner.insert_action_group("trackwidget", self.action_group)

        self.signals.append(
            (menu_button, menu_button.connect("notify::active", self._on_activate))
        )

    def set_playlist(self, playlist, on_removed=None) -> None:
        """Show a "Remove from this playlist" option for one of the user's
        playlists.

        Args:
            playlist: The playlist the track is shown in
            on_removed: Called after the track is removed from the playlist
        """
        self.playlist = playlist
        self.on_removed_from_playlist = on_removed

    def _on_activate(self, *args) -> None:
        if not self.built:
            self._build()
        self._update_playlists_submenu()
        self._update_block_section()
        if not self.built:
            self._add_remove_section()
            self.built = True

    def _build(self) -> None:
        self.menu.append(
            _("Go to album"), f"win.push-album-page::{self.track.album.id}"
        )
        self.menu.append(
            _("Go to track radio"), f"win.push-track-radio-page::{self.track.id}"
        )
        self.menu.append(
            _("Show credits"), f"win.push-track-credits-page::{self.track.id}"
        )
        self.menu.append(_("Play next"), "trackwidget.play-next")
        self.menu.append(_("Add to queue"), "trackwidget.add-to-queue")
        self.menu.append(
            _("Add to my collection"), "trackwidget.add-to-my-collection"
        )
        self.menu.append(_("Copy share url"), "trackwidget.copy-share-url")
        self.menu.append_submenu(_("Add to a playlist"), self.playlists_submenu)

        action_entries = [
            ("play-next", self._play_next),
            ("add-to-queue", self._add_to_queue),
            ("add-to-my-collection", self._add_to_my_collection),
            ("copy-share-url", self._copy_share_url),
            ("new-playlist", self._new_playlist),
            ("remove-from-playlist", self._remove_from_playlist),
        ]
        for name, callback in action_entries:
            action = Gio.SimpleAction.new(name, None)
            self.signals.append((action, action.connect("activate", callback)))
            self.action_group.add_action(action)

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

    def _add_remove_section(self) -> None:
        if self.playlist is not None:
            remove_section = Gio.Menu()
            remove_section.append(
                _("Remove from this playlist"), "trackwidget.remove-from-playlist"
            )
            self.menu.append_section(None, remove_section)

    def _update_playlists_submenu(self) -> None:
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

    def _update_block_section(self) -> None:
        if self.block_section is None:
            self.block_section = Gio.Menu()
            self.menu.append_section(None, self.block_section)

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

    def _toggle_block_track(self, *args) -> None:
        utils.toggle_blocked(self.track)

    def _toggle_block_artist(self, action, parameter) -> None:
        artists = utils.get_track_artists(self.track)
        utils.toggle_blocked(artists[parameter.get_int16()])

    def _play_next(self, *args) -> None:
        utils.player_object.add_next(self.track)

    def _add_to_queue(self, *args) -> None:
        utils.player_object.add_to_queue(self.track)

    def _add_to_my_collection(self, *args) -> None:
        threading.Thread(
            target=utils.session.user.favorites.add_track, args=(self.track.id,)
        ).start()

    def _add_to_playlist(self, action, parameter) -> None:
        selected_playlist = utils.user_playlists[parameter.get_int16()]
        threading.Thread(
            target=utils.th_add_to_playlist, args=(selected_playlist, self.track)
        ).start()

    def _new_playlist(self, *args) -> None:
        utils.new_playlist(self.track)

    def _remove_from_playlist(self, *args) -> None:
        threading.Thread(
            target=utils.th_remove_from_playlist,
            args=(
                self.playlist,
                self.track,
                getattr(self.owner, "index", 0),
                self.on_removed_from_playlist,
            ),
        ).start()

    def _copy_share_url(self, *args) -> None:
        utils.share_this(self.track)
