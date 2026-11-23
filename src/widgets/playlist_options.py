# playlist_options.py
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
from typing import Any, Callable

from gi.repository import Adw, Gio, GLib

from ..lib import utils


class PlaylistOptions:
    """The options of one of the user's own or saved playlists: edit, make
    public or private, move to a folder, delete. The same menu on the playlist's
    page and on its card.

    menu is the Gio.Menu and actions the action group (prefix "playlist") to
    insert on the widget showing it; call update() before showing the menu, as
    the folders can change.
    """

    def __init__(
        self,
        playlist: Any,
        on_changed: Callable[[Any], None] | None = None,
        on_deleted: Callable[[], None] | None = None,
    ) -> None:
        self.playlist = playlist
        self.on_changed = on_changed
        self.on_deleted = on_deleted
        self.menu = Gio.Menu()
        self.actions = Gio.SimpleActionGroup()
        for name, callback in (
            ("edit", self._on_edit),
            ("toggle-public", self._on_toggle_public),
            ("delete", self._on_delete),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.actions.add_action(action)
        move = Gio.SimpleAction.new("move-to-folder", GLib.VariantType.new("s"))
        move.connect("activate", self._on_move_to_folder)
        self.actions.add_action(move)
        self.update()

    @staticmethod
    def applies_to(playlist: Any) -> bool:
        """Whether a playlist has these options: one of the user's own or saved"""
        return utils.is_own_playlist(playlist) or utils.is_favourited(playlist)

    def update(self) -> None:
        """Fill the menu for the playlist as it is now"""
        self.menu.remove_all()
        own = utils.is_own_playlist(self.playlist)
        if own:
            self.menu.append(_("Edit playlist"), "playlist.edit")
            self.menu.append(
                _("Make private") if self.playlist.public else _("Make public"),
                "playlist.toggle-public",
            )
        folders = sorted(
            (f for f in utils.folders.values() if f.id),
            key=lambda f: (f.name or "").lower(),
        )
        move_menu = Gio.Menu()
        move_menu.append(_("No folder"), "playlist.move-to-folder::root")
        folder_section = Gio.Menu()
        for folder in folders:
            item = Gio.MenuItem.new(folder.name, None)
            item.set_action_and_target_value(
                "playlist.move-to-folder", GLib.Variant.new_string(str(folder.id))
            )
            folder_section.append_item(item)
        move_menu.append_section(None, folder_section)
        self.menu.append_submenu(_("Move to folder"), move_menu)
        if own:
            self.menu.append(_("Delete playlist"), "playlist.delete")

    def _changed(self, playlist: Any) -> None:
        self.playlist = playlist
        self.update()
        if self.on_changed:
            self.on_changed(playlist)

    def _on_move_to_folder(self, action, parameter) -> None:
        threading.Thread(
            target=utils.th_move_to_folder,
            args=(self.playlist, parameter.get_string()),
            daemon=True,
        ).start()

    def _on_edit(self, *args) -> None:
        from ..new_playlist import NewPlaylistWindow

        dialog = NewPlaylistWindow()
        dialog.set_editing(self.playlist.name, self.playlist.description)

        def on_save(dialog, title, description):
            dialog.close()
            threading.Thread(
                target=utils.th_edit_playlist,
                args=(self.playlist, title, description, self._changed),
            ).start()

        dialog.connect("create-playlist", on_save)
        dialog.present(utils.navigation_view.get_root())

    def _on_toggle_public(self, *args) -> None:
        threading.Thread(
            target=utils.th_set_playlist_public,
            args=(self.playlist, not self.playlist.public, self._changed),
        ).start()

    def _on_delete(self, *args) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Delete {}?").format(self.playlist.name),
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
                args=(self.playlist, self.on_deleted),
            ).start()

        dialog.connect("response", on_response)
        dialog.present(utils.navigation_view.get_root())
