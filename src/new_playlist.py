# new_playlist.py
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


from gi.repository import Adw, GObject, Gtk

import logging
logger = logging.getLogger(__name__)


@Gtk.Template(resource_path="/io/github/nokse22/high-tide/ui/new_playlist.ui")
class NewPlaylistWindow(Adw.Dialog):
    """Dialog window for creating new playlists.

    Provides a form interface for users to enter playlist name and description.
    Emits a 'create-playlist' signal when the user confirms creation.
    """

    __gtype_name__ = "NewPlaylistWindow"

    __gsignals__ = {
        "create-playlist": (GObject.SignalFlags.RUN_FIRST, None, (str, str))
    }

    playlist_name_entry = Gtk.Template.Child()
    playlist_description_entry = Gtk.Template.Child()
    create_button = Gtk.Template.Child()

    def __init__(self) -> None:
        super().__init__()

        self.playlist_name_entry.connect(
            "notify::text", self.on_title_text_inserted_func
        )

    @Gtk.Template.Callback("on_create_button_clicked")
    def on_create_button_clicked_func(self, *args) -> None:
        playlist_title: str = self.playlist_name_entry.get_text()
        playlist_description: str = self.playlist_description_entry.get_text()
        self.emit("create-playlist", playlist_title, playlist_description)

    def on_title_text_inserted_func(self, *args) -> None:
        playlist_title: str = self.playlist_name_entry.get_text()
        logger.info(f"!{playlist_title}!")
        if playlist_title != "":
            self.create_button.set_sensitive(True)
            return
        self.create_button.set_sensitive(False)
