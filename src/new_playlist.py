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


from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib

import tidalapi

@Gtk.Template(resource_path='/io/github/nokse22/high-tide/new_playlist.ui')
class NewPlaylistWindow(Adw.Window):
    __gtype_name__ = 'NewPlaylistWindow'

    playlist_name_entry = Gtk.Template.Child()
    playlist_description_entry = Gtk.Template.Child()
    create_button = Gtk.Template.Child()

    def __init__(self, _win, _session):
        super().__init__()

        self.session = _session
        self.playlist_name_entry.connect("notify::text", self.on_title_text_inserted_func)

    @Gtk.Template.Callback("on_create_button_clicked")
    def on_create_button_clicked_func(self, btn):
        playlist_title = self.playlist_name_entry.get_text()
        playlist_description = self.playlist_description_entry.get_text()
        self.session.user.create_playlist(playlist_title, playlist_description)

        self.destroy()

    # @Gtk.Template.Callback("on_title_text_inserted")
    def on_title_text_inserted_func(self, *args):
        playlist_title = self.playlist_name_entry.get_text()
        print(f"!{playlist_title}!")
        if playlist_title != "":
            self.create_button.set_sensitive(True)
            return
        self.create_button.set_sensitive(False)
            
