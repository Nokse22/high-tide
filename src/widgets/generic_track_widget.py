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


from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio

import tidalapi
import threading

from ..lib import utils

from tidalapi.user import Favorites

@Gtk.Template(resource_path='/io/github/nokse22/high-tide/ui/widgets/generic_track_widget.ui')
class GenericTrackWidget(Gtk.ListBoxRow):
    __gtype_name__ = 'GenericTrackWidget'

    image = Gtk.Template.Child()
    track_album_label = Gtk.Template.Child()
    track_title_label = Gtk.Template.Child()
    track_duration_label = Gtk.Template.Child()
    artist_label = Gtk.Template.Child()
    playlists_submenu = Gtk.Template.Child()
    track_album_button = Gtk.Template.Child()
    _grid = Gtk.Template.Child()

    def __init__(self, _track, _win, is_album):
        super().__init__()

        if is_album:
            self._grid.remove(self.track_album_button)
            self.image.set_visible(False)
            self.track_title_label.set_margin_start(12)

        self.track = _track
        self.win = _win

        self.track_album_label.set_label(self.track.album.name)
        self.track_title_label.set_label(self.track.name)
        self.artist_label.set_label(self.track.artist.name)

        self.track_duration_label.set_label(utils.pretty_duration(self.track.duration))

        action_group = Gio.SimpleActionGroup()
        action_entries = [
            ("radio", self._get_radio),
            ("play-next", self._play_next),
            ("add-to-queue", self._add_to_queue),
            ("add-to-my-collection", self._add_to_my_collection)
        ]

        # action = Gio.SimpleAction.new("add-to-playlist", GLib.Variant("s"))
        # action.connect("activate", self.add_to_playlist)
        # action_group.add_action(action)

        # for index, playlist in enumerate(self.win.favourite_playlists):
        #     if index > 10:
        #         break
        #     item = Gio.MenuItem.new()
        #     item.set_label(playlist.name)
        #     item.set_action_and_target_value("trackwidget.add-to-playlist", GLib.Variant.new_string(playlist.id))
        #     self.playlists_submenu.insert_item(index, item)

        for index, playlist in enumerate(self.win.favourite_playlists):
            if index > 10:
                break
            item = Gio.MenuItem.new()
            item.set_label(playlist.name)
            action_name = f"add-to-playlist-{index}"  # Unique action name for each playlist
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", self._add_to_playlist, index)
            action_group.add_action(action)
            item.set_action_and_target_value(action_name, GLib.Variant.new_string(playlist.id))
            self.playlists_submenu.insert_item(index, item)

        for name, callback in action_entries:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            action_group.add_action(action)

        self.insert_action_group("trackwidget", action_group)

        th = threading.Thread(target=utils.add_image, args=(self.image, self.track.album))
        th.deamon = True
        th.start()

    def _get_radio(self, *args):
        from ..pages.track_radio_page import trackRadioPage
        page = trackRadioPage(self.win, self.track, f"{self.track.name} Radio")
        page.load()
        self.win.navigation_view.push(page)

    def _play_next(self, *args):
        self.win.player_object.add_next(self.track)

    def _add_to_queue(self, *args):
        self.win.player_object.add_to_queue(self.track)

    def _add_to_my_collection(self, *args):
        th = threading.Thread(target=self.th_add_to_my_collection, args=())
        th.deamon = True
        th.start()

    def th_add_to_my_collection(self):
        self.win.session.user.favorites.add_track(self.track.id)

    def _add_to_playlist(self, action, parameter, playlist_index):
        playlist_id = parameter.get_string()
        selected_playlist = self.win.favourite_playlists[playlist_index]

        print(f"Added to playlist: {selected_playlist.name}, ID: {playlist_id}")

    @Gtk.Template.Callback("on_artist_button_clicked")
    def _on_artist_button_clicked(self, *args):
        from ..pages.artist_page import artistPage
        page = artistPage(self.win, self.track.artist, f"{self.track.artist.name}")
        page.load()
        self.win.navigation_view.push(page)

    @Gtk.Template.Callback("on_album_button_clicked")
    def _on_album_button_clicked(self, *args):
        from ..pages.album_page import albumPage
        page = albumPage(self.win, self.track.album, f"{self.track.album.name}")
        page.load()
        self.win.navigation_view.push(page)
