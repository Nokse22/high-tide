# playlist_page.py
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

from gi.repository import Adw, Gio, Gtk

from .track_list_page import TrackListPage
from ..lib import utils
from ..new_playlist import NewPlaylistWindow


class HTPlaylistPage(TrackListPage):
    """It is used to display a playlist with author,
    number of tracks and duration"""

    __gtype_name__ = "HTPlaylistPage"

    tracks = None
    auto_load = None
    builder = None
    original_tracks = []
    current_sort = 0

    def _load_async(self):
        self.item = utils.get_playlist(self.id)
        self.tracks = self.item.tracks(limit=50)
        self.original_tracks = self.tracks.copy()

    def _load_finish(self):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/nokse22/high-tide/ui/pages_ui/tracks_list_template.ui"
        )

        creator_name = "TIDAL"
        if self.item.creator and self.item.creator.name:
            creator_name = self.item.creator.name

        title = self.item.name
        subtitle = _("by {}").format(creator_name)

        is_own_playlist = utils.is_own_playlist(self.item)
        if is_own_playlist:
            builder.get_object("_auto_load").set_playlist(self.item)
            self._add_playlist_actions(builder)

        self._setup_ui(
            builder,
            title,
            subtitle,
            self.tracks,
            reload_function=self.item.tracks,
        )

        if is_own_playlist:
            self._setup_playlist_menu(builder)

    def _setup_playlist_menu(self, builder):
        self.title_label = builder.get_object("_title_label")

        self.playlist_menu = Gio.Menu()
        menu_button = builder.get_object("_playlist_menu_button")
        menu_button.set_menu_model(self.playlist_menu)
        menu_button.set_visible(True)

        self._update_playlist_menu()

    def _add_playlist_actions(self, builder):
        action_group = Gio.SimpleActionGroup()
        for name, callback in (
            ("edit", self._on_edit),
            ("toggle-public", self._on_toggle_public),
            ("delete", self._on_delete),
        ):
            action = Gio.SimpleAction.new(name, None)
            self.signals.append((action, action.connect("activate", callback)))
            action_group.add_action(action)
        # On the content, not the page: the page's scrolled window doesn't see
        # action groups inserted on the page
        builder.get_object("_main").insert_action_group("playlist", action_group)

    def _update_playlist_menu(self):
        self.playlist_menu.remove_all()
        self.playlist_menu.append(_("Edit playlist"), "playlist.edit")
        self.playlist_menu.append(
            _("Make private") if self.item.public else _("Make public"),
            "playlist.toggle-public",
        )
        self.playlist_menu.append(_("Delete playlist"), "playlist.delete")

    def _on_edit(self, *args):
        dialog = NewPlaylistWindow()
        dialog.set_editing(self.item.name, self.item.description)

        def on_save(dialog, title, description):
            dialog.close()
            threading.Thread(
                target=utils.th_edit_playlist,
                args=(self.item, title, description, self._on_playlist_changed),
            ).start()

        dialog.connect("create-playlist", on_save)
        dialog.present(self.get_root())

    def _on_toggle_public(self, *args):
        threading.Thread(
            target=utils.th_set_playlist_public,
            args=(self.item, not self.item.public, self._on_playlist_changed),
        ).start()

    def _on_playlist_changed(self, playlist):
        self.item = playlist
        self.set_title(playlist.name)
        self.title_label.set_label(playlist.name)
        self._update_playlist_menu()

    def _on_delete(self, *args):
        dialog = Adw.AlertDialog(
            heading=_("Delete {}?").format(self.item.name),
            body=_("The playlist will be deleted from your TIDAL account."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dialog, response):
            if response != "delete":
                return
            threading.Thread(
                target=utils.th_delete_playlist,
                args=(self.item, self._on_deleted),
            ).start()

        dialog.connect("response", on_response)
        dialog.present(self.get_root())

    def _on_deleted(self):
        if utils.navigation_view.get_visible_page() is self:
            utils.navigation_view.pop()
        else:
            utils.navigation_view.remove(self)
