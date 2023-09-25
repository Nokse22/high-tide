# card_widget.py
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

import tidalapi
from tidalapi.page import PageItem, PageLink
from tidalapi.mix import Mix, MixType
from tidalapi.artist import Artist
from tidalapi.album import Album
from tidalapi.media import Track
from tidalapi.playlist import Playlist
from tidalapi.user import Favorites

@Gtk.Template(resource_path='/io/github/nokse22/high-tide/ui/widgets/card_widget.ui')
class CardWidget(Gtk.Box):
    __gtype_name__ = 'CardWidget'

    image = Gtk.Template.Child()
    button = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    detail_label = Gtk.Template.Child()
    track_artist_label = Gtk.Template.Child()
    track_artist_button = Gtk.Template.Child()

    def __init__(self, _item, _win):
        super().__init__()

        self.item = _item
        self.win = _win

        if isinstance(_item, Mix):
            self.make_mix_card()
        elif isinstance(_item, Album):
            self.make_album_card()
        elif isinstance(_item, Playlist):
            self.make_playlist_card()
        elif isinstance(_item, Artist):
            self.make_artist_card()
        elif isinstance(_item, PageItem):
            self.make_page_item_card()

    def make_mix_card(self):
        self.title_label.set_text(self.item.title)
        self.detail_label.set_text(self.item.sub_title)
        self.track_artist_label.set_visible(False)

        th = threading.Thread(target=utils.add_image, args=(self.image, self.item))
        th.deamon = True
        th.start()

    def make_album_card(self):
        self.title_label.set_text(self.item.name)
        self.track_artist_label.set_text(self.item.artist.name)
        self.detail_label.set_visible(False)

        th = threading.Thread(target=utils.add_image, args=(self.image, self.item))
        th.deamon = True
        th.start()

    def make_playlist_card(self):
        self.title_label.set_text(self.item.name)
        self.track_artist_label.set_visible(False)

        creator = self.item.creator
        if creator:
            creator = creator.name
        else:
            creator = "TIDAL"
        self.detail_label.set_text(f"by {creator}")

        th = threading.Thread(target=utils.add_image, args=(self.image, self.item))
        th.deamon = True
        th.start()

    def make_artist_card(self):
        self.title_label.set_text(self.item.name)
        self.detail_label.set_text("Artist")
        self.track_artist_label.set_visible(False)

        th = threading.Thread(target=utils.add_image, args=(self.image, self.item))
        th.deamon = True
        th.start()

    def make_page_item_card(self):
        self.title_label.set_text(self.item.short_header)
        self.detail_label.set_text(self.item.short_sub_header)
        self.track_artist_label.set_visible(False)

        th = threading.Thread(target=utils.add_image, args=(self.image, self.item))
        th.deamon = True
        th.start()

    @Gtk.Template.Callback("on_artist_button_clicked")
    def _on_artist_button_clicked(self, *args):
        from ..pages.artist_page import artistPage
        page = artistPage(self.win, self.item.artist, f"{self.item.artist.name}")
        page.load()
        self.win.navigation_view.push(page)

    @Gtk.Template.Callback("on_image_button_clicked")
    def _on_image_button_clicked(self, *args):
        if isinstance(self.item, Mix):
            from ..pages.mix_page import mixPage
            page = mixPage(self.win, self.item, f"{self.item.title}")
            page.load()
            self.win.navigation_view.push(page)

        elif isinstance(self.item, Album):
            from ..pages.album_page import albumPage
            page = albumPage(self.win, self.item, f"{self.item.name}")
            page.load()
            self.win.navigation_view.push(page)

        elif isinstance(self.item, Playlist):
            from ..pages.playlist_page import playlistPage
            page = playlistPage(self.win, self.item, f"{self.item.name}")
            page.load()
            self.win.navigation_view.push(page)

        elif isinstance(self.item, Artist):
            from ..pages.artist_page import artistPage
            page = artistPage(self.win, self.item, f"{self.item.name}")
            page.load()
            self.win.navigation_view.push(page)
